# MVP Catalogação ISBN — FastAPI + OpenCV + Tesseract
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Tesseract + por + OpenCV deps (libgl, libglib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-por \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Tesseract no Linux fica em /usr/bin/tesseract — ajusta fallback se não achar o path Windows
ENV TESSERACT_CMD=/usr/bin/tesseract

EXPOSE 8000

# Gera cert auto-assinado em data/certs na primeira execução
CMD ["python", "scripts/servidor.py", "--host", "0.0.0.0", "--porta", "8000"]
