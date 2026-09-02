"""
Consulta ao acervo ja existente no BibLivre 5: **este ISBN ja esta catalogado?**

Se estiver, o livro escaneado nao vira registro bibliografico novo — vira
exemplar a mais do registro que ja existe.

Por que um indice em memoria e nao um SELECT por ISBN
-----------------------------------------------------
O ISBN mora dentro do `iso2709` (campo 020 $a), que e um blob MARC em `text`.
Nao ha coluna nem indice para ele: qualquer busca e varredura da tabela inteira.
Com ~15 mil registros isso custa alguns segundos — inaceitavel a cada bipe do
scanner. Entao varremos **uma vez**, montamos `{isbn -> registro}` em memoria e
reusamos. O indice se invalida sozinho por TTL e explicitamente apos cada
insercao (`invalidar()`).

O casamento e por ISBN normalizado, com equivalencia ISBN-10 <-> ISBN-13: um
livro gravado em 1998 com ISBN-10 casa com o codigo de barras EAN-13 de hoje.
"""

import os
import re
import threading
import time

from . import exemplares as _exemplares
from . import marc as _marc
from .conexao import conectar, db_config, testar_conexao  # noqa: F401  (reexport)

# TTL do indice. Curto o bastante para refletir edicoes feitas pela tela do
# BibLivre durante a sessao, longo o bastante para o scanner nao pagar a
# varredura a cada bipe.
TTL_SEGUNDOS = 300

_lock = threading.Lock()
_indice: dict[str, dict] | None = None
_indice_em: float = 0.0
_ultimo_erro: str = ""


# --- normalizacao de ISBN ---

def _digitos(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def _dv10(nove: str) -> str:
    s = sum((10 - i) * int(d) for i, d in enumerate(nove))
    r = (11 - s % 11) % 11
    return "X" if r == 10 else str(r)


def _dv13(doze: str) -> str:
    s = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(doze))
    return str((10 - s % 10) % 10)


def variantes(isbn: str) -> set[str]:
    """Todas as formas equivalentes de um ISBN (10 e 13), para casar os dois."""
    d = _digitos(isbn)
    saida = set()
    if len(d) == 10:
        saida.add(d)
        corpo = "978" + d[:9]
        saida.add(corpo + _dv13(corpo))
    elif len(d) == 13:
        saida.add(d)
        if d.startswith("978"):
            nove = d[3:12]
            saida.add(nove + _dv10(nove))
    elif d:
        saida.add(d)
    return saida


# --- indice ISBN -> registro ---

def _varrer(con) -> dict[str, dict]:
    with con.cursor() as cur:
        holdings = _exemplares.contagem_global(cur)
        cur.execute("SELECT id, iso2709 FROM biblio_records WHERE database = 'main'")
        linhas = cur.fetchall()

    indice: dict[str, dict] = {}
    for rec_id, iso in linhas:
        reg = _marc.do_iso2709(iso)
        if reg is None:
            continue
        campos_isbn = [f for f in reg.get_fields("020")]
        if not campos_isbn:
            continue
        titulo = ""
        c245 = reg.get("245")
        if c245 is not None:
            titulo = " ".join(v for v in [c245.get("a"), c245.get("b")] if v).strip(" /:")
        autor = ""
        c100 = reg.get("100")
        if c100 is not None:
            autor = (c100.get("a") or "").strip(" ,.")
        c035 = reg.get("035")
        origem = (c035.get("a") or "") if c035 is not None else ""

        entrada = {
            "record_id": rec_id,
            "titulo": titulo,
            "autor": autor,
            "id_origem": origem,
            "exemplares": holdings.get(rec_id, 0),
        }
        for campo in campos_isbn:
            for bruto in campo.get_subfields("a"):
                for v in variantes(bruto):
                    # Primeiro registro vence: o menor id e o mais antigo, e
                    # ISBN repetido no acervo de origem e conhecido (ver ROADMAP).
                    indice.setdefault(v, entrada)
    return indice


def indice(forcar: bool = False) -> dict[str, dict]:
    """Indice ISBN -> registro, remontado por TTL ou sob demanda."""
    global _indice, _indice_em, _ultimo_erro
    with _lock:
        fresco = _indice is not None and (time.time() - _indice_em) < TTL_SEGUNDOS
        if fresco and not forcar:
            return _indice
        try:
            con = conectar()
        except Exception as e:
            _ultimo_erro = str(e)
            return _indice or {}
        try:
            _indice = _varrer(con)
            _indice_em = time.time()
            _ultimo_erro = ""
        except Exception as e:
            _ultimo_erro = str(e)
        finally:
            try:
                con.close()
            except Exception:
                pass
        return _indice or {}


def invalidar() -> None:
    """Descarta o indice — chamar depois de inserir obras/exemplares."""
    global _indice_em
    with _lock:
        _indice_em = 0.0


def buscar(isbn: str) -> dict | None:
    """Registro ja catalogado com este ISBN, ou None."""
    if not isbn:
        return None
    idx = indice()
    if not idx:
        return None
    for v in variantes(isbn):
        achado = idx.get(v)
        if achado:
            return achado
    return None


def estado() -> dict:
    """Diagnostico para a UI: ha conexao? o indice esta quente? quantos ISBNs?"""
    cfg = db_config()
    return {
        "configurado": bool(cfg.get("senha") or os.environ.get("PGPASSWORD")),
        "host": cfg.get("host"),
        "dbname": cfg.get("dbname"),
        "user": cfg.get("user"),
        "schema": cfg.get("schema"),
        "indexados": len(_indice or {}),
        "indice_em": _indice_em,
        "idade_segundos": round(time.time() - _indice_em) if _indice_em else None,
        "erro": _ultimo_erro,
    }
