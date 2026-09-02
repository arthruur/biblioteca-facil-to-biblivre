"""
Painel de lotes: as N bandejas que a tela do PC gerencia.

Cada celular na estante tem a sua (ver biblio.catalogacao.lotes). O PC nao bipa
— ele olha, renomeia, descarta e envia para a fila. As rotas por aparelho vivem
aqui; o bipe em si continua em `catalogacao.py`, porque a regra de lá ("a tela
do celular nunca bloqueia") vale para ele e não para estas.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from biblio.catalogacao import lotes
from biblio.catalogacao.fila import carrinho_enviar

from ..deps import em_thread

router = APIRouter(prefix="/lotes", tags=["lotes"])


@router.get("", summary="Todas as bandejas, com a versao do estado")
async def painel():
    """
    O que a tela do PC busca em laco.

    `versao` sobe a cada mutacao em qualquer bandeja: a tela compara com a que
    ja tem e só re-renderiza quando muda. Ver o docstring de `lotes.py` sobre
    por que contador e não SSE.
    """
    return lotes.listar()


@router.get("/versao", summary="So o contador — para laco de baixo custo")
async def versao():
    return {"versao": lotes.versao()}


@router.put("/{dispositivo}", summary="Renomeia um aparelho")
async def renomear(dispositivo: str, dados: dict):
    nome = (dados or {}).get("nome") or ""
    return lotes.renomear(dispositivo, nome)


@router.delete("/{dispositivo}", summary="Tira o aparelho do painel e descarta o lote")
async def esquecer(dispositivo: str):
    r = lotes.esquecer(dispositivo)
    if r["status"] == "nao_encontrado":
        return JSONResponse(r, status_code=404)
    return r


@router.delete("/{dispositivo}/itens", summary="Esvazia a bandeja de um aparelho")
async def limpar(dispositivo: str):
    return lotes.limpar(dispositivo)


@router.post("/{dispositivo}/enviar", summary="Manda a bandeja de um aparelho para a fila")
async def enviar(dispositivo: str):
    return await em_thread(carrinho_enviar, dispositivo)


@router.post("/enviar-tudo", summary="Manda todas as bandejas para a fila")
async def enviar_tudo():
    return await em_thread(carrinho_enviar, None)
