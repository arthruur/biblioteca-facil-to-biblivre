"""
Quem está no balcão. Sessão em memória, autenticada contra `logins`.

ESQUELETO DO INTEGRADOR — dono é o pacote **A8**; a regra de negócio é do
`biblio.biblivre.operador` (pacote A4). O token volta no corpo e o cliente o
reenvia em `X-Sessao`, na mesma mecânica do `X-Dispositivo` que a captura já
usa — cabeçalho porque é identidade de quem chama, não dado da chamada.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/sessao", tags=["sessao"])


def _pendente(rota: str):
    return JSONResponse(
        {"status": "erro", "codigo": "nao_implementado",
         "mensagem": f"{rota}: pendente (pacote A8 do plano de agentes)"},
        status_code=501)


@router.post("", summary="Entra com o login do BibLivre")
async def entrar():
    return _pendente("POST /sessao")


@router.get("", summary="A sessão corrente (401 se não houver)")
async def atual():
    return _pendente("GET /sessao")


@router.delete("", summary="Sai")
async def sair():
    return _pendente("DELETE /sessao")
