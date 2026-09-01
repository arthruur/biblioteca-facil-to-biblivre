"""
Servidor web para catalogacao de livros via codigo de barras ISBN.

Roda um FastAPI que:
  1. Serve a pagina HTML com scanner de codigo de barras em tempo real
  2. Recebe o ISBN decodificado pelo navegador
  3. Consulta APIs externas (Google Books / Open Library)
  4. Retorna metadados completos do livro

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
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Importar funcoes dos scripts locais
sys.path.insert(0, str(Path(__file__).parent))
from detectar_ficha import binarizar, encontrar_ficha, nitidez, preparar_para_ocr
from extrair_isbn import extrair_isbn_do_texto

# --- Configuracao ---
DATA_DIR = Path(__file__).parent.parent / "data"
FILA_DIR = DATA_DIR / "fila"
STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Catalogacao ISBN")

# URL do servidor (preenchida ao iniciar)
SERVER_URL = ""

# Estado em memoria: fila de itens capturados
fila_lock = threading.Lock()
fila: list[dict] = []


def obter_ip_local() -> str:
    """Descobre o IP local da maquina na rede."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# --- Lookup de metadados via API externa ---

def buscar_google_books(isbn: str) -> dict | None:
    """Consulta Google Books API pelo ISBN. Retorna dict ou None."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.loads(resp.read().decode())
            if dados.get("totalItems", 0) == 0:
                return None
            vol = dados["items"][0]["volumeInfo"]
            autores = vol.get("authors", [])
            return {
                "titulo": vol.get("title", ""),
                "subtitulo": vol.get("subtitle", ""),
                "autor": ", ".join(autores),
                "editora": vol.get("publisher", ""),
                "ano": str(vol.get("publishedDate", ""))[:4],
                "edicao": vol.get("edition", ""),
                "paginas": str(vol.get("pageCount", "")),
                "idioma": vol.get("language", ""),
                "descricao": vol.get("description", "")[:500],
                "capa": vol.get("imageLinks", {}).get("thumbnail", ""),
                "fonte": "Google Books",
            }
    except Exception:
        return None


def buscar_open_library(isbn: str) -> dict | None:
    """Consulta Open Library API pelo ISBN. Retorna dict ou None."""
    url = f"https://openlibrary.org/isbn/{isbn}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.loads(resp.read().decode())
            titulo = dados.get("title", "")
            autores_keys = dados.get("authors", [])
            autores = []
            for a in autores_keys:
                if isinstance(a, dict) and "key" in a:
                    # Buscar nome do autor
                    try:
                        a_url = f"https://openlibrary.org{a['key']}.json"
                        a_req = urllib.request.Request(a_url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
                        with urllib.request.urlopen(a_req, timeout=5) as a_resp:
                            a_dados = json.loads(a_resp.read().decode())
                            autores.append(a_dados.get("name", ""))
                    except Exception:
                        autores.append("")
                elif isinstance(a, str):
                    autores.append(a)

            return {
                "titulo": titulo,
                "subtitulo": "",
                "autor": ", ".join(autores),
                "editora": dados.get("publishers", [""])[0] if dados.get("publishers") else "",
                "ano": str(dados.get("publish_date", ""))[:4],
                "edicao": "",
                "paginas": "",
                "idioma": dados.get("languages", [{}])[0].get("key", "").replace("/languages/", "") if dados.get("languages") else "",
                "descricao": "",
                "capa": f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
                "fonte": "Open Library",
            }
    except Exception:
        return None


def buscar_metadados(isbn: str) -> dict:
    """
    Busca metadados do livro pelo ISBN.
    Tenta Google Books primeiro, depois Open Library como fallback.
    """
    # Tentar Google Books
    resultado = buscar_google_books(isbn)
    if resultado:
        return {"status": "ok", "isbn": isbn, **resultado}

    # Fallback: Open Library
    resultado = buscar_open_library(isbn)
    if resultado:
        return {"status": "ok", "isbn": isbn, **resultado}

    # Nenhuma API encontrou
    return {
        "status": "nao_encontrado",
        "isbn": isbn,
        "titulo": "",
        "autor": "",
        "editora": "",
        "ano": "",
        "mensagem": f"ISBN {isbn} nao encontrado nas APIs externas",
    }


# --- Pipeline de processamento de foto (ficha CIP) ---

def processar_foto(bytes_foto: bytes) -> dict:
    """Pipeline completo: bytes -> OpenCV -> deteccao -> OCR -> extracao."""
    arr = np.frombuffer(bytes_foto, dtype=np.uint8)
    original = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if original is None:
        return {"status": "erro", "mensagem": "Nao foi possivel ler a imagem"}

    niv = nitidez(original)
    if niv < 30:
        return {"status": "erro", "mensagem": f"Imagem borrada (nitidez: {niv:.0f}). Segure firme."}

    contorno, warp = encontrar_ficha(original)
    if contorno is None:
        return {"status": "erro", "mensagem": "Ficha CIP nao detectada. Aponte para a ficha."}

    ocr_img = preparar_para_ocr(warp)

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

    isbn_encontrados = extrair_isbn_do_texto(texto_ocr)

    cdd = ""
    cutter = ""
    for linha in texto_ocr.split("\n"):
        linha = linha.strip()
        if linha.upper().startswith("CDD"):
            cdd = linha.split(":", 1)[-1].strip() if ":" in linha else ""
        elif linha.upper().startswith("CUTTER"):
            cutter = linha.split(":", 1)[-1].strip() if ":" in linha else ""

    resultado = {
        "status": "ok",
        "texto_ocr": texto_ocr.strip(),
        "cdd": cdd,
        "cutter": cutter,
        "isbn": None,
        "isbn_valido": None,
    }

    if isbn_encontrados:
        valido = [i for i in isbn_encontrados if i["valido"]]
        isbn = valido[0] if valido else isbn_encontrados[0]
        resultado["isbn"] = isbn["isbn"]
        resultado["isbn_valido"] = isbn["valido"]

    return resultado


# --- Rotas ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve a pagina principal com a URL do servidor embutida."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
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


@app.get("/api/lookup/{isbn}")
async def lookup(isbn: str):
    """Consulta metadados do livro pelo ISBN."""
    resultado = await asyncio_to_sync(buscar_metadados, isbn)
    return JSONResponse(resultado)


@app.post("/api/capturar")
async def capturar(foto: UploadFile = File(...)):
    """Recebe foto, processa e retorna campos extraidos (ficha CIP)."""
    bytes_foto = await foto.read()
    resultado = await asyncio_to_sync(processar_foto, bytes_foto)
    return JSONResponse(resultado)


@app.post("/api/confirmar")
async def confirmar(dados: dict):
    """Salva item confirmado na fila de revisao."""
    item = {
        "timestamp": datetime.now().isoformat(),
        "isbn": dados.get("isbn"),
        "titulo": dados.get("titulo", ""),
        "autor": dados.get("autor", ""),
        "editora": dados.get("editora", ""),
        "ano": dados.get("ano", ""),
        "cdd": dados.get("cdd", ""),
        "cutter": dados.get("cutter", ""),
        "confirmado": True,
    }

    with fila_lock:
        fila.append(item)

    FILA_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = FILA_DIR / f"fila_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    arquivo.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "ok", "mensagem": "Salvo na fila de revisao"}


@app.get("/api/fila")
async def listar_fila():
    """Lista itens na fila (para revisao futura)."""
    with fila_lock:
        return {"itens": fila, "total": len(fila)}


async def asyncio_to_sync(func, *args):
    """Executa funcao sincrona em thread pool."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Servidor de catalogacao por ISBN")
    parser.add_argument("--porta", type=int, default=8000, help="Porta do servidor (padrao: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (padrao: 0.0.0.0)")
    args = parser.parse_args()

    ip = obter_ip_local()

    DATA_DIR.mkdir(exist_ok=True)
    FILA_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)

    global SERVER_URL
    SERVER_URL = f"http://{ip}:{args.porta}"

    print(f"\n  === Catalogacao ISBN ===")
    print(f"  No celular, acesse: {SERVER_URL}")
    print(f"  Para parar: Ctrl+C\n")

    uvicorn.run(app, host=args.host, port=args.porta)


if __name__ == "__main__":
    main()
