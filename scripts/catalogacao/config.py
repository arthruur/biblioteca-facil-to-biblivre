"""Caminhos e estado compartilhado do servidor."""

import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FILA_DIR = DATA_DIR / "fila"
STATIC_DIR = ROOT / "static"
CERT_DIR = DATA_DIR / "certs"

# Preenchido em runtime por servidor.main()
SERVER_URL: str = ""

fila_lock = threading.Lock()
fila: list[dict] = []

# Carrinho em memoria (Fase de Captura) — acumula ISBNs antes do envio
carrinho_lock = threading.Lock()
carrinho: list[dict] = []  # cada item: {isbn, titulo, autor, ...}
