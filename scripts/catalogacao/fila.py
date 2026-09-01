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
        "quantidade": int(dados.get("quantidade") or dados.get("exemplares") or 1),
        "exemplares": int(dados.get("quantidade") or dados.get("exemplares") or 1),
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


# --- Lote (alias carrinho): acumula ISBNs; mesmo ISBN soma exemplares ---

def carrinho_adicionar(isbn: str) -> dict:
    """Adiciona ISBN ao lote. Se ja existe, incrementa quantidade (exemplares)."""
    limpo = isbn.replace("-", "").replace(" ", "").strip()
    with carrinho_lock:
        for item in carrinho:
            if item.get("isbn") == limpo:
                item["quantidade"] = int(item.get("quantidade") or 1) + 1
                item["exemplares"] = item["quantidade"]
                return {"status": "incrementado", "isbn": limpo, "item": item, "total": len(carrinho), "quantidade": item["quantidade"]}
        dados = buscar_metadados(limpo)
        entry = {"isbn": limpo, **dados, "quantidade": 1, "exemplares": 1, "adicionado_em": datetime.now().isoformat()}
        carrinho.append(entry)
        return {"status": "ok", "item": entry, "total": len(carrinho)}


def carrinho_listar() -> dict:
    with carrinho_lock:
        return {"itens": list(carrinho), "total": len(carrinho)}


def carrinho_atualizar_quantidade(isbn: str, quantidade: int) -> dict:
    limpo = isbn.replace("-", "").strip()
    q = max(1, int(quantidade))
    with carrinho_lock:
        for item in carrinho:
            if item.get("isbn") == limpo:
                item["quantidade"] = q
                item["exemplares"] = q
                return {"status": "ok", "isbn": limpo, "quantidade": q, "item": item}
        return {"status": "nao_encontrado", "isbn": limpo}


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
