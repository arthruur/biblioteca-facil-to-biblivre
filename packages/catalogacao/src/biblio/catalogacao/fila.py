"""
Lote (pre-envio, em memoria) e Fila de revisao (pos-captura, persistida).

O lote e volatil de proposito: e a bandeja do scanner, esvaziada a cada envio.
A fila e o oposto — e o trabalho pendente do bibliotecario e sobrevive a
reinicio do servidor, entao mora em data/fila/*.json, um arquivo por item,
carregado na subida do processo.

Cada item da fila carrega um status (pendente -> revisado -> exportado, ou
ignorado) e, quando ha banco configurado, um bloco "acervo" dizendo se aquele
ISBN ja existe no BibLivre. Quando existe, o item nao vira registro
bibliografico novo: vira exemplar do registro que ja esta la.
"""

import json
import re
import threading
from datetime import datetime

from biblio.biblivre import acervo as _acervo

from .config import FILA_DIR, carrinho, carrinho_lock, fila, fila_lock
from .lookup import buscar_metadados

STATUS_VALIDOS = ("pendente", "revisado", "exportado", "ignorado")

# Campos que a tela de revisao pode editar
CAMPOS_EDITAVEIS = (
    "titulo", "subtitulo", "autor", "editora", "ano", "edicao", "paginas",
    "idioma", "cdd", "cutter", "localizacao", "notas", "isbn",
)

_id_lock = threading.Lock()


