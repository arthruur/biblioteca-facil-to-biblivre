"""
Fila de revisão: o trabalho pendente do bibliotecário, no PC.

Ao contrário da captura, aqui **nada é apressado** e nada escreve no acervo sem
confirmação explícita. O export é o único ponto do sistema que grava no
BibLivre, e ele mostra antes quantas fichas nascem e quantas são reaproveitadas.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from biblio.biblivre import conexao
from biblio.catalogacao import lotes
from biblio.catalogacao.export import exportar_itens
from biblio.catalogacao.fila import (
    acao_em_lote,
    atualizar_item,
    carrinho_enviar,
    estatisticas,
    listar_fila,
    obter_item,
    reconsultar_acervo,
    remover_item,
)

from ..deps import em_thread
from ..schemas import AcaoEmLote, PedidoExport

router = APIRouter(prefix="/fila", tags=["fila"])


@router.get("", summary="Lista a fila (status aceita 'pendente,revisado')")
async def listar(status: str | None = None, busca: str | None = None):
    return listar_fila(status, busca)


@router.get("/stats", summary="Os sete indicadores da tela de revisão")
async def stats():
    return estatisticas()


@router.get("/export", summary="Dump da fila para conferência")
async def export():
    dados = listar_fila()
    if dados["total"] == 0:
        return {"status": "vazio", "total": 0, "itens": []}
    return {"status": "ok", **dados}


@router.post("/acoes", summary="revisado | pendente | ignorado | remover, em lote")
async def acoes(dados: AcaoEmLote):
    return acao_em_lote(dados.ids, dados.acao)


@router.post("/reconsultar", summary="Reavalia a fila inteira contra o acervo")
async def reconsultar():
    return await em_thread(reconsultar_acervo)


@router.post("/exportar-biblivre", summary="Gera MRC/CSV e, com executar, grava")
async def exportar_biblivre(dados: PedidoExport | None = None):
    """
    O único caminho que escreve no BibLivre.

    Sem `ids`, exporta tudo que está pendente ou revisado. O lote que ainda
    estiver aberto no celular é enviado antes, para não ficar trabalho para
    trás — quem clicou "exportar" no PC quis exportar tudo.
    """
    dados = dados or PedidoExport()

    db_args = dados.db.para_config() if dados.db else None
    if db_args and db_args.get("senha"):
        conexao.definir_db(db_args)
    db_args = {**conexao.db_config(), **(db_args or {})}

    # Bandeja aberta em qualquer aparelho entra antes: quem clicou "exportar"
    # no PC quis exportar tudo, inclusive o que o celular acabou de bipar e
    # ainda nao enviou.
    if lotes.totais()["itens"]:
        await em_thread(carrinho_enviar, None)

    if dados.ids:
        alvo = set(dados.ids)
        itens = [i for i in listar_fila()["itens"] if i.get("id") in alvo]
    else:
        itens = listar_fila("pendente,revisado")["itens"]

    if not itens:
        return JSONResponse(
            {"status": "vazio", "mensagem": "Nada na fila para exportar"},
            status_code=400)

    resultado = await em_thread(exportar_itens, itens, dados.executar, db_args)
    if dados.executar and resultado.get("status") == "ok" and resultado.get("ids"):
        acao_em_lote(resultado["ids"], "exportado")
    return JSONResponse(resultado)


# As rotas com {item_id} vêm por último: senão "/fila/stats" casaria com elas.

@router.get("/{item_id}")
async def item(item_id: str):
    achado = obter_item(item_id)
    if achado is None:
        return JSONResponse({"status": "nao_encontrado"}, status_code=404)
    return achado


@router.put("/{item_id}", summary="Edita campos; mexer no ISBN reconsulta o acervo")
async def editar(item_id: str, dados: dict):
    resultado = await em_thread(atualizar_item, item_id, dados)
    if resultado.get("status") == "nao_encontrado":
        return JSONResponse(resultado, status_code=404)
    return resultado


@router.delete("/{item_id}")
async def remover(item_id: str):
    resultado = remover_item(item_id)
    if resultado.get("status") == "nao_encontrado":
        return JSONResponse(resultado, status_code=404)
    return resultado
