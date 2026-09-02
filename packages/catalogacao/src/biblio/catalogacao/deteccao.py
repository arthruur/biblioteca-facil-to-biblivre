"""
Detecta e retifica a caixa da ficha CIP a partir de uma foto de celular.

Pipeline (conforme CATALOGACAO_POR_FOTO.md):
  grayscale → blur → Canny → findContours → maior quadrilátero (razão ~1.67)
  → getPerspectiveTransform + warpPerspective → threshold adaptativo

Uso:
  python scripts/detectar_ficha.py foto.jpg
  python scripts/detectar_ficha.py foto.jpg --debug          # salva etapas intermediárias
  python scripts/detectar_ficha.py foto.jpg --out ficha.png  # caminho de saída
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


# Proporção esperada da ficha ABNT: ~12,5 × 7,5 cm → 1,666...
RAZAO_ESPERADA = 12.5 / 7.5
TOLERANCIA_RAZAO = 0.25  # aceita entre ~1,25 e ~2,08


def nitidez(image: np.ndarray) -> float:
    """Variância do Laplaciano — quanto maior, mais nítida a imagem."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def ordenar_pontos(pontos: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos no padrão: top-left, top-right, bottom-right, bottom-left."""
    ret = np.zeros((4, 2), dtype="float32")
    s = pontos.sum(axis=1)
    d = np.diff(pontos, axis=1)
    ret[0] = pontos[np.argmin(s)]   # top-left
    ret[2] = pontos[np.argmax(s)]   # bottom-right
    ret[1] = pontos[np.argmin(d)]   # top-right
    ret[3] = pontos[np.argmax(d)]   # bottom-left
    return ret


def encontrar_ficha(image: np.ndarray):
    """
    Procura o maior quadrilatero com proporcao proxima a RAZAO_ESPERADA.
    Tenta dois metodos:
      1. Deteccao por borda (Canny + contornos)
      2. Deteccao por regiao branca (threshold + contornos)
    Retorna (contorno, warp) ou (None, None) se nao encontrar.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # --- Metodo 1: Deteccao por borda ---
    edged = cv2.Canny(blurred, 30, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.dilate(edged, kernel, iterations=2)
    edged = cv2.erode(edged, kernel, iterations=1)

    contorno, warp = _buscar_quadrilatero(edged, image)
    if contorno is not None:
        return contorno, warp

    # --- Metodo 2: Deteccao por regiao branca ---
    # A ficha CIP tem fundo branco; a pagina de fundo e levemente cinza
    # Threshold binario invertido: branco = 255, resto = 0
    _, thresh = cv2.threshold(blurred, 220, 255, cv2.THRESH_BINARY)
    # Fechamento para preencher o texto dentro da ficha
    kernel_grande = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_grande)

    contorno, warp = _buscar_quadrilatero(thresh, image)
    return contorno, warp


def _buscar_quadrilatero(edge_map: np.ndarray, original: np.ndarray):
    """Busca o maior quadrilatero com proporcao valida num edge/thresh map."""
    contours, _ = cv2.findContours(edge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:30]

    h_img, w_img = edge_map.shape[:2]
    area_min = h_img * w_img * 0.05

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) != 4:
            continue

        pontos = ordenar_pontos(approx.reshape(4, 2).astype("float32"))
        w = np.linalg.norm(pontos[0] - pontos[1])
        h = np.linalg.norm(pontos[0] - pontos[3])

        if w * h < area_min:
            continue

        razao = max(w, h) / min(w, h)
        if abs(razao - RAZAO_ESPERADA) > TOLERANCIA_RAZAO:
            continue

        # Encontrou — retifica
        dst = np.array([
            [0, 0],
            [int(max(w, h)), 0],
            [int(max(w, h)), int(min(w, h))],
            [0, int(min(w, h))],
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(pontos, dst)
        warp = cv2.warpPerspective(original, M, (int(max(w, h)), int(min(w, h))))

        return cnt, warp

    return None, None


def binarizar(warp: np.ndarray) -> np.ndarray:
    """Threshold adaptativo para binarizar a ficha retificada."""
    gray = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY) if len(warp.shape) == 3 else warp
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )


def preparar_para_ocr(warp: np.ndarray) -> np.ndarray:
    """
    Prepara a ficha retificada para OCR:
    1. Converte para cinza
    2. Upscale 2x (Tesseract precisa de ~300 DPI equivalente)
    3. Binariza com threshold adaptativo
    """
    gray = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY) if len(warp.shape) == 3 else warp
    h, w = gray.shape
    # Upscale 2x para melhorar acurácia do OCR
    upscale = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    binarizada = cv2.adaptiveThreshold(
        upscale, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    return binarizada


def salvar_debug(base_path: Path, original, cinza, edged, contorno_ficha, warp, binarizada):
    """Salva imagens intermediárias para debug visual."""
    cv2.imwrite(str(base_path / "01_cinza.png"), cinza)
    cv2.imwrite(str(base_path / "02_canny.png"), edged)

    com_contorno = original.copy()
    if contorno_ficha is not None:
        cv2.drawContours(com_contorno, [contorno_ficha], -1, (0, 255, 0), 3)
    cv2.imwrite(str(base_path / "03_contorno.png"), com_contorno)

    if warp is not None:
        cv2.imwrite(str(base_path / "04_retificada.png"), warp)
    if binarizada is not None:
        cv2.imwrite(str(base_path / "05_binarizada.png"), binarizada)
