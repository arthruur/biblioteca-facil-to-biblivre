"""
Lotes por aparelho: N celulares bipando na mesma biblioteca ao mesmo tempo.

Antes existia um lote só, global. Isso funciona com uma pessoa e quebra com
duas: quem está na estante A e quem está na estante B enchem a mesma bandeja,
e se uma delas bipa a prateleira errada não há como desfazer só o que ela fez.
Agora cada aparelho tem a sua bandeja, e o PC vê as N bandejas separadas — pode
enviar uma, algumas ou todas para a fila.

O lote continua volátil de propósito (docs/SPEC_UI.md §1): mora em memória e
esvazia no envio. O que se acrescentou é a identidade de quem bipou.

IDENTIDADE DO APARELHO
----------------------
O id vem do cliente (um uuid guardado no `localStorage` do navegador do
celular) pelo cabeçalho `X-Dispositivo`. Não é autenticação e não pretende
ser: a rede é a LAN da biblioteca, e o que se quer é distinguir aparelhos, não
autorizá-los. Aparelho sem id cai no lote do balcão — é o caso do próprio PC
digitando ISBN à mão.

POR QUE VERSÃO E NÃO SSE
------------------------
A tela do PC precisa ver o bipe do celular aparecer sozinha. `_versao` sobe a
cada mutação e vai em toda resposta de `listar()`; o PC busca a cada dois
segundos e só re-renderiza quando o número muda. Um contador é comparável a
manter fila de eventos por assinante e acordar o loop asyncio de dentro de uma
worker thread — e este servidor atende meia dúzia de aparelhos numa LAN, não
milhares na internet.
"""

import threading
from datetime import datetime, timezone

# Aparelho sem id declarado: o próprio PC, digitando no balcão.
BALCAO = "balcao"
NOME_BALCAO = "Balcão (este PC)"

# Depois disto o aparelho é mostrado como parado — ele não avisa que saiu, só
# para de aparecer. Dois minutos é mais que o intervalo entre dois livros de
# quem está trabalhando, e menos que o tempo de alguém desistir e ir embora.
OCIOSO_SEGUNDOS = 120

_lock = threading.Lock()
_lotes: dict[str, dict] = {}
_versao = 0


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mudou() -> int:
    """Marca uma mutação. Só chamar com `_lock` tomado."""
    global _versao
    _versao += 1
    return _versao


def _obter(dispositivo: str | None, nome: str | None = None) -> dict:
    """A bandeja deste aparelho, criada na primeira vez. Requer `_lock`."""
    ident = (dispositivo or "").strip() or BALCAO
    lote = _lotes.get(ident)
    if lote is None:
        lote = {
            "id": ident,
            "nome": (nome or "").strip()
            or (NOME_BALCAO if ident == BALCAO else ""),
            "criado_em": _agora(),
            "visto_em": _agora(),
            "ultimo_bipe_em": None,
            "itens": [],
        }
        _lotes[ident] = lote
        _mudou()
    lote["visto_em"] = _agora()
    if nome and nome.strip() and nome.strip() != lote["nome"]:
        lote["nome"] = nome.strip()
        _mudou()
    return lote


def _rotulo(lote: dict) -> str:
    """Nome de exibição. Aparelho que nunca se nomeou ganha um do id."""
    if lote["nome"]:
        return lote["nome"]
    return f"Aparelho {lote['id'][:6]}"


def _resumo(lote: dict) -> dict:
    itens = lote["itens"]
    return {
        "id": lote["id"],
        "nome": _rotulo(lote),
        "nomeado": bool(lote["nome"]),
        "criado_em": lote["criado_em"],
        "visto_em": lote["visto_em"],
        "ultimo_bipe_em": lote["ultimo_bipe_em"],
        "titulos": len(itens),
        "exemplares": sum(int(i.get("quantidade") or 1) for i in itens),
        "itens": [dict(i) for i in itens],
    }


# --- Leitura ---

