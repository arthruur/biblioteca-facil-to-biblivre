"""
A aplicação FastAPI: monta os routers e serve o frontend buildado.

Este arquivo não tem lógica de domínio — só composição. Toda regra mora nos
pacotes (`biblio.biblivre`, `biblio.catalogacao`, `biblio.migracao`), que
também são o que os CLIs de migração usam. Se aparecer regra de negócio aqui, ela está no lugar errado.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from biblio.biblivre import acervo as _acervo
from biblio.biblivre import conexao
from biblio.catalogacao import config
from biblio.catalogacao.fila import carregar_do_disco, reconsultar_acervo
from biblio.migracao import execucao as migracao_execucao

from .routers import acervo, catalogacao, fila, lotes, migracao, sistema

# O bundle do Vite. Em dev o front roda no dev server (porta 5173) e fala com
# esta API por proxy, então a pasta pode não existir — a API sobe do mesmo jeito.
# No container o pacote não fica dentro do repositório, daí o override por env.
WEB_DIST = Path(os.environ.get("BIBLIO_WEB_DIST")
                or (config.ROOT / "apps" / "web" / "dist"))

DESCRICAO = """
API do sistema de gestão de acervo.

* **catalogacao** — o bipe do celular: ISBN → metadados → lote → fila
* **fila** — revisão no PC e o caminho diário que grava no BibLivre
* **migracao** — o acervo legado inteiro: `.bkp` → conferência → gravação
* **acervo** — "este ISBN já está catalogado?" e a conexão que responde
* **sistema** — URL de acesso, QR code, saúde

Dois caminhos escrevem no BibLivre, e eles têm ritmos diferentes. A fila é o do
dia a dia, item a item. A migração é o do primeiro dia, uma vez por biblioteca:
os mesmos módulos que os CLIs de `scripts/` usam, agora com relatório na tela
antes da transação — porque o que ela grava não tem desfazer.
"""


@asynccontextmanager
async def ciclo(app: FastAPI):
    """
    O que precisa acontecer **no processo que serve**, nao no que o lanca.

    Estava tudo em `servidor.py:main()`, e isso funcionava enquanto havia um
    processo so. Com `--reload` o uvicorn passa a rodar a aplicacao num
    subprocesso, que nao herda memoria nenhuma: a fila reidratada no pai ficava
    no pai, e a tela de revisao abria vazia com os JSON intactos no disco.
    Daqui para frente a subida mora no ciclo de vida da aplicacao, que roda
    igual nos dois modos.
    """
    # Em modo reload o pai nao consegue passar isto por atribuicao.
    if not config.SERVER_URL:
        config.SERVER_URL = os.environ.get("BIBLIO_SERVER_URL", "")

    pendentes = preparar()
    print(f"\n  Fila carregada do disco: {pendentes} item(ns)")

    # A migração também é trabalho de gente: o relatório que a pessoa leu para
    # decidir gravar não pode morrer num restart do uvicorn.
    retomada = migracao_execucao.carregar_do_disco()
    if retomada:
        print(f"  Migração retomada: {retomada['id']} ({retomada['fase']})")

    # O indice de ISBN custa uma varredura da `biblio_records` inteira (~15 mil
    # registros, alguns segundos). Pagar isso a cada save em desenvolvimento
    # nao se justifica: com BIBLIO_SEM_INDICE=1 ele e montado sob demanda, no
    # primeiro bipe, pelo TTL que `acervo.indice()` ja tem.
    if os.environ.get("BIBLIO_SEM_INDICE") == "1":
        print("  Índice de ISBN: sob demanda (BIBLIO_SEM_INDICE=1)")
    else:
        conectar_acervo()

    yield


def conectar_acervo() -> None:
    """
    Liga a checagem de ISBN já catalogado, se houver senha.

    Sem banco o app funciona igual, mas trata todo livro como obra nova — e a
    tela avisa disso em vez de degradar em silêncio.
    """
    if not (conexao.db_config().get("senha") or os.environ.get("PGPASSWORD")):
        print("  Sem senha do Postgres: checagem de ISBN já catalogado desligada "
              "(configure na tela de revisão, use --db-senha ou o .env)")
        return

    teste = conexao.testar_conexao()
    if not teste.get("conectado"):
        print(f"  Acervo indisponível ({teste.get('erro')}) — a checagem de "
              "ISBN já catalogado fica desligada até configurar na tela")
        return

    total = len(_acervo.indice(forcar=True))
    print(f"  Acervo conectado: {teste['obras']:,} obras, "
          f"{teste['exemplares']:,} exemplares — {total:,} ISBNs indexados")
    reconsultar_acervo()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Biblio — API de acervo",
        version="0.1.0",
        description=DESCRICAO,
        lifespan=ciclo,
        openapi_tags=[
            {"name": "catalogacao", "description": "Captura por código de barras."},
            {"name": "fila", "description": "Revisão e gravação no BibLivre."},
            {"name": "migracao", "description": "Acervo legado: .bkp → BibLivre."},
            {"name": "acervo", "description": "Dedup por ISBN e conexão."},
            {"name": "sistema", "description": "Diagnóstico do servidor."},
        ],
    )

    app.include_router(catalogacao.router, prefix="/api")
    app.include_router(catalogacao.alias, prefix="/api")
    app.include_router(fila.router, prefix="/api")
    app.include_router(lotes.router, prefix="/api")
    app.include_router(migracao.router, prefix="/api")
    app.include_router(acervo.router, prefix="/api")
    app.include_router(sistema.router, prefix="/api")

    _montar_frontend(app)
    return app


def _montar_frontend(app: FastAPI) -> None:
    """
    Serve o bundle do Vite, com fallback de SPA.

    `/`, `/fila`, `/migracao` e `/scanner-debug` são rotas do cliente, não do
    servidor: as quatro devolvem o mesmo index.html e o React decide o que
    renderizar. A lista é explícita de propósito — um catch-all engoliria erro
    de digitação em `/api/...` e devolveria HTML onde o celular espera JSON.
    """
    index = WEB_DIST / "index.html"

    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"),
                  name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/fila", include_in_schema=False)
    @app.get("/migracao", include_in_schema=False)
    @app.get("/scanner-debug", include_in_schema=False)
    async def spa():
        if not index.exists():
            return HTMLResponse(_sem_build(), status_code=503)
        return FileResponse(index)


def _sem_build() -> str:
    return """
    <h1>Frontend não buildado</h1>
    <p>A API está no ar — veja <a href="/docs">/docs</a>.</p>
    <p>Para as telas, rode:</p>
    <pre>cd apps/web &amp;&amp; npm install &amp;&amp; npm run build</pre>
    <p>Ou, em desenvolvimento, <code>npm run dev</code> (porta 5173, com HMR).</p>
    """


def preparar() -> int:
    """Cria as pastas de dados e reidrata a fila do disco. Devolve quantos itens."""
    config.garantir_pastas()
    return carregar_do_disco()


app = create_app()
