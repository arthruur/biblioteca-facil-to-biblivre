"""
A aplicação FastAPI: monta os routers e serve as telas.

Este arquivo não tem lógica de domínio — só composição. Toda regra mora nos
pacotes (`biblio.biblivre`, `biblio.catalogacao`), que também são o que os CLIs
de migração usam. Se aparecer regra de negócio aqui, ela está no lugar errado.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from biblio.catalogacao import config
from biblio.catalogacao.fila import carregar_do_disco

from .routers import acervo, catalogacao, fila, sistema

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

    _montar_telas(app)
    return app


def _pagina(nome: str, substituir: dict | None = None) -> HTMLResponse:
    arq = config.ROOT / "static" / nome
    if not arq.exists():
        return HTMLResponse(f"<h1>{nome} nao encontrado</h1>", status_code=404)
    html = arq.read_text(encoding="utf-8")
    for chave, valor in (substituir or {}).items():
        html = html.replace(chave, valor)
    return HTMLResponse(html)


def _montar_telas(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        return _pagina("index.html", {"{{SERVER_URL}}": config.SERVER_URL})

    @app.get("/fila", response_class=HTMLResponse, include_in_schema=False)
    async def fila_page():
        return _pagina("fila.html")


def preparar() -> int:
    """Cria as pastas de dados e reidrata a fila do disco. Devolve quantos itens."""
    config.garantir_pastas()
    return carregar_do_disco()


app = create_app()