def listar(dispositivo: str | None = None, nome: str | None = None) -> dict:
    """
    Todas as bandejas, mais a versão do estado.

    Passar `dispositivo` registra a presença dele de tabela: é o que o celular
    faz ao abrir a tela, e é assim que o PC descobre que ele existe antes do
    primeiro bipe.
    """
    with _lock:
        if dispositivo:
            _obter(dispositivo, nome)
        aparelhos = [_resumo(l) for l in _lotes.values()]
        versao = _versao

    # Bandeja vazia de aparelho que já foi embora é ruído na tela do PC: ela
    # some da lista sem precisar de "desparear".
    aparelhos = [a for a in aparelhos if a["titulos"] or a["id"] == BALCAO
                 or _ocioso_segundos(a) < OCIOSO_SEGUNDOS]
    aparelhos.sort(key=lambda a: (a["ultimo_bipe_em"] or "", a["criado_em"]),
                   reverse=True)
    return {
        "versao": versao,
        "dispositivos": aparelhos,
        "titulos": sum(a["titulos"] for a in aparelhos),
        "exemplares": sum(a["exemplares"] for a in aparelhos),
    }


def _ocioso_segundos(resumo: dict) -> float:
    marca = resumo["ultimo_bipe_em"] or resumo["visto_em"]
    try:
        quando = datetime.fromisoformat(marca)
    except (TypeError, ValueError):
        return 0.0
    return (datetime.now(timezone.utc) - quando).total_seconds()


def versao() -> int:
    with _lock:
        return _versao


def itens(dispositivo: str | None = None) -> list[dict]:
    """Itens de uma bandeja, ou de todas quando `dispositivo` é None."""
    with _lock:
        if dispositivo:
            lote = _lotes.get(dispositivo.strip() or BALCAO)
            return [dict(i) for i in (lote["itens"] if lote else [])]
        return [dict(i) for l in _lotes.values() for i in l["itens"]]


def totais() -> dict:
    """Contagens agregadas — é o que `estatisticas()` da fila consome."""
    with _lock:
        todos = [i for l in _lotes.values() for i in l["itens"]]
        return {
            "itens": len(todos),
            "exemplares": sum(int(i.get("quantidade") or 1) for i in todos),
            "dispositivos": len(_lotes),
        }


# --- Mutação ---

def adicionar(isbn: str, dispositivo: str | None = None,
              nome: str | None = None, *, buscar, consultar_acervo) -> dict:
    """
    Um bipe.

    `buscar` e `consultar_acervo` entram por parâmetro para este módulo não
    depender de `lookup` nem de `biblivre` — quem chama é `fila.py`, que já
    tem as duas. Elas rodam fora do lock: são lentas (rede e varredura do
    acervo) e segurar o lock nelas travaria o bipe de outro aparelho.
    """
    limpo = isbn.replace("-", "").replace(" ", "").strip()

    with _lock:
        lote = _obter(dispositivo, nome)
        for item in lote["itens"]:
            if item.get("isbn") == limpo:
                item["quantidade"] = int(item.get("quantidade") or 1) + 1
                item["exemplares"] = item["quantidade"]
                lote["ultimo_bipe_em"] = _agora()
                _mudou()
                return {"status": "incrementado", "isbn": limpo,
                        "item": dict(item), "dispositivo": lote["id"],
                        "total": len(lote["itens"]),
                        "quantidade": item["quantidade"]}

    dados = buscar(limpo)
    info_acervo = consultar_acervo(limpo)

    with _lock:
        lote = _obter(dispositivo, nome)
        # Corrida: outro bipe do mesmo ISBN neste aparelho pode ter entrado
        # durante o lookup.
        for item in lote["itens"]:
            if item.get("isbn") == limpo:
                item["quantidade"] = int(item.get("quantidade") or 1) + 1
                item["exemplares"] = item["quantidade"]
                lote["ultimo_bipe_em"] = _agora()
                _mudou()
                return {"status": "incrementado", "isbn": limpo,
                        "item": dict(item), "dispositivo": lote["id"],
                        "total": len(lote["itens"]),
                        "quantidade": item["quantidade"]}

        entrada = {
            "isbn": limpo, **dados, "quantidade": 1, "exemplares": 1,
            "acervo": info_acervo, "adicionado_em": datetime.now().isoformat(),
            "dispositivo": lote["id"], "dispositivo_nome": _rotulo(lote),
        }
        lote["itens"].append(entrada)
        lote["ultimo_bipe_em"] = _agora()
        _mudou()
        return {"status": "ok", "item": dict(entrada),
                "dispositivo": lote["id"], "total": len(lote["itens"])}


