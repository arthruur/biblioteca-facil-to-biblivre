"""
A aplicação FastAPI: monta os routers e serve o frontend buildado.

Este arquivo não tem lógica de domínio — só composição. Toda regra mora nos
pacotes (`biblio.biblivre`, `biblio.catalogacao`), que também são o que os CLIs
de migração usam. Se aparecer regra de negócio aqui, ela está no lugar errado.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from biblio.catalogacao import config
from biblio.catalogacao.fila import carregar_do_disco

from .routers import acervo, catalogacao, fila, sistema

# O bundle do Vite. Em dev o front roda no dev server (porta 5173) e fala com
# esta API por proxy, então a pasta pode não existir — a API sobe do mesmo jeito.
# No container o pacote não fica dentro do repositório, daí o override por env.
WEB_DIST = Path(os.environ.get("BIBLIO_WEB_DIST")
                or (config.ROOT / "apps" / "web" / "dist"))

DESCRICAO = """
API do sistema de gestão de acervo.

* **catalogacao** — o bipe do celular: ISBN → metadados → lote → fila
* **fila** — revisão no PC e o único caminho que grava no BibLivre
* **acervo** — "este ISBN já está catalogado?" e a conexão que responde
* **sistema** — URL de acesso, QR code, saúde

A migração de acervo legado (Biblioteca Fácil → BibLivre) não está exposta em
HTTP: ela mora em `biblio.legado` + `biblio.biblivre` e roda pelos CLIs em
`scripts/`, porque é operação de onboarding assistida, não de uso diário.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Biblio — API de acervo",
        version="0.1.0",
        description=DESCRICAO,
        openapi_tags=[
            {"name": "catalogacao", "description": "Captura por código de barras."},
            {"name": "fila", "description": "Revisão e gravação no BibLivre."},
            {"name": "acervo", "description": "Dedup por ISBN e conexão."},
            {"name": "sistema", "description": "Diagnóstico do servidor."},
        ],
    )

    app.include_router(catalogacao.router, prefix="/api")
    app.include_router(catalogacao.alias, prefix="/api")
    app.include_router(fila.router, prefix="/api")
    app.include_router(acervo.router, prefix="/api")
    app.include_router(sistema.router, prefix="/api")

    _montar_frontend(app)
    return app


def _montar_frontend(app: FastAPI) -> None:
    """
    Serve o bundle do Vite, com fallback de SPA.

    `/` e `/fila` são rotas do cliente, não do servidor: as duas devolvem o
    mesmo index.html e o React decide o que renderizar.
    """
    index = WEB_DIST / "index.html"

    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"),
                  name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/fila", include_in_schema=False)
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
