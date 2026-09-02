"""Caminhos, estado compartilhado e localização do Tesseract."""

import os
import shutil
import threading
from pathlib import Path

# A raiz do repositório: .../packages/catalogacao/src/biblio/catalogacao/config.py
ROOT = Path(__file__).resolve().parents[5]
DATA_DIR = Path(os.environ.get("BIBLIO_DATA_DIR") or (ROOT / "data"))
FILA_DIR = DATA_DIR / "fila"
EXPORT_DIR = DATA_DIR / "export"
CERT_DIR = DATA_DIR / "certs"

# Preenchido em runtime por quem sobe o servidor (usado no QR code da tela).
SERVER_URL: str = ""

fila_lock = threading.Lock()
fila: list[dict] = []

# O lote NAO mora aqui: virou um por aparelho, em `lotes.py`. Deixar a lista
# global de pe so criaria a armadilha de alguem dar append nela e a tela nao
# mostrar nada.


def garantir_pastas() -> None:
    for pasta in (DATA_DIR, FILA_DIR, EXPORT_DIR, CERT_DIR):
        pasta.mkdir(parents=True, exist_ok=True)


def tesseract_cmd() -> str | None:
    """
    Onde está o binário do Tesseract.

    O container define `TESSERACT_CMD=/usr/bin/tesseract`; no Windows o
    instalador padrão não põe o executável no PATH, daí o caminho fixo como
    último recurso. Devolve None quando não achou — quem chama transforma isso
    em mensagem de erro na tela, em vez de estourar dentro do pytesseract.
    """
    do_ambiente = os.environ.get("TESSERACT_CMD")
    if do_ambiente and Path(do_ambiente).exists():
        return do_ambiente

    no_path = shutil.which("tesseract")
    if no_path:
        return no_path

    padrao_windows = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if padrao_windows.exists():
        return str(padrao_windows)
    return None


def aplicar_tesseract(pytesseract) -> str:
    """Aponta o pytesseract para o binário achado. Levanta se não houver."""
    caminho = tesseract_cmd()
    if not caminho:
        raise RuntimeError(
            "Tesseract não encontrado. Instale o tesseract-ocr (com o idioma "
            "'por') ou aponte TESSERACT_CMD para o executável.")
    pytesseract.pytesseract.tesseract_cmd = caminho
    return caminho


# --- Conexao com o BibLivre ---
# Mora em biblio.biblivre.conexao: e o mesmo estado que os CLIs de migracao
# usam, e ter duas copias da credencial seria pedir divergencia. Reexportado
# aqui porque as telas e as rotas ja falavam com `config`.

from biblio.biblivre.conexao import (  # noqa: E402
    db_config,
    definir_db,
    sem_senha,
)

__all__ = [
    "ROOT", "DATA_DIR", "FILA_DIR", "EXPORT_DIR", "CERT_DIR", "SERVER_URL",
    "fila", "fila_lock", "garantir_pastas",
    "tesseract_cmd", "aplicar_tesseract", "db_config", "definir_db", "sem_senha",
]
