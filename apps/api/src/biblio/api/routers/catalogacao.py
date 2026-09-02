"""
Captura: o que a tela do celular chama a cada bipe.

A regra que manda aqui é a da spec: **a tela do celular nunca bloqueia.** Nada
neste router pode exigir decisão do usuário, e falha de lookup devolve 200 com
o campo vazio em vez de erro — perder um bipe custa mais do que um card sem
título.
"""

from fastapi import APIRouter, File, UploadFile
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
async def lote_add(dados: LoteEntrada):
    isbn = (dados.isbn or "").strip()
    if not isbn:
        return JSONResponse({"status": "erro", "mensagem": "ISBN vazio"},
                            status_code=400)
    return await em_thread(carrinho_adicionar, isbn)


@router.get("/lote")
async def lote_get():
    return carrinho_listar()


@router.put("/lote/{isbn}", summary="Ajusta quantos exemplares deste título")
async def lote_put(isbn: str, dados: Quantidade):
    return await em_thread(carrinho_atualizar_quantidade, isbn, dados.valor())


@router.delete("/lote/{isbn}")
async def lote_del(isbn: str):
    return carrinho_remover(isbn)


@router.delete("/lote")
async def lote_clear():
    return carrinho_limpar()


@router.post("/lote/enviar", summary="Move o lote inteiro para a fila de revisão")
async def lote_send():
    return await em_thread(carrinho_enviar)


# --- Alias histórico: /api/carrinho* ---
# "Carrinho" era o nome antigo do lote. O vocabulário mudou (docs/SPEC_UI.md,
# seção 8), mas há telas e atalhos apontando para o caminho velho, e quebrar
# um bipe em campo por causa de renomeação seria o pior tipo de regressão.

alias = APIRouter(tags=["catalogacao (alias)"], include_in_schema=False)


@alias.post("/carrinho")
async def carrinho_add(dados: LoteEntrada):
    return await lote_add(dados)


@alias.get("/carrinho")
async def carrinho_get():
    return carrinho_listar()


@alias.put("/carrinho/{isbn}")
async def carrinho_put(isbn: str, dados: Quantidade):
    return await lote_put(isbn, dados)


@alias.delete("/carrinho/{isbn}")
async def carrinho_del(isbn: str):
    return carrinho_remover(isbn)


@alias.delete("/carrinho")
async def carrinho_clear():
    return carrinho_limpar()


@alias.post("/carrinho/enviar")
async def carrinho_send():
    return await em_thread(carrinho_enviar)
