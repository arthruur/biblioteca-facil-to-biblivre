"""
Insercao de exemplares (biblio_holdings) para a catalogacao por ISBN.

Existe porque o caminho novo tem um caso que o `inserir_exemplares.py` da
migracao nao tinha: **acrescentar exemplar a um registro que ja esta no
acervo**. Aquele script casa exemplar com obra pelo `035 $a` do CSV — ele so
sabe ligar exemplar a obra que ele mesmo acabou de importar. Aqui o
`record_id` ja e conhecido (veio do indice de ISBN em `acervo.py`), entao o
casamento e direto.

O que NAO se reinventa: o formato do exemplar. O MARC (090/541/852/949), o
tombo `<prefixo>.<ano>.<contador>` e o INSERT sao os mesmos de
`inserir_exemplares.py`, importados de la — o formato foi conferido contra o
fonte do BibLivre e nao deve existir em duas versoes.
"""

import io
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inserir_exemplares import (  # type: ignore
    AVAILABILITY,
    INSERT_SQL,
    MATERIAL,
    USUARIO_PADRAO,
    gerar_tombos,
    ler_prefixo_tombo,
    montar_exemplar,
)

TIPO_AQUISICAO = "Catalogação por ISBN"


def _loc_dos_registros(cur, record_ids: list[int]) -> dict[int, dict]:
    """090 $a/$b/$c de cada registro — o exemplar herda a localizacao da obra."""
    if not record_ids:
        return {}
    from pymarc import MARCReader

    cur.execute("SELECT id, iso2709 FROM biblio_records WHERE id = ANY(%s)",
                (list(record_ids),))
    saida: dict[int, dict] = {}
    for rec_id, iso in cur.fetchall():
        loc: dict = {}
        try:
            reg = next(MARCReader(io.BytesIO((iso or "").encode("utf-8")),
                                  to_unicode=True, force_utf8=True), None)
            if reg is not None:
                c090 = reg.get("090")
                if c090 is not None:
                    loc = {c: (c090.get(c) or "").strip() for c in "abc"}
        except Exception:
            loc = {}
        saida[rec_id] = loc
    return saida


def _ordem_atual(cur, record_ids: list[int]) -> dict[int, int]:
    """Quantos exemplares cada obra ja tem — o proximo e ex.N+1."""
    if not record_ids:
        return {}
    cur.execute(
        "SELECT record_id, count(*) FROM biblio_holdings "
        "WHERE record_id = ANY(%s) GROUP BY record_id", (list(record_ids),))
    return dict(cur.fetchall())


def _contador_de_tombos(cur, prefixo: str) -> tuple[Counter, set]:
    cur.execute("SELECT accession_number FROM biblio_holdings")
    existentes = {t for (t,) in cur.fetchall() if t}
    contador: Counter = Counter()
    padrao = re.compile(rf"{re.escape(prefixo)}\.(\d{{4}})\.(\d+)$")
    for t in existentes:
        m = padrao.match(t)
        if m:
            ano, num = int(m.group(1)), int(m.group(2))
            if num > contador[ano]:
                contador[ano] = num
    return contador, existentes


def inserir_exemplares(con, pedidos: list[dict], schema: str = "single",
                       biblioteca: str = "", usuario: int = USUARIO_PADRAO) -> dict:
    """
    Cria N exemplares para cada obra pedida.

    `pedidos`: [{record_id, quantidade, isbn, titulo, localizacao?, volume?,
                 data_aquisicao?, novo?}]

    Nao commita: quem chama decide (a insercao de obras e a de exemplares
    fecham na mesma transacao).
    """
    pedidos = [p for p in pedidos if p.get("record_id") and int(p.get("quantidade") or 0) > 0]
    if not pedidos:
        return {"inseridos": 0, "tombos": [], "por_obra": {}}

    hoje = date.today().strftime("%Y-%m-%d")
    ids = [int(p["record_id"]) for p in pedidos]

    with con.cursor() as cur:
        prefixo, origem_prefixo = ler_prefixo_tombo(cur, schema)
        locs = _loc_dos_registros(cur, ids)
        ordens = _ordem_atual(cur, ids)
        contador, tombos_existentes = _contador_de_tombos(cur, prefixo)

    # Uma linha por exemplar fisico, no formato que montar_exemplar espera
    linhas: list[dict] = []
    for p in pedidos:
        rec_id = int(p["record_id"])
        base = ordens.get(rec_id, 0)
        for k in range(int(p["quantidade"])):
            linhas.append({
                "record_id": rec_id,
                "isbn": p.get("isbn") or "",
                "titulo": p.get("titulo") or "",
                "novo": bool(p.get("novo")),
                "numacervo": str(p.get("numacervo") or rec_id),
                "tombo": "",
                "exemplar": "1",
                "ordem_exemplar": base + k + 1,
                "volume": str(p.get("volume") or ""),
                "localizacao": str(p.get("localizacao") or ""),
                "data_aquisicao": str(p.get("data_aquisicao") or hoje),
            })
            ordens[rec_id] = base + k + 1

    tombos, por_ano, _ = gerar_tombos(linhas, prefixo, None, contador)
    colisoes = sorted(set(tombos) & tombos_existentes)
    if colisoes:
        raise RuntimeError(
            f"{len(colisoes)} tombo(s) gerados ja existem no banco (ex.: {colisoes[:3]}). "
            "accession_number e UNIQUE — verifique o prefixo em Administracao.")

    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    valores = []
    por_obra: dict[int, list[str]] = {}
    for linha, tombo in zip(linhas, tombos):
        rec_id = linha["record_id"]
        origem = "obra nova" if linha["novo"] else "exemplar acrescentado a obra existente"
        nota = f"Catalogação por ISBN {linha['isbn'] or 's/ ISBN'} em {agora} ({origem})"
        rec, location_d = montar_exemplar(
            linha, locs.get(rec_id, {}), tombo, biblioteca, TIPO_AQUISICAO,
            nota_procedencia=nota)
        iso = rec.as_marc().decode("utf-8")
        valores.append((rec_id, iso, AVAILABILITY, "main", MATERIAL,
                        tombo, location_d, usuario))
        por_obra.setdefault(rec_id, []).append(tombo)

    from psycopg2.extras import execute_batch

    with con.cursor() as cur:
        execute_batch(cur, INSERT_SQL.strip(), valores, page_size=200)

    return {
        "inseridos": len(valores),
        "tombos": tombos,
        "por_obra": {str(k): v for k, v in por_obra.items()},
        "prefixo": prefixo,
        "origem_prefixo": origem_prefixo,
        "por_ano": dict(por_ano),
    }
