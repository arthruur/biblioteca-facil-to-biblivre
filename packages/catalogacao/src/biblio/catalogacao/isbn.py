"""
Extrai e valida ISBN a partir de texto OCR de ficha CIP.

Uso:
  python scripts/extrair_isbn.py "ISBN 978-65-1234-567-8"
  python scripts/extrair_isbn.py --arquivo data/teste/ficha_sintetica_ficha.png
"""

import argparse
import re
import sys

import cv2
import pytesseract

from .config import aplicar_tesseract


def limpar_isbn(texto: str) -> str:
    """Remove espacos, hifens e pontuacao de um ISBN."""
    return re.sub(r"[\s\-\.]", "", texto)


def validar_isbn13(isbn: str) -> bool:
    """
    Valida ISBN-13 com dígito verificador.
    Algoritmo: soma ponderada com pesos 1,3,1,3,... mod 10.
    """
    if len(isbn) != 13 or not isbn.isdigit():
        return False
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn))
    return soma % 10 == 0


def validar_isbn10(isbn: str) -> bool:
    """
    Valida ISBN-10 com dígito verificador.
    O ultimo digito pode ser X (equivale a 10).
    Algoritmo: soma ponderada com pesos 10,9,8,...,1 mod 11.
    """
    if len(isbn) != 10:
        return False
    if not isbn[:9].isdigit():
        return False
    ultimo = 10 if isbn[9].upper() == "X" else int(isbn[9])
    if ultimo is False:
        return False
    soma = sum(int(isbn[i]) * (10 - i) for i in range(9)) + ultimo
    return soma % 11 == 0


def extrair_isbn_do_texto(texto: str) -> list[dict]:
    """
    Busca ISBNs no texto OCR.
    Retorna lista de {'isbn': str, 'tipo': '13'|'10', 'valido': bool}.
    """
    # Padrões para ISBN-13 e ISBN-10
    padroes = [
        # ISBN-13: 13 dígitos (com ou sem hífens)
        r"ISBN[\s:\-]*([\d\-]{13,17})",
        # ISBN-10: 10 dígitos (com ou sem hifens, ultimo pode ser X)
        r"ISBN[\s:\-]*([\d\-]{10,14}[Xx]?)",
        # Sem prefixo ISBN — 13 dígitos contíguos começando com 978 ou 979
        r"\b(97[89][\d\-]{10,14})\b",
        # Sem prefixo ISBN — 10 dígitos (com hifens)
        r"\b([\d]{1,5}\-[\d]{1,5}\-[\d]{1,5}[\dXx])\b",
    ]

    encontrados = []
    vistos = set()

    for padrao in padroes:
        for m in re.finditer(padrao, texto, re.IGNORECASE):
            bruto = m.group(1)
            limpo = limpar_isbn(bruto)

            if limpo in vistos:
                continue
            vistos.add(limpo)

            if len(limpo) == 13 and limpo.isdigit():
                valido = validar_isbn13(limpo)
                encontrados.append({"isbn": limpo, "tipo": "13", "valido": valido})
            elif len(limpo) == 10:
                valido = validar_isbn10(limpo)
                encontrados.append({"isbn": limpo, "tipo": "10", "valido": valido})

    return encontrados


def extrair_da_imagem(caminho_imagem: str) -> str:
    """Roda OCR na imagem e retorna o texto bruto."""
    img = cv2.imread(caminho_imagem)
    if img is None:
        print(f"Nao foi possivel ler: {caminho_imagem}", file=sys.stderr)
        sys.exit(1)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    h, w = gray.shape
    # Upscale 3x para OCR
    up = cv2.resize(gray, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

    aplicar_tesseract(pytesseract)
    return pytesseract.image_to_string(up, lang="por", config="--psm 6")
