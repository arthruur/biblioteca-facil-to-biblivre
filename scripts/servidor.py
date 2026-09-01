"""
Servidor web para captura de ficha CIP via camera do celular.

Roda um FastAPI que:
  1. Serve a pagina HTML com acesso a camera
  2. Recebe a foto capturada
  3. Roda deteccao + OCR + extracao de ISBN
  4. Retorna os campos extraidos

Uso:
  python scripts/servidor.py                    # inicia em http://0.0.0.0:8000
  python scripts/servidor.py --porta 9000       # porta alternativa

Acessa no celular: http://IP-DO-PC:8000
"""

import argparse
import io
import json
import socket
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Importar funções dos scripts locais
sys.path.insert(0, str(Path(__file__).parent))
from detectar_ficha import binarizar, encontrar_ficha, nitidez, preparar_para_ocr
from extrair_isbn import extrair_isbn_do_texto

# --- Configuracao ---
DATA_DIR = Path(__file__).parent.parent / "data"
FILA_DIR = DATA_DIR / "fila"
STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Catalogacao por Foto")

# URL do servidor (preenchida ao iniciar)
SERVER_URL = ""

# Estado em memória: fila de itens capturados
fila_lock = threading.Lock()
fila: list[dict] = []


def obter_ip_local() -> str:
    """Descobre o IP local da máquina na rede."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def processar_foto(bytes_foto: bytes) -> dict:
    """
    Pipeline completo: bytes → OpenCV → detecção → OCR → extração.
    Retorna dict com status e campos.
    """
    # Decodificar imagem
    arr = np.frombuffer(bytes_foto, dtype=np.uint8)
    original = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if original is None:
        return {"status": "erro", "mensagem": "Não foi possível ler a imagem"}

    # Gate de nitidez
    niv = nitidez(original)
    if niv < 30:
        return {"status": "erro", "mensagem": f"Imagem borrada (nitidez: {niv:.0f}). Segure firme."}

    # Detectar e retificar ficha
    contorno, warp = encontrar_ficha(original)
    if contorno is None:
        return {"status": "erro", "mensagem": "Ficha CIP não detectada. Aponte para a ficha."}

    # Preparar para OCR (upscale + binarização)
    ocr_img = preparar_para_ocr(warp)

    # Salvar temporariamente e rodar OCR
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        cv2.imwrite(tmp.name, ocr_img)
        tmp_path = tmp.name

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        from PIL import Image
        img_pil = Image.open(tmp_path)
        texto_ocr = pytesseract.image_to_string(img_pil, lang="por", config="--psm 6")
    except Exception as e:
        return {"status": "erro", "mensagem": f"Erro no OCR: {str(e)}"}
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Extrair ISBN
    isbn_encontrados = extrair_isbn_do_texto(texto_ocr)

    # Extrair CDD e Cutter do texto
    cdd = ""
    cutter = ""
    for linha in texto_ocr.split("\n"):
        linha = linha.strip()
        if linha.upper().startswith("CDD"):
            cdd = linha.split(":", 1)[-1].strip() if ":" in linha else ""
        elif linha.upper().startswith("CUTTER"):
            cutter = linha.split(":", 1)[-1].strip() if ":" in linha else ""

    # Montar resultado
    resultado = {
        "status": "ok",
        "texto_ocr": texto_ocr.strip(),
        "cdd": cdd,
        "cutter": cutter,
        "isbn": None,
        "isbn_valido": None,
    }

    if isbn_encontrados:
        # Pegar o ISBN válido, ou o primeiro se nenhum for válido
        valido = [i for i in isbn_encontrados if i["valido"]]
        isbn = valido[0] if valido else isbn_encontrados[0]
        resultado["isbn"] = isbn["isbn"]
        resultado["isbn_valido"] = isbn["valido"]

    return resultado


# --- Rotas ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve a página principal com a URL do servidor embutida."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
        # Substituir placeholder pela URL real do servidor
        html = html.replace("{{SERVER_URL}}", SERVER_URL)
        return HTMLResponse(html)
    return HTMLResponse("<h1>Arquivo static/index.html nao encontrado</h1>")


@app.get("/api/qrcode")
async def qrcode():
    """Gera QR code com a URL do servidor."""
    import qrcode
    import qrcode.image.svg

    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(SERVER_URL, image_factory=factory)
    buffer = io.BytesIO()
    img.save(buffer)
    return Response(content=buffer.getvalue(), media_type="image/svg+xml")


@app.post("/api/capturar")
async def capturar(foto: UploadFile = File(...)):
    """Recebe foto, processa e retorna campos extraídos."""
    bytes_foto = await foto.read()

    # Processar em thread separada para não bloquear
    resultado = await asyncio_to_sync(processar_foto, bytes_foto)
    return JSONResponse(resultado)


@app.post("/api/confirmar")
async def confirmar(dados: dict):
    """Salva item confirmado na fila de revisão."""
    item = {
        "timestamp": datetime.now().isoformat(),
        "isbn": dados.get("isbn"),
        "cdd": dados.get("cdd"),
        "cutter": dados.get("cutter"),
        "texto_ocr": dados.get("texto_ocr"),
        "confirmado": True,
    }

    with fila_lock:
        fila.append(item)

    # Salvar em disco
    FILA_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = FILA_DIR / f"fila_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    arquivo.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "ok", "mensagem": "Salvo na fila de revisão"}


@app.get("/api/fila")
async def listar_fila():
    """Lista itens na fila (para revisão futura)."""
    with fila_lock:
        return {"itens": fila, "total": len(fila)}


async def asyncio_to_sync(func, *args):
    """Executa funcao sincrona em thread pool."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description="Servidor de captura de ficha CIP")
    parser.add_argument("--porta", type=int, default=8000, help="Porta do servidor (padrao: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (padrao: 0.0.0.0)")
    args = parser.parse_args()

    ip = obter_ip_local()

    # Criar diretorios
    DATA_DIR.mkdir(exist_ok=True)
    FILA_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)

    global SERVER_URL
    SERVER_URL = f"http://{ip}:{args.porta}"

    print(f"\n  === Catalogacao por Foto ===")
    print(f"  No celular, acesse: {SERVER_URL}")
    print(f"  Para parar: Ctrl+C\n")

    uvicorn.run(app, host=args.host, port=args.porta)


if __name__ == "__main__":
    main()
