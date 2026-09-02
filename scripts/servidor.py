"""
Servidor web para catalogacao de livros via codigo de barras ISBN.

Duas telas, dois papeis:
  /       captura no celular  — scanner continuo, acumula um lote de ISBNs
  /fila   revisao no PC       — dashboard da fila, edicao e envio ao BibLivre

Uso:
  python scripts/servidor.py                    # https://0.0.0.0:8000
  python scripts/servidor.py --porta 9000
  python scripts/servidor.py --sem-ssl          # http://localhost:8000
  python scripts/servidor.py --db-senha SENHA   # liga a checagem de ISBN ja catalogado

Acessa no celular: https://IP-DO-PC:8000
"""

import argparse
import io
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

sys.path.insert(0, str(Path(__file__).parent))
from catalogacao import acervo, config
from catalogacao.cert import gerar_certificado
from catalogacao.export import exportar_itens
from catalogacao.ficha import processar_foto
from catalogacao.fila import (
    acao_em_lote,
    adicionar_fila,
    atualizar_item,
    carregar_do_disco,
    carrinho_adicionar,
    carrinho_atualizar_quantidade,
    carrinho_enviar,
    carrinho_limpar,
    carrinho_listar,
    carrinho_remover,
    estatisticas,
    listar_fila,
    obter_item,
    reconsultar_acervo,
    remover_item,
)
from catalogacao.lookup import buscar_metadados
from catalogacao.rede import obter_ip_local

app = FastAPI(title="Catalogacao ISBN")


async def _to_thread(func, *args, **kwargs):
    import asyncio
    import functools

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


def _pagina(nome: str, substituir: dict | None = None) -> HTMLResponse:
    arq = config.STATIC_DIR / nome
    if not arq.exists():
        return HTMLResponse(f"<h1>{nome} nao encontrado</h1>", status_code=404)
    html = arq.read_text(encoding="utf-8")
    for chave, valor in (substituir or {}).items():
        html = html.replace(chave, valor)
    return HTMLResponse(html)


# --- Telas ---


@app.get("/", response_class=HTMLResponse)
async def index():
    return _pagina("index.html", {"{{SERVER_URL}}": config.SERVER_URL})


@app.get("/fila", response_class=HTMLResponse)
async def fila_page():
    return _pagina("fila.html")


# --- Captura ---