def _normalizar_isbn(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def _novo_id() -> str:
    with _id_lock:
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _arquivo(item_id: str):
    seguro = re.sub(r"[^0-9A-Za-z_-]", "", item_id)
    return FILA_DIR / f"fila_{seguro}.json"


def _gravar(item: dict) -> None:
    FILA_DIR.mkdir(parents=True, exist_ok=True)
    _arquivo(item["id"]).write_text(
        json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")


def _consultar_acervo(isbn: str) -> dict | None:
    """Bloco "acervo" do item — silencioso se nao ha banco configurado."""
    try:
        achado = _acervo.buscar(isbn)
    except Exception:
        return None
    if not achado:
        return None
    return {
        "existe": True,
        "record_id": achado["record_id"],
        "exemplares": achado["exemplares"],
        "titulo": achado["titulo"],
        "autor": achado["autor"],
        "id_origem": achado.get("id_origem", ""),
    }


# --- Fila ---

def carregar_do_disco() -> int:
    """Reidrata a fila a partir de data/fila/*.json. Chamado na subida."""
    FILA_DIR.mkdir(parents=True, exist_ok=True)
    itens: list[dict] = []
    for arq in sorted(FILA_DIR.glob("fila_*.json")):
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(dados, dict):
            continue
        # Arquivos da versao anterior nao tinham id nem status
        dados.setdefault("id", arq.stem.replace("fila_", "", 1))
        dados.setdefault("status", "pendente")
        dados.setdefault("quantidade", int(dados.get("exemplares") or 1))
        dados["exemplares"] = dados["quantidade"]
        itens.append(dados)
    itens.sort(key=lambda i: i.get("timestamp") or "")
    with fila_lock:
        fila[:] = itens
    return len(itens)


def adicionar_fila(dados: dict) -> dict:
    """
    Acrescenta a fila. Se o mesmo ISBN ja esta la em item ainda nao exportado,
    soma exemplares em vez de criar uma segunda ficha do mesmo livro.
    """
    isbn = _normalizar_isbn(dados.get("isbn"))
    qtd = int(dados.get("quantidade") or dados.get("exemplares") or 1)

    if isbn:
        alvo = None
        with fila_lock:
            for existente in fila:
                if (_normalizar_isbn(existente.get("isbn")) == isbn
                        and existente.get("status") in ("pendente", "revisado")):
                    existente["quantidade"] = int(existente.get("quantidade") or 1) + qtd
                    existente["exemplares"] = existente["quantidade"]
                    existente["atualizado_em"] = datetime.now().isoformat()
                    alvo = dict(existente)
                    break
        if alvo is not None:
            _gravar(alvo)
            return {**alvo, "acao": "incrementado"}

    item = {
        "id": _novo_id(),
        "timestamp": datetime.now().isoformat(),
        "status": "pendente",
        "isbn": dados.get("isbn") or "",
        "titulo": dados.get("titulo", ""),
        "subtitulo": dados.get("subtitulo", ""),
        "autor": dados.get("autor", ""),
        "editora": dados.get("editora", ""),
        "ano": dados.get("ano", ""),
        "edicao": dados.get("edicao", ""),
        "paginas": dados.get("paginas", ""),
        "idioma": dados.get("idioma", ""),
        "descricao": dados.get("descricao", ""),
        "capa": dados.get("capa", ""),
        "fonte": dados.get("fonte", ""),
        "cdd": dados.get("cdd", ""),
        "cutter": dados.get("cutter", ""),
        "localizacao": dados.get("localizacao", ""),
        "notas": dados.get("notas", ""),
        "quantidade": qtd,
        "exemplares": qtd,
        "acervo": dados.get("acervo") or _consultar_acervo(isbn),
        "confirmado": True,
    }
    with fila_lock:
        fila.append(item)
    _gravar(item)
    return {**item, "acao": "criado"}


def listar_fila(status: str | None = None, busca: str | None = None) -> dict:
    with fila_lock:
        itens = list(fila)
    if status and status != "todos":
        alvos = set(status.split(","))
        itens = [i for i in itens if i.get("status") in alvos]
    if busca:
        termo = busca.strip().lower()
        campos = ("titulo", "autor", "editora", "isbn", "cdd")
        itens = [i for i in itens
                 if termo in " ".join(str(i.get(c) or "") for c in campos).lower()]
    return {"itens": itens, "total": len(itens)}


def obter_item(item_id: str) -> dict | None:
    with fila_lock:
        for i in fila:
            if i.get("id") == item_id:
                return i
    return None


def atualizar_item(item_id: str, campos: dict) -> dict:
    with fila_lock:
        alvo = next((i for i in fila if i.get("id") == item_id), None)
        if alvo is None:
            return {"status": "nao_encontrado", "id": item_id}
        for chave in CAMPOS_EDITAVEIS:
            if chave in campos:
                alvo[chave] = campos[chave]
        if "quantidade" in campos or "exemplares" in campos:
            q = max(1, int(campos.get("quantidade") or campos.get("exemplares") or 1))
            alvo["quantidade"] = q
            alvo["exemplares"] = q
        novo_status = campos.get("status")
        if novo_status in STATUS_VALIDOS:
            alvo["status"] = novo_status
        alvo["atualizado_em"] = datetime.now().isoformat()
        copia = dict(alvo)

    # ISBN editado a mao: reconsulta o acervo
    if "isbn" in campos:
        info = _consultar_acervo(_normalizar_isbn(copia.get("isbn")))
        copia["acervo"] = info
        with fila_lock:
            for i in fila:
                if i.get("id") == item_id:
                    i["acervo"] = info
    _gravar(copia)
    return {"status": "ok", "item": copia}


def remover_item(item_id: str) -> dict:
    with fila_lock:
        antes = len(fila)
        fila[:] = [i for i in fila if i.get("id") != item_id]
        removeu = len(fila) != antes
    if removeu:
        _arquivo(item_id).unlink(missing_ok=True)
        return {"status": "ok", "id": item_id}
    return {"status": "nao_encontrado", "id": item_id}


def acao_em_lote(ids: list[str], acao: str) -> dict:
    """revisado | pendente | ignorado | remover sobre varios itens de uma vez."""
    alvos = set(ids or [])
    if not alvos:
        return {"status": "vazio", "afetados": 0}
    if acao == "remover":
        afetados = 0
        for item_id in alvos:
            if remover_item(item_id)["status"] == "ok":
                afetados += 1
        return {"status": "ok", "afetados": afetados}
    if acao not in STATUS_VALIDOS:
        return {"status": "erro", "mensagem": f"acao invalida: {acao}"}
    copias = []
    with fila_lock:
        for i in fila:
            if i.get("id") in alvos:
                i["status"] = acao
                i["atualizado_em"] = datetime.now().isoformat()
                copias.append(dict(i))
    for c in copias:
        _gravar(c)
    return {"status": "ok", "afetados": len(copias)}


def reconsultar_acervo() -> dict:
    """Reavalia todos os itens da fila contra o acervo (apos conectar o banco)."""
    try:
        _acervo.indice(forcar=True)
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}
    with fila_lock:
        alvos = [i for i in fila if i.get("status") in ("pendente", "revisado")]
    achados = 0
    for item in alvos:
        info = _consultar_acervo(_normalizar_isbn(item.get("isbn")))
        with fila_lock:
            item["acervo"] = info
        if info:
            achados += 1
        _gravar(dict(item))
    return {"status": "ok", "avaliados": len(alvos), "no_acervo": achados}


def estatisticas() -> dict:
    with fila_lock:
        itens = list(fila)
    with carrinho_lock:
        no_lote = len(carrinho)
        exemplares_lote = sum(int(i.get("quantidade") or 1) for i in carrinho)

    por_status = {s: 0 for s in STATUS_VALIDOS}
    exemplares = 0
    ja_no_acervo = 0
    sem_metadados = 0
    repetidos: dict[str, int] = {}
    for i in itens:
        atual = i.get("status") or "pendente"
        por_status[atual] = por_status.get(atual, 0) + 1
        if atual == "exportado":
            continue
        exemplares += int(i.get("quantidade") or 1)
        if (i.get("acervo") or {}).get("existe"):
            ja_no_acervo += 1
        if not (i.get("titulo") or "").strip():
            sem_metadados += 1
        chave = _normalizar_isbn(i.get("isbn"))
        if chave:
            repetidos[chave] = repetidos.get(chave, 0) + 1

    a_exportar = por_status["pendente"] + por_status["revisado"]
    return {
        "total": len(itens),
        "por_status": por_status,
        "a_exportar": a_exportar,
        "exemplares": exemplares,
        "ja_no_acervo": ja_no_acervo,
        "obras_novas": max(0, a_exportar - ja_no_acervo),
        "sem_metadados": sem_metadados,
        "isbn_repetido": sum(1 for v in repetidos.values() if v > 1),
        "lote": {"itens": no_lote, "exemplares": exemplares_lote},
    }


# --- Lote (alias carrinho): acumula ISBNs; mesmo ISBN soma exemplares ---

def carrinho_adicionar(isbn: str) -> dict:
    """Adiciona ISBN ao lote. Se ja existe, incrementa quantidade (exemplares)."""
    limpo = isbn.replace("-", "").replace(" ", "").strip()
    with carrinho_lock:
        for item in carrinho:
            if item.get("isbn") == limpo:
                item["quantidade"] = int(item.get("quantidade") or 1) + 1
                item["exemplares"] = item["quantidade"]
                return {"status": "incrementado", "isbn": limpo, "item": item,
                        "total": len(carrinho), "quantidade": item["quantidade"]}

    # Lookup externo e consulta ao acervo ficam fora do lock: sao lentos.
    dados = buscar_metadados(limpo)
    info_acervo = _consultar_acervo(limpo)
    entry = {"isbn": limpo, **dados, "quantidade": 1, "exemplares": 1,
             "acervo": info_acervo, "adicionado_em": datetime.now().isoformat()}

    with carrinho_lock:
        # Corrida: outro bipe do mesmo ISBN pode ter entrado durante o lookup
        for item in carrinho:
            if item.get("isbn") == limpo:
                item["quantidade"] = int(item.get("quantidade") or 1) + 1
                item["exemplares"] = item["quantidade"]
                return {"status": "incrementado", "isbn": limpo, "item": item,
                        "total": len(carrinho), "quantidade": item["quantidade"]}
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
    """Move todo o lote para a fila e limpa o lote. Retorna enviados."""
    with carrinho_lock:
        if not carrinho:
            return {"status": "vazio", "enviados": 0}
        itens = list(carrinho)
        carrinho.clear()
    enviados = [adicionar_fila(dados) for dados in itens]
    return {"status": "ok", "enviados": len(enviados), "itens": enviados}
