"""
Captura: o que a tela do celular chama a cada bipe.

A regra que manda aqui é a da spec: **a tela do celular nunca bloqueia.** Nada
neste router pode exigir decisão do usuário, e falha de lookup devolve 200 com
o campo vazio em vez de erro — perder um bipe custa mais do que um card sem
título.
"""

from urllib.parse import unquote

from fastapi import APIRouter, File, Header, UploadFile
from fastapi.responses import JSONResponse

from biblio.catalogacao.fila import (
    adicionar_fila,
    carrinho_adicionar,
    carrinho_atualizar_quantidade,
    carrinho_enviar,
    carrinho_limpar,
    carrinho_listar,
    carrinho_remover,
)
from biblio.catalogacao.lookup import buscar_metadados

from ..deps import em_thread
from ..schemas import LoteEntrada, Quantidade

router = APIRouter(tags=["catalogacao"])

# Quem esta bipando.
#
# O celular gera um uuid na primeira visita, guarda no `localStorage` e manda
# em `X-Dispositivo`. Nao e autenticacao: a rede e a LAN da biblioteca, e o que
# se quer e separar a bandeja de um aparelho da do outro (ver `lotes.py`).
# Requisicao sem cabecalho cai no lote do balcao — o caso do proprio PC
# digitando ISBN a mao.
#
# `X-Dispositivo-Nome` e opcional e chega percent-encoded (cabecalho HTTP nao
# carrega acento, e "Celular da Ana" tem). A tela prefere batizar o aparelho
# por PUT /api/lotes/{id}, que passa pelo corpo e nao precisa disso.
Dispositivo = Header(default=None, alias="X-Dispositivo")
DispositivoNome = Header(default=None, alias="X-Dispositivo-Nome")


def _nome(bruto: str | None) -> str | None:
    if not bruto:
        return None
    return unquote(bruto)


@router.get("/lookup/{isbn}", summary="Metadados de um ISBN, sem adicionar ao lote")
async def lookup(isbn: str):
    return JSONResponse(await em_thread(buscar_metadados, isbn))


@router.post("/capturar", summary="OCR de ficha CIP (livro sem código de barras)")
async def capturar(foto: UploadFile = File(...)):
    # `ficha` puxa OpenCV e Tesseract; importar sob demanda deixa o servidor
    # subir mesmo numa instalação que só usa o código de barras.
    try:
        from biblio.catalogacao.ficha import processar_foto
    except ImportError as e:
        return JSONResponse(
            {"status": "erro",
             "mensagem": f"OCR indisponível nesta instalação: {e}"},
            status_code=501)
    return JSONResponse(await em_thread(processar_foto, await foto.read()))


@router.post("/confirmar", summary="Envia um item direto para a fila")
async def confirmar(dados: dict):
    item = await em_thread(adicionar_fila, dados)
    return {"status": "ok", "mensagem": "Salvo na fila de revisao", "item": item}


# --- Lote: a bandeja do scanner, volátil de propósito ---

@router.post("/lote", summary="Bipe: adiciona ISBN ao lote (repetido soma exemplar)")
async def lote_add(dados: LoteEntrada,
                   dispositivo: str | None = Dispositivo,
                   dispositivo_nome: str | None = DispositivoNome):
    isbn = (dados.isbn or "").strip()
    if not isbn:
        return JSONResponse({"status": "erro", "mensagem": "ISBN vazio"},
                            status_code=400)
    return await em_thread(carrinho_adicionar, isbn, dispositivo,
                           _nome(dispositivo_nome))


@router.get("/lote")
async def lote_get(dispositivo: str | None = Dispositivo,
                   dispositivo_nome: str | None = DispositivoNome):
    """
    A bandeja de quem pergunta.

    Sem cabecalho devolve o agregado de todas — e o que a tela do PC usava
    antes de existir o painel, e o que os alias /api/carrinho* continuam
    vendo.
    """
    return carrinho_listar(dispositivo, _nome(dispositivo_nome))


@router.put("/lote/{isbn}", summary="Ajusta quantos exemplares deste título")
async def lote_put(isbn: str, dados: Quantidade,
                   dispositivo: str | None = Dispositivo):
    return await em_thread(carrinho_atualizar_quantidade, isbn, dados.valor(),
                           dispositivo)


@router.delete("/lote/{isbn}")
async def lote_del(isbn: str, dispositivo: str | None = Dispositivo):
    return carrinho_remover(isbn, dispositivo)


@router.delete("/lote")
async def lote_clear(dispositivo: str | None = Dispositivo):
    return carrinho_limpar(dispositivo)


@router.post("/lote/enviar", summary="Move o lote inteiro para a fila de revisão")
async def lote_send(dispositivo: str | None = Dispositivo):
    return await em_thread(carrinho_enviar, dispositivo)


# --- Alias histórico: /api/carrinho* ---
# "Carrinho" era o nome antigo do lote. O vocabulário mudou (docs/SPEC_UI.md,
# seção 8), mas há telas e atalhos apontando para o caminho velho, e quebrar
# um bipe em campo por causa de renomeação seria o pior tipo de regressão.
#
# Cada alias declara os próprios cabeçalhos e chama a camada de dados direto,
# em vez de reusar a função da rota nova: chamada Python não passa pelo
# FastAPI, então um `Header(...)` como default chegaria como FieldInfo no lugar
# do valor.

alias = APIRouter(tags=["catalogacao (alias)"], include_in_schema=False)


@alias.post("/carrinho")
async def carrinho_add(dados: LoteEntrada,
                       dispositivo: str | None = Dispositivo,
                       dispositivo_nome: str | None = DispositivoNome):
    isbn = (dados.isbn or "").strip()
    if not isbn:
        return JSONResponse({"status": "erro", "mensagem": "ISBN vazio"},
                            status_code=400)
    return await em_thread(carrinho_adicionar, isbn, dispositivo,
                           _nome(dispositivo_nome))


@alias.get("/carrinho")
async def carrinho_get(dispositivo: str | None = Dispositivo):
    return carrinho_listar(dispositivo)


@alias.put("/carrinho/{isbn}")
async def carrinho_put(isbn: str, dados: Quantidade,
                       dispositivo: str | None = Dispositivo):
    return await em_thread(carrinho_atualizar_quantidade, isbn, dados.valor(),
                           dispositivo)


@alias.delete("/carrinho/{isbn}")
async def carrinho_del(isbn: str, dispositivo: str | None = Dispositivo):
    return carrinho_remover(isbn, dispositivo)


@alias.delete("/carrinho")
async def carrinho_clear(dispositivo: str | None = Dispositivo):
    return carrinho_limpar(dispositivo)


@alias.post("/carrinho/enviar")
async def carrinho_send(dispositivo: str | None = Dispositivo):
    return await em_thread(carrinho_enviar, dispositivo)
