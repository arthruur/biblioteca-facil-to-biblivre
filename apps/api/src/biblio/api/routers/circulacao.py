"""
Balcão: empréstimo, devolução, renovação e consulta.

ESQUELETO DO INTEGRADOR — o dono deste arquivo é o pacote **A8** do
docs/PLANO_AGENTES.html, que substitui o corpo das rotas. O que está aqui fixa
os caminhos e os corpos que as telas (A6 e A7) já consomem, e faz o contrato
aparecer no `/docs` enquanto o resto não chega.

Quando implementar, três coisas não são negociáveis:

  * **este arquivo é quem commita** — uma transação por requisição: abre a
    conexão, chama `biblio.biblivre.emprestimo`, `con.commit()` no sucesso,
    `con.rollback()` em qualquer exceção, fecha sempre;
  * tudo que toca banco passa por `deps.em_thread` — bloquear o event loop
    trava a captura, que não pode esperar;
  * o `operador_id` sai da **sessão**, nunca do corpo da requisição.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/circulacao", tags=["circulacao"])


def _pendente(rota: str):
    return JSONResponse(
        {"status": "erro", "codigo": "nao_implementado",
         "mensagem": f"{rota}: pendente (pacote A8 do plano de agentes)"},
        status_code=501)


@router.get("/resolver", summary="Tombo, ISBN ou leitor? Quem decide é o servidor")
async def resolver(codigo: str = ""):
    return _pendente("GET /circulacao/resolver")


@router.get("/leitores", summary="Busca de leitor por nome")
async def leitores(busca: str = ""):
    return _pendente("GET /circulacao/leitores")


@router.get("/leitor/{user_id}", summary="Ficha, situação e empréstimos do leitor")
async def leitor(user_id: int):
    return _pendente("GET /circulacao/leitor/{user_id}")


@router.get("/exemplar/{holding_id}", summary="Exemplar, obra e empréstimo em aberto")
async def exemplar(holding_id: int):
    return _pendente("GET /circulacao/exemplar/{holding_id}")


@router.post("/emprestimos", summary="Empresta (201) ou barra com o motivo (409)")
async def emprestar():
    return _pendente("POST /circulacao/emprestimos")


@router.post("/devolucoes", summary="Devolve, com multa e reserva pendente")
async def devolver():
    return _pendente("POST /circulacao/devolucoes")


@router.post("/renovacoes", summary="Renova um empréstimo em aberto")
async def renovar():
    return _pendente("POST /circulacao/renovacoes")


@router.get("/pendencias", summary="Atrasados e movimento do dia")
async def pendencias(tipo: str = "atrasados"):
    return _pendente("GET /circulacao/pendencias")
