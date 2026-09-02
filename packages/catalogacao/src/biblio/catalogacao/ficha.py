"""Pipeline de ficha CIP: deteccao + OCR + extracao de ISBN/CDD/Cutter."""

import tempfile
from pathlib import Path

import cv2
import numpy as np

from .config import aplicar_tesseract
from .deteccao import encontrar_ficha, nitidez, preparar_para_ocr
from .isbn import extrair_isbn_do_texto


def processar_foto(bytes_foto: bytes) -> dict:
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
        from PIL import Image

        aplicar_tesseract(pytesseract)
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

    resultado: dict = {
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
