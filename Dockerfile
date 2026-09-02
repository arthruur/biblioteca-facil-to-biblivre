# syntax=docker/dockerfile:1
#
# Build do frontend (Vite) e runtime Python numa imagem só.
#
# O estágio Node existe apenas para produzir apps/web/dist: a imagem final não
# leva Node nem node_modules, só os arquivos estáticos buildados.

FROM node:22-slim AS web
WORKDIR /build
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Tesseract (OCR da ficha CIP, para livro sem código de barras) + as
# dependências nativas do OpenCV. O idioma português já entra na imagem: não
# há download em runtime numa biblioteca com internet ruim.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-por \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# O código vem antes do install porque os pacotes são instalados em modo
# editável — o instalador precisa enxergar os src/ para montar o mapeamento do
# namespace `biblio`. O cache de wheels do pip fica num mount, então mudar
# código não obriga a rebaixar opencv e pandas de novo.
COPY requirements.txt ./
COPY packages/ packages/
COPY apps/api/ apps/api/
COPY scripts/ scripts/
COPY docs/ docs/
COPY --from=web /build/dist apps/web/dist

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

ENV TESSERACT_CMD=/usr/bin/tesseract \
    BIBLIO_DATA_DIR=/app/data \
    BIBLIO_WEB_DIST=/app/apps/web/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,ssl; ctx=ssl._create_unverified_context(); \
        urllib.request.urlopen('https://localhost:8000/api/saude', context=ctx)" || exit 1

# Gera o certificado autoassinado em data/certs na primeira execução: sem
# HTTPS a câmera do navegador não abre, e sem câmera não há scanner.
CMD ["biblio-servidor", "--host", "0.0.0.0", "--porta", "8000"]
