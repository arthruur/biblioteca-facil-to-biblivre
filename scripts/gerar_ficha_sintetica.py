"""
Gera uma imagem sintética de ficha CIP para testar o detector.

Cria uma página com um retângulo Proporção ~1,67 (ficha ABNT) contendo
texto simulado de ficha catalográfica, plus ruído de fundo.

Uso:
  python scripts/gerar_ficha_sintetica.py              # gera data/teste/ficha_sintetica.png
  python scripts/gerar_ficha_sintetica.py --out img.png
"""

import argparse
from pathlib import Path

import cv2
import numpy as np


def desenhar_ficha(largura_pagina=1080, altura_pagina=1920):
    """Cria uma imagem de página com ficha CIP sintética."""
    # Fundo da página (branco levemente sujo — simula foto real)
    pagina = np.full((altura_pagina, largura_pagina, 3), 235, dtype=np.uint8)
    ruido = np.random.normal(0, 3, pagina.shape).astype(np.int16)
    pagina = np.clip(pagina.astype(np.int16) + ruido, 0, 255).astype(np.uint8)

    # Dimensões da ficha ABNT: 12,5 × 7,5 cm
    # Na imagem, vamos colocar com tamanho razoável
    w_ficha = int(largura_pagina * 0.6)
    h_ficha = int(w_ficha / (12.5 / 7.5))

    # Posição (ligeiramente descentrada e rotacionada para simular foto real)
    x0 = int(largura_pagina * 0.22)
    y0 = int(altura_pagina * 0.35)

    # Criar a ficha
    ficha = np.full((h_ficha, w_ficha, 3), 255, dtype=np.uint8)

    # Borda da ficha (retangulo duplo — padrao ABNT)
    espessura = 4
    cv2.rectangle(ficha, (6, 6), (w_ficha - 6, h_ficha - 6), (0, 0, 0), espessura)
    cv2.rectangle(ficha, (14, 14), (w_ficha - 14, h_ficha - 14), (0, 0, 0), 2)

    # Texto simulado da ficha CIP
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    cor = (30, 30, 30)
    y = 40
    dy = 32

    linhas = [
        (0.6, 1, "Biblioteca Municipal"),
        (0.55, 1, "Sao Paulo : Editora Exemplo, 2024"),
        (0.55, 1, "123 p. ; 21 cm"),
        (0.0, 0, ""),  # linha em branco
        (0.6, 1, "ISBN 978-65-1234-567-9"),  # digito verificador = 9
        (0.0, 0, ""),
        (0.55, 1, "I. Titulo"),
        (0.0, 0, ""),
        (0.55, 1, "CDD: 020"),
        (0.55, 1, "Cutter: A123"),
    ]

    for escala, esp, texto in linhas:
        if texto:
            cv2.putText(ficha, texto, (20, y), fonte, escala, cor, esp, cv2.LINE_AA)
        y += dy

    # Aplicar rotação leve na ficha (simula foto torta)
    angulo = np.random.uniform(-4, 4)
    centro = (w_ficha // 2, h_ficha // 2)
    M_rot = cv2.getRotationMatrix2D(centro, angulo, 1.0)
    ficha_rot = cv2.warpAffine(ficha, M_rot, (w_ficha, h_ficha),
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))

    # Colocar a ficha na página
    # Garantir que cabe
    y1 = min(y0 + h_ficha, altura_pagina)
    x1 = min(x0 + w_ficha, largura_pagina)
    h_recorte = y1 - y0
    w_recorte = x1 - x0

    roi = pagina[y0:y1, x0:x1]
    ficha_corte = ficha_rot[:h_recorte, :w_recorte]

    # Máscara para colar só a ficha (fundo branco da ficha → transparente)
    mascara = cv2.cvtColor(ficha_corte, cv2.COLOR_BGR2GRAY) < 240
    for c in range(3):
        roi[:, :, c] = np.where(mascara, ficha_corte[:, :, c], roi[:, :, c])

    return pagina


def main():
    parser = argparse.ArgumentParser(description="Gera ficha CIP sintética para teste")
    parser.add_argument("--out", default=None, help="Caminho de saída")
    args = parser.parse_args()

    if args.out:
        saida = Path(args.out)
    else:
        saida = Path("data/teste/ficha_sintetica.png")

    saida.parent.mkdir(parents=True, exist_ok=True)

    imagem = desenhar_ficha()
    cv2.imwrite(str(saida), imagem)
    print(f"Ficha sintetica gerada: {saida}")
    print(f"  Dimensoes: {imagem.shape[1]}x{imagem.shape[0]} px")


if __name__ == "__main__":
    main()
