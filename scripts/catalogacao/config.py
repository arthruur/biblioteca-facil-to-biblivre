"""Caminhos, credenciais e estado compartilhado do servidor."""

import os
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

# Lote em memoria (Fase de Captura) — acumula ISBNs antes do envio
carrinho_lock = threading.Lock()
carrinho: list[dict] = []  # cada item: {isbn, titulo, autor, ...}

# --- Conexao com o BibLivre ---
# A senha nunca e persistida em disco: entra por variavel de ambiente ao subir
# o servidor ou pela tela (POST /api/db) e vive so na memoria do processo.
_db_lock = threading.Lock()


def _env(*nomes: str, padrao: str = "") -> str:
    """Primeiro nome preenchido vence. Aceita BIBLIVRE_DB_* e os PG* padrao
    (que o docker-compose ja define)."""
    for n in nomes:
        v = os.environ.get(n)
        if v:
            return v
    return padrao


_db: dict = {
    "host": _env("BIBLIVRE_DB_HOST", "PGHOST", padrao="localhost"),
    "port": int(_env("BIBLIVRE_DB_PORT", "PGPORT", padrao="5432")),
    "dbname": _env("BIBLIVRE_DB_NAME", "PGDATABASE", padrao="biblivre4"),
    "user": _env("BIBLIVRE_DB_USER", "PGUSER", padrao="biblivre"),
    "senha": _env("BIBLIVRE_DB_SENHA", "PGPASSWORD"),
    "schema": _env("BIBLIVRE_DB_SCHEMA", padrao="single"),
}


def db_config() -> dict:
    with _db_lock:
        return dict(_db)


def definir_db(novo: dict) -> dict:
    """Atualiza so as chaves informadas; devolve a config sem a senha."""
    with _db_lock:
        for chave in ("host", "dbname", "user", "senha", "schema"):
            if novo.get(chave) is not None and novo.get(chave) != "":
                _db[chave] = novo[chave]
        if novo.get("port"):
            _db["port"] = int(novo["port"])
        return {k: v for k, v in _db.items() if k != "senha"}
