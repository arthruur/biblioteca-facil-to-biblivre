"""
Acervo: a pergunta "este ISBN já está catalogado?" e a conexão que a responde.

Banco desconectado nunca degrada em silêncio. Sem ele todo livro escaneado
vira obra nova, e o dano é duplicata no acervo — por isso `estado()` sempre diz
se o índice existe e quando foi montado, e a tela mostra isso o tempo todo.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from biblio.biblivre import acervo, conexao
from biblio.catalogacao.fila import reconsultar_acervo

from ..deps import em_thread
from ..schemas import ConexaoDb

router = APIRouter(tags=["acervo"])


@router.get("/acervo/status", summary="Diagnóstico do índice de ISBN")
async def status():
    return acervo.estado()


@router.get("/acervo/isbn/{isbn}", summary="Este ISBN já está no acervo?")
async def por_isbn(isbn: str):
    achado = await em_thread(acervo.buscar, isbn)
    if not achado:
        return {"existe": False, "isbn": isbn}
    return {"existe": True, "isbn": isbn, **achado}


@router.post("/acervo/reindexar-cache", summary="Força nova varredura do acervo")
async def reindexar_cache():
    await em_thread(acervo.indice, True)
    return {"status": "ok", **acervo.estado()}


@router.get("/db", summary="Estado da conexão (nunca devolve a senha)")
async def db_estado():
    return {"config": conexao.sem_senha(), **acervo.estado()}


@router.post("/db", summary="Conecta, testa e reavalia a fila inteira")
async def db_conectar(dados: ConexaoDb):
    """
    Guarda as credenciais em memória, testa a conexão e reavalia a fila.

    A senha vive só no processo — nunca vai para disco. Ao conectar com
    sucesso a fila inteira é reconsultada, e a resposta diz quantos itens
    passaram a ser "já no acervo": é a informação que muda a decisão de quem
    está prestes a exportar.
    """
    resumo = conexao.definir_db(dados.para_config())
    teste = await em_thread(conexao.testar_conexao)
    if not teste.get("conectado"):
        return JSONResponse({"status": "erro", "config": resumo, **teste},
                            status_code=400)
    revisao = await em_thread(reconsultar_acervo)
    return {"status": "ok", "config": resumo, **teste, "fila": revisao}
