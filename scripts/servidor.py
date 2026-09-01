"""
Servidor web para catalogacao de livros via codigo de barras ISBN.

Uso:
  python scripts/servidor.py                    # https://0.0.0.0:8000
  python scripts/servidor.py --porta 9000
  python scripts/servidor.py --sem-ssl          # http://localhost:8000

Acessa no celular: https://IP-DO-PC:8000
"""

import argparse
import io
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

sys.path.insert(0, str(Path(__file__).parent))
from catalogacao import config
from catalogacao.cert import gerar_certificado
from catalogacao.ficha import processar_foto
from catalogacao.fila import (
    adicionar_fila,
    carrinho_adicionar,
    carrinho_enviar,
    carrinho_limpar,
    carrinho_listar,
    carrinho_remover,
    listar_fila,
)
from catalogacao.lookup import buscar_metadados
from catalogacao.rede import obter_ip_local

app = FastAPI(title="Catalogacao ISBN")


async def _to_thread(func, *args):
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8") if (config.STATIC_DIR / "index.html").exists() else "<h1>index.html nao encontrado</h1>"
    return HTMLResponse(html.replace("{{SERVER_URL}}", config.SERVER_URL))


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
    adicionar_fila(dados)
    return {"status": "ok", "mensagem": "Salvo na fila de revisao"}


@app.get("/api/fila")
async def fila():
    return listar_fila()


# --- Carrinho: acumula ISBNs antes do envio (scanner de documentos) ---


@app.post("/api/carrinho")
async def carrinho_add(dados: dict):
    isbn = (dados.get("isbn") or "").strip()
    if not isbn:
        return JSONResponse({"status": "erro", "mensagem": "ISBN vazio"}, status_code=400)
    return await _to_thread(carrinho_adicionar, isbn)


@app.get("/api/carrinho")
async def carrinho_get():
    return carrinho_listar()


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
    args = p.parse_args()

    ip = obter_ip_local()
    config.DATA_DIR.mkdir(exist_ok=True)
    config.FILA_DIR.mkdir(exist_ok=True)
    config.STATIC_DIR.mkdir(exist_ok=True)

    if args.sem_ssl:
        config.SERVER_URL = f"http://localhost:{args.porta}"
        print(f"\n  Rodando em HTTP: {config.SERVER_URL}\n")
        uvicorn.run(app, host="127.0.0.1", port=args.porta)
    else:
        cert, key = gerar_certificado()
        config.SERVER_URL = f"https://{ip}:{args.porta}"
        print(f"\n  === Catalogacao ISBN ===")
        print(f"  No celular: {config.SERVER_URL}  (aceite o certificado)\n")
        uvicorn.run(app, host=args.host, port=args.porta, ssl_certfile=cert, ssl_keyfile=key)


if __name__ == "__main__":
    main()