def atualizar_quantidade(isbn: str, quantidade: int,
                         dispositivo: str | None = None) -> dict:
    limpo = isbn.replace("-", "").strip()
    q = max(1, int(quantidade))
    with _lock:
        for lote in _alvos(dispositivo):
            for item in lote["itens"]:
                if item.get("isbn") == limpo:
                    item["quantidade"] = q
                    item["exemplares"] = q
                    _mudou()
                    return {"status": "ok", "isbn": limpo, "quantidade": q,
                            "dispositivo": lote["id"], "item": dict(item)}
        return {"status": "nao_encontrado", "isbn": limpo}


def remover(isbn: str, dispositivo: str | None = None) -> dict:
    limpo = isbn.replace("-", "").strip()
    with _lock:
        for lote in _alvos(dispositivo):
            antes = len(lote["itens"])
            lote["itens"][:] = [x for x in lote["itens"]
                                if x.get("isbn") != limpo]
            if len(lote["itens"]) != antes:
                _mudou()
                return {"status": "ok", "dispositivo": lote["id"],
                        "total": len(lote["itens"])}
        return {"status": "nao_encontrado", "isbn": limpo}


def limpar(dispositivo: str | None = None) -> dict:
    """Esvazia uma bandeja, ou todas quando `dispositivo` é None."""
    with _lock:
        alvos = _alvos(dispositivo)
        removidos = sum(len(l["itens"]) for l in alvos)
        for lote in alvos:
            lote["itens"].clear()
        if removidos:
            _mudou()
        return {"status": "ok", "removidos": removidos}


def renomear(dispositivo: str, nome: str) -> dict:
    with _lock:
        lote = _obter(dispositivo)
        lote["nome"] = (nome or "").strip()
        _mudou()
        return {"status": "ok", "id": lote["id"], "nome": _rotulo(lote)}


def esquecer(dispositivo: str) -> dict:
    """Tira o aparelho da tela do PC. O lote dele é descartado."""
    ident = (dispositivo or "").strip()
    with _lock:
        lote = _lotes.pop(ident, None)
        if lote is None:
            return {"status": "nao_encontrado", "id": ident}
        _mudou()
        return {"status": "ok", "id": ident, "descartados": len(lote["itens"])}


def retirar(dispositivo: str | None = None) -> list[dict]:
    """
    Tira os itens das bandejas e devolve — o passo de "enviar para a fila".
    `dispositivo` None retira de todas.

    A gravação na fila é de quem chama; aqui só se esvazia a bandeja, de forma
    atômica, para dois envios simultâneos não mandarem o mesmo item duas vezes.
    """
    with _lock:
        saindo: list[dict] = []
        for lote in _alvos(dispositivo):
            if not lote["itens"]:
                continue
            saindo.extend(dict(i) for i in lote["itens"])
            lote["itens"].clear()
        if saindo:
            _mudou()
        return saindo


def _alvos(dispositivo: str | None) -> list[dict]:
    """Bandejas afetadas por uma operação. Requer `_lock`."""
    if dispositivo:
        lote = _lotes.get(dispositivo.strip())
        return [lote] if lote else []
    return list(_lotes.values())


def semear(item: dict, dispositivo: str | None = None) -> dict:
    """
    Poe um item pronto na bandeja, sem lookup nem consulta ao acervo.

    Existe para os testes: eles precisam de um lote com conteudo conhecido sem
    depender das APIs externas de ISBN nem de um Postgres de pe.
    """
    with _lock:
        lote = _obter(dispositivo)
        entrada = {"quantidade": 1, "exemplares": 1, "acervo": None, **item,
                   "dispositivo": lote["id"],
                   "dispositivo_nome": _rotulo(lote)}
        lote["itens"].append(entrada)
        lote["ultimo_bipe_em"] = _agora()
        _mudou()
        return dict(entrada)


def zerar() -> None:
    """Descarta tudo. Só para os testes."""
    global _versao
    with _lock:
        _lotes.clear()
        _versao += 1
