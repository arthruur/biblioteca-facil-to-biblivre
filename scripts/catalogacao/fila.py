"""Fila de revisao (pos-catalogacao) e carrinho (pre-envio)."""

import json
from datetime import datetime

from .config import FILA_DIR, carrinho, carrinho_lock, fila, fila_lock
from .lookup import buscar_metadados


# --- Fila ---

def adicionar_fila(dados: dict) -> dict:
    item = {
        "timestamp": datetime.now().isoformat(),
        "isbn": dados.get("isbn"),
        "titulo": dados.get("titulo", ""),
        "autor": dados.get("autor", ""),
        "editora": dados.get("editora", ""),
        "ano": dados.get("ano", ""),
        "cdd": dados.get("cdd", ""),
        "cutter": dados.get("cutter", ""),
        "confirmado": True,
    }
    with fila_lock:
        fila.append(item)
    FILA_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = FILA_DIR / f"fila_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    arquivo.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


def listar_fila() -> dict:
    with fila_lock:
        return {"itens": list(fila), "total": len(fila)}


# --- Carrinho: acumula ISBNs antes do envio (padrao scanner de documentos) ---

def carrinho_adicionar(isbn: str) -> dict:
    """Adiciona ISBN ao carrinho com deduplicacao. Faz lookup imediato."""
    limpo = isbn.replace("-", "").replace(" ", "").strip()
    with carrinho_lock:
        for item in carrinho:
            if item.get("isbn") == limpo:
                return {"status": "duplicado", "isbn": limpo, "mensagem": "Ja no carrinho"}
        dados = buscar_metadados(limpo)
        # Normaliza: mesmo se nao_encontrado, guarda para revisao
        entry = {"isbn": limpo, **dados, "adicionado_em": datetime.now().isoformat()}
        carrinho.append(entry)
        return {"status": "ok", "item": entry, "total": len(carrinho)}


def carrinho_listar() -> dict:
    with carrinho_lock:
        return {"itens": list(carrinho), "total": len(carrinho)}


def carrinho_remover(isbn: str) -> dict:
    limpo = isbn.replace("-", "").strip()
    with carrinho_lock:
        antes = len(carrinho)
        carrinho[:] = [x for x in carrinho if x.get("isbn") != limpo]
        if len(carrinho) == antes:
            return {"status": "nao_encontrado", "isbn": limpo}
        return {"status": "ok", "total": len(carrinho)}


def carrinho_limpar() -> dict:
    with carrinho_lock:
        carrinho.clear()
        return {"status": "ok", "total": 0}


def carrinho_enviar() -> dict:
    """Move todo o carrinho para a fila e limpa o carrinho. Retorna enviados."""
    with carrinho_lock:
        if not carrinho:
            return {"status": "vazio", "enviados": 0}
        itens = list(carrinho)
        carrinho.clear()
    enviados = []
    for dados in itens:
        enviados.append(adicionar_fila(dados))
    return {"status": "ok", "enviados": len(enviados), "itens": enviados}
