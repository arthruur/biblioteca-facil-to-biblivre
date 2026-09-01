"""
Servidor web para captura de ficha CIP via câmera do celular.

Roda um FastAPI que:
  1. Serve a página HTML com acesso à câmera
  2. Recebe a foto capturada
  3. Roda detecção + OCR + extração de ISBN
  4. Retorna os campos extraídos

Uso:
  python scripts/servidor.py                    # inicia em https://0.0.0.0:8000
  python scripts/servidor.py --porta 9000       # porta alternativa
  python scripts/servidor.py --sem-ssl          # HTTP (só funciona em localhost)

Acessa no celular: https://IP-DO-PC:8000
"""

import argparse
import json
import socket
import ssl
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Importar funções dos scripts locais
sys.path.insert(0, str(Path(__file__).parent))
from detectar_ficha import binarizar, encontrar_ficha, nitidez, preparar_para_ocr
from extrair_isbn import extrair_isbn_do_texto

# --- Configuração ---
DATA_DIR = Path(__file__).parent.parent / "data"
FILA_DIR = DATA_DIR / "fila"
STATIC_DIR = Path(__file__).parent.parent / "static"
CERT_DIR = DATA_DIR / "certs"

app = FastAPI(title="Catalogacao por Foto")

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
    """Serve a página principal."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Arquivo static/index.html não encontrado</h1>")


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
    """Executa função síncrona em thread pool."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# --- Main ---

def gerar_certificado():
    """Gera certificado autoassinado para HTTPS."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert_path = CERT_DIR / "cert.pem"
    key_path = CERT_DIR / "key.pem"

    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    # Gerar com openssl (se disponível) ou com Python
    try:
        import subprocess
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "365", "-nodes",
            "-subj", "/CN=localhost"
        ], check=True, capture_output=True)
        print(f"Certificado gerado em: {CERT_DIR}")
        return str(cert_path), str(key_path)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Fallback: gerar com Python
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    print(f"Certificado gerado em: {CERT_DIR}")
    return str(cert_path), str(key_path)


def main():
    parser = argparse.ArgumentParser(description="Servidor de captura de ficha CIP")
    parser.add_argument("--porta", type=int, default=8000, help="Porta do servidor (padrão: 8000)")
    parser.add_argument("--sem-ssl", action="store_true", help="Rodar sem HTTPS (só localhost)")
    args = parser.parse_args()

    ip = obter_ip_local()

    # Criar diretórios
    DATA_DIR.mkdir(exist_ok=True)
    FILA_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)

    if args.sem_ssl:
        print(f"\n  Rodando em HTTP (só localhost)")
        print(f"  Acesse: http://localhost:{args.porta}\n")
        uvicorn.run(app, host="127.0.0.1", port=args.porta)
    else:
        cert_path, key_path = gerar_certificado()
        print(f"\n  === Catalogacao por Foto ===")
        print(f"  Rodando em HTTPS")
        print(f"  No celular, acesse: https://{ip}:{args.porta}")
        print(f"  (Aceite o aviso do certificado autoassinado)")
        print(f"  Para parar: Ctrl+C\n")

        # Configurar SSL
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(cert_path, key_path)

        uvicorn.run(app, host="0.0.0.0", port=args.porta, ssl_certfile=cert_path, ssl_keyfile=key_path)


if __name__ == "__main__":
    main()