@app.get("/api/qrcode")
async def qrcode():
    import qrcode.image.svg

    img = qrcode.make(config.SERVER_URL, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@app.get("/api/lookup/{isbn}")
async def lookup(isbn: str):
    return JSONResponse(await _to_thread(buscar_metadados, isbn))


@app.post("/api/capturar")
async def capturar(foto: UploadFile = File(...)):
    return JSONResponse(await _to_thread(processar_foto, await foto.read()))


@app.post("/api/confirmar")
async def confirmar(dados: dict):
    item = await _to_thread(adicionar_fila, dados)
    return {"status": "ok", "mensagem": "Salvo na fila de revisao", "item": item}


# --- Acervo: o ISBN ja esta catalogado? ---


@app.get("/api/acervo/status")
async def acervo_status():
    return acervo.estado()


@app.get("/api/acervo/isbn/{isbn}")
async def acervo_isbn(isbn: str):
    achado = await _to_thread(acervo.buscar, isbn)
    if not achado:
        return {"existe": False, "isbn": isbn}
    return {"existe": True, "isbn": isbn, **achado}


@app.post("/api/db")
async def db_conectar(dados: dict):
    """Guarda credenciais em memoria, testa a conexao e reavalia a fila."""
    resumo = config.definir_db(dados or {})
    teste = await _to_thread(acervo.testar_conexao)
    if not teste.get("conectado"):
        return JSONResponse({"status": "erro", "config": resumo, **teste}, status_code=400)
    revisao = await _to_thread(reconsultar_acervo)
    return {"status": "ok", "config": resumo, **teste, "fila": revisao}


@app.get("/api/db")
async def db_estado():
    return {"config": {k: v for k, v in config.db_config().items() if k != "senha"},
            **acervo.estado()}


@app.post("/api/acervo/reindexar-cache")
async def acervo_reindexar():
    await _to_thread(acervo.indice, True)
    return {"status": "ok", **acervo.estado()}


# --- Fila de revisao ---


@app.get("/api/fila")
async def fila(status: str | None = None, busca: str | None = None):
    return listar_fila(status, busca)


@app.get("/api/fila/stats")
async def fila_stats():
    return estatisticas()


@app.get("/api/fila/export")
async def fila_export():
    dados = listar_fila()
    if dados["total"] == 0:
        return {"status": "vazio", "total": 0, "itens": []}
    return {"status": "ok", **dados}


@app.post("/api/fila/acoes")
async def fila_acoes(dados: dict):
    return acao_em_lote(dados.get("ids") or [], dados.get("acao") or "")


@app.post("/api/fila/reconsultar")
async def fila_reconsultar():
    return await _to_thread(reconsultar_acervo)


@app.get("/api/fila/{item_id}")
async def fila_item(item_id: str):
    item = obter_item(item_id)
    if item is None:
        return JSONResponse({"status": "nao_encontrado"}, status_code=404)
    return item


@app.put("/api/fila/{item_id}")
async def fila_editar(item_id: str, dados: dict):
    resultado = await _to_thread(atualizar_item, item_id, dados)
    if resultado.get("status") == "nao_encontrado":
        return JSONResponse(resultado, status_code=404)
    return resultado


@app.delete("/api/fila/{item_id}")
async def fila_remover(item_id: str):
    resultado = remover_item(item_id)
    if resultado.get("status") == "nao_encontrado":
        return JSONResponse(resultado, status_code=404)
    return resultado


@app.post("/api/fila/exportar-biblivre")
async def fila_exportar_biblivre(dados: dict | None = None):
    """
    Gera MRC/CSV e, com executar=true, grava no BibLivre.

    Corpo: {executar: bool, ids: [..]?, db: {senha, host?, ...}?}
    Sem `ids`, exporta tudo que esta pendente ou revisado.
    """
    dados = dados or {}
    executar = bool(dados.get("executar"))
    db_args = dados.get("db") if isinstance(dados.get("db"), dict) else None
    if db_args and db_args.get("senha"):
        config.definir_db(db_args)
    db_args = {**config.db_config(), **(db_args or {})}

    if config.carrinho:
        await _to_thread(carrinho_enviar)

    ids = dados.get("ids")
    if ids:
        alvo = set(ids)
        itens = [i for i in listar_fila()["itens"] if i.get("id") in alvo]
    else:
        itens = listar_fila("pendente,revisado")["itens"]

    if not itens:
        return JSONResponse({"status": "vazio", "mensagem": "Nada na fila para exportar"},
                            status_code=400)

    resultado = await _to_thread(exportar_itens, itens, executar, db_args)
    if executar and resultado.get("status") == "ok" and resultado.get("ids"):
        acao_em_lote(resultado["ids"], "exportado")
    return JSONResponse(resultado)


# --- Lote (antes "carrinho"): acumula ISBNs antes do envio ---
# Mantem alias /api/carrinho para compatibilidade


@app.post("/api/lote")
async def lote_add(dados: dict):
    isbn = (dados.get("isbn") or "").strip()
    if not isbn:
        return JSONResponse({"status": "erro", "mensagem": "ISBN vazio"}, status_code=400)
    return await _to_thread(carrinho_adicionar, isbn)


@app.get("/api/lote")
async def lote_get():
    return carrinho_listar()


@app.put("/api/lote/{isbn}")
async def lote_put(isbn: str, dados: dict):
    q = int(dados.get("quantidade") or dados.get("exemplares") or 1)
    return await _to_thread(carrinho_atualizar_quantidade, isbn, q)


@app.delete("/api/lote/{isbn}")
async def lote_del(isbn: str):
    return carrinho_remover(isbn)


@app.delete("/api/lote")
async def lote_clear():
    return carrinho_limpar()


@app.post("/api/lote/enviar")
async def lote_send():
    return await _to_thread(carrinho_enviar)


@app.post("/api/carrinho")
async def carrinho_add(dados: dict):
    return await lote_add(dados)


@app.get("/api/carrinho")
async def carrinho_get():
    return carrinho_listar()


@app.put("/api/carrinho/{isbn}")
async def carrinho_put(isbn: str, dados: dict):
    return await lote_put(isbn, dados)


@app.delete("/api/carrinho/{isbn}")
async def carrinho_del(isbn: str):
    return carrinho_remover(isbn)


@app.delete("/api/carrinho")
async def carrinho_clear():
    return carrinho_limpar()


@app.post("/api/carrinho/enviar")
async def carrinho_send():
    return await _to_thread(carrinho_enviar)


def main():
    p = argparse.ArgumentParser(description="Servidor de catalogacao por ISBN")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--sem-ssl", action="store_true", help="HTTP em localhost (sem HTTPS)")
    p.add_argument("--db-senha", help="senha do Postgres do BibLivre (ou PGPASSWORD)")
    p.add_argument("--db-host", help="host do Postgres (padrao: localhost)")
    p.add_argument("--db-nome", help="banco (padrao: biblivre4)")
    p.add_argument("--db-usuario", help="usuario (padrao: biblivre)")
    p.add_argument("--db-schema", help="schema da biblioteca (padrao: single)")
    args = p.parse_args()

    ip = obter_ip_local()
    config.DATA_DIR.mkdir(exist_ok=True)
    config.FILA_DIR.mkdir(exist_ok=True)
    config.STATIC_DIR.mkdir(exist_ok=True)

    config.definir_db({
        "senha": args.db_senha, "host": args.db_host, "dbname": args.db_nome,
        "user": args.db_usuario, "schema": args.db_schema,
    })

    pendentes = carregar_do_disco()
    print(f"\n  Fila carregada do disco: {pendentes} item(ns)")

    if config.db_config().get("senha") or os.environ.get("PGPASSWORD"):
        teste = acervo.testar_conexao()
        if teste.get("conectado"):
            total = len(acervo.indice(forcar=True))
            print(f"  Acervo conectado: {teste['obras']:,} obras, "
                  f"{teste['exemplares']:,} exemplares — {total:,} ISBNs indexados")
            reconsultar_acervo()
        else:
            print(f"  Acervo indisponivel ({teste.get('erro')}) — a checagem de "
                  "ISBN ja catalogado fica desligada ate configurar em /fila")
    else:
        print("  Sem senha do Postgres: checagem de ISBN ja catalogado desligada "
              "(configure na tela /fila ou use --db-senha)")

    if args.sem_ssl:
        config.SERVER_URL = f"http://localhost:{args.porta}"
        print(f"\n  Rodando em HTTP: {config.SERVER_URL}\n")
        uvicorn.run(app, host="127.0.0.1", port=args.porta)
    else:
        cert, key = gerar_certificado()
        config.SERVER_URL = f"https://{ip}:{args.porta}"
        print("\n  === Catalogacao ISBN ===")
        print(f"  No celular: {config.SERVER_URL}  (aceite o certificado)")
        print(f"  No PC:      {config.SERVER_URL}/fila\n")
        uvicorn.run(app, host=args.host, port=args.porta, ssl_certfile=cert, ssl_keyfile=key)


if __name__ == "__main__":
    main()
