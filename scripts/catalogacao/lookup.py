"""Lookup de metadados por ISBN: Google Books + BrasilAPI (CBL) + Open Library."""

import json
import urllib.request


def buscar_google_books(isbn: str) -> dict | None:
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.loads(resp.read().decode())
            if dados.get("totalItems", 0) == 0:
                return None
            vol = dados["items"][0]["volumeInfo"]
            autores = vol.get("authors", [])
            return {
                "titulo": vol.get("title", ""),
                "subtitulo": vol.get("subtitle", ""),
                "autor": ", ".join(autores),
                "editora": vol.get("publisher", ""),
                "ano": str(vol.get("publishedDate", ""))[:4],
                "edicao": vol.get("edition", ""),
                "paginas": str(vol.get("pageCount", "")),
                "idioma": vol.get("language", ""),
                "descricao": vol.get("description", "")[:500],
                "capa": vol.get("imageLinks", {}).get("thumbnail", ""),
                "fonte": "Google Books",
            }
    except Exception:
        return None


def buscar_brasilapi(isbn: str) -> dict | None:
    """BrasilAPI — base CBL, essencial para ISBNs brasileiros 97865* (ex: 9786559870530)."""
    url = f"https://brasilapi.com.br/api/isbn/v1/{isbn}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
            if not d.get("title"):
                return None
            autores = d.get("authors") or []
            return {
                "titulo": d.get("title", ""),
                "subtitulo": d.get("subtitle", ""),
                "autor": ", ".join(autores),
                "editora": d.get("publisher", ""),
                "ano": str(d.get("year") or "")[:4],
                "edicao": "",
                "paginas": str(d.get("page_count") or ""),
                "idioma": "por",
                "descricao": (d.get("synopsis") or "")[:500],
                "capa": d.get("cover_url") or f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
                "fonte": "BrasilAPI/CBL",
            }
    except Exception:
        return None


def buscar_open_library(isbn: str) -> dict | None:
    url = f"https://openlibrary.org/isbn/{isbn}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.loads(resp.read().decode())
            titulo = dados.get("title", "")
            autores_keys = dados.get("authors", [])
            autores: list[str] = []
            for a in autores_keys:
                if isinstance(a, dict) and "key" in a:
                    try:
                        a_url = f"https://openlibrary.org{a['key']}.json"
                        a_req = urllib.request.Request(a_url, headers={"User-Agent": "CatalogacaoBiblioteca/1.0"})
                        with urllib.request.urlopen(a_req, timeout=5) as a_resp:
                            a_dados = json.loads(a_resp.read().decode())
                            autores.append(a_dados.get("name", ""))
                    except Exception:
                        autores.append("")
                elif isinstance(a, str):
                    autores.append(a)
            return {
                "titulo": titulo,
                "subtitulo": "",
                "autor": ", ".join(autores),
                "editora": dados.get("publishers", [""])[0] if dados.get("publishers") else "",
                "ano": str(dados.get("publish_date", ""))[:4],
                "edicao": "",
                "paginas": "",
                "idioma": dados.get("languages", [{}])[0].get("key", "").replace("/languages/", "") if dados.get("languages") else "",
                "descricao": "",
                "capa": f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
                "fonte": "Open Library",
            }
    except Exception:
        return None


def buscar_metadados(isbn: str) -> dict:
    for fn in (buscar_google_books, buscar_brasilapi, buscar_open_library):
        r = fn(isbn)
        if r:
            return {"status": "ok", "isbn": isbn, **r}
    return {
        "status": "nao_encontrado",
        "isbn": isbn,
        "titulo": "",
        "autor": "",
        "editora": "",
        "ano": "",
        "mensagem": f"ISBN {isbn} nao encontrado nas APIs externas",
    }
