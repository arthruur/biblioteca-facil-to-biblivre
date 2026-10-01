"""
Exemplares (`biblio_holdings`) — o registro MARC da cópia física.

Dois caminhos chegam aqui, e é de propósito que eles compartilhem este módulo:

    migração        exemplares.csv + mapa do 035 $a  ->  inserir_do_csv
    catalogação     record_id já conhecido           ->  inserir_para_obras

O formato do exemplar (090/541/852/949, o tombo, o INSERT) foi conferido contra
o fonte do BibLivre e **não deve existir em duas versões** — por isso os dois
caminhos passam por `montar_exemplar` e `gerar_tombos`.

POR QUE ESTE PASSO EXISTE
-------------------------
A importação de arquivo do BibLivre só cria registros bibliográficos —
`cataloging/Handler.java:saveImport()` trata BIBLIO, AUTHORITIES e VOCABULARY,
nunca HOLDING. Exemplar é um registro MARC separado ligado ao bibliográfico por
uma FK no banco (`biblio_holdings.record_id`), e essa ligação não tem
representação dentro de um arquivo MARC. Empréstimo é feito contra exemplar
(`LendingBO.doLend(HoldingDTO, ...)`), então sem este passo o acervo fica
catalogado e inemprestável.

Inserir por SQL não é gambiarra: é o que o próprio BibLivre faz na migração
dele do Biblivre 3 (`HoldingDAO.saveFromBiblivre3`).

O QUE ISTO REPRODUZ DO BIBLIVRE (verificado no fonte)
-----------------------------------------------------
Leader     `MarcUtils.createBasicLeader(MaterialType.HOLDINGS, RecordStatus.NEW)`
           pos/05 'n', pos/06 'u', pos/07-08 '  ', pos/09 'a',
           pos/17-19 'un ', pos/20-23 '4500'  ->  "00000nu  a2200000un 4500"
090 $a$b$c copiados do 090 do registro bibliográfico; $d = "ex.N"
           (`HoldingBO.createAutomaticHolding`)
541 $a$c$d biblioteca depositária, tipo e data de aquisição
949 $a     tombo (`MarcConstants.ACCESSION_NUMBER` = "949")
INSERT     colunas de `HoldingDAO.save`: record_id, iso2709, availability,
           database, material, accession_number, location_d, created_by.
           `id` fica por conta de `nextval('biblio_holdings_id_seq')`.
valores    availability='available', database=igual ao do bibliográfico,
           material='holdings' (os enums do BibLivre têm toString() em
           minúsculas; MaterialType também).

O TOMBO DA MIGRAÇÃO É O NUMACERVO
---------------------------------
`accession_number` é NOT NULL e tem índice UNIQUE global
(`IX_biblio_holdings_accession_number`). No acervo de origem o campo `TOMBO`
quase não era usado (188 de 16.251 exemplares, com 4 valores distintos); o
número que a biblioteca escreve no livro e usa no balcão é o `NUMACERVO` — um
por exemplar, único no `.bkp`. É ele que vira o tombo (`tombos_de_origem`), e
por isso o mesmo livro físico tem o mesmo tombo em qualquer carga, de qualquer
backup.

A catalogação por ISBN continua gerando no formato do próprio BibLivre
(`HoldingBO.getNextAccessionNumber`): `<prefixo>.<ano>.<contador>`, com o
prefixo lido da tabela `configurations`. Os dois formatos não colidem — um é só
dígitos, o outro sempre tem o prefixo —, e o contador do BibLivre continua de
onde paramos: ele faz `max(dígitos finais) + 1` dentro de
`<prefixo>.<ano atual>.`, e o NUMACERVO não entra nessa conta.

O formato gerado continua disponível para a migração (`tombo_de_origem=False`,
o `--tombo-gerado` do CLI), para o caso de uma biblioteca que nunca usou o
NUMACERVO como identificação física.
"""

import re
from collections import Counter
from datetime import date, datetime

from pymarc import Field, Record, Subfield

from . import obras as _obras
from .conexao import SCHEMA_GLOBAL, SCHEMA_PADRAO, USUARIO_PADRAO, ident

# Leader de exemplar, exatamente como MarcUtils.createBasicLeader o monta para
# MaterialType.HOLDINGS + RecordStatus.NEW. pymarc recalcula pos/00-04 e
# pos/12-16 ao serializar.
LEADER_HOLDING = "00000nu  a2200000un 4500"

# Valores das colunas, vindos dos enums do BibLivre (todos com toString() em
# minúsculas): HoldingAvailability.AVAILABLE, MaterialType.HOLDINGS.
AVAILABILITY = "available"
MATERIAL = "holdings"

ANO_MIN, ANO_MAX = 1900, date.today().year + 1

TIPO_AQUISICAO_MIGRACAO = "Migração Biblioteca Fácil"
TIPO_AQUISICAO_ISBN = "Catalogação por ISBN"

INSERT_SQL = """
INSERT INTO biblio_holdings
    (record_id, iso2709, availability, database, material,
     accession_number, location_d, created_by)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def _sf(codigo, valor):
    return Subfield(code=codigo, value=valor)


# --- Tombos ---

def ler_prefixo_tombo(cur, schema: str = SCHEMA_PADRAO) -> tuple[str, str]:
    """
    Prefixo do tombo, na mesma ordem de busca do BibLivre: `Configurations.get`
    procura no schema da biblioteca e, não achando, cai para o schema `global`
    (é lá que `sql/biblivre4.sql` semeia a chave, com o valor 'Bib'; ela só
    aparece no schema da biblioteca se alguém a alterar pela tela de
    Administração).
    """
    for esquema in (schema, SCHEMA_GLOBAL):
        cur.execute(
            "SELECT value FROM {}.configurations WHERE key = %s".format(ident(esquema)),
            ("cataloging.accession_number_prefix",),
        )
        achado = cur.fetchone()
        if achado and achado[0].strip():
            return achado[0].strip(), esquema
    return "Bib", "padrão do BibLivre"


def gerar_tombos(linhas, prefixo, ano_fixo=None, contador_inicial=None):
    """
    Um tombo `<prefixo>.<ano>.<contador>` por linha, com contador por ano —
    mesmo formato de HoldingBO.getNextAccessionNumber.

    `contador_inicial` continua de onde o banco parou (lotes incrementais).
    Devolve (tombos, contador_por_ano, anos_invalidos).
    """
    contador = Counter(contador_inicial or {})
    tombos = []
    anos_invalidos = []

    for i, linha in enumerate(linhas):
        if ano_fixo:
            ano = ano_fixo
        else:
            m = re.match(r"(\d{4})", linha["data_aquisicao"].strip())
            ano = int(m.group(1)) if m else 0
            if not (ANO_MIN <= ano <= ANO_MAX):
                anos_invalidos.append((i, linha["data_aquisicao"], linha["numacervo"]))
                ano = date.today().year

        contador[ano] += 1
        tombos.append(f"{prefixo}.{ano}.{contador[ano]}")

    return tombos, contador, anos_invalidos


def tombos_de_origem(linhas) -> list[str]:
    """
    O tombo da migração: o `NUMACERVO` do Biblioteca Fácil, sem zeros à
    esquerda. É o número que está no livro, e é estável entre backups — a mesma
    cópia física tem o mesmo NUMACERVO em qualquer `.bkp` que se carregue.
    """
    return [str(int(str(linha["numacervo"]).strip())) for linha in linhas]


def tombos_existentes(cur, prefixo: str) -> tuple[Counter, set]:
    """
    O que já está no banco: o conjunto de tombos (para detectar colisão) e o
    maior contador por ano dentro do prefixo (para continuar a numeração).
    """
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


# --- MARC do exemplar ---

def montar_exemplar(linha, loc_biblio, tombo, biblioteca="",
                    tipo_aquisicao=TIPO_AQUISICAO_MIGRACAO,
                    nota_procedencia=None):
    """
    O registro MARC do exemplar, no molde de HoldingBO.

    `nota_procedencia` sobrescreve o 852 $x. O padrão é a nota da migração; a
    catalogação por ISBN passa a sua.
    """
    rec = Record(force_utf8=True, leader=LEADER_HOLDING)

    # 090: o BibLivre copia $a/$b/$c do bibliográfico e acrescenta $d = ex.N.
    # Quando o bibliográfico não tem 090 $c mas o exemplar tem volume, o
    # BibLivre usa "v.N" — aqui o volume vem da linha.
    volume_c = loc_biblio.get("c", "")
    if not volume_c and linha["volume"].strip():
        volume_c = f"v. {linha['volume'].strip()}"

    sub090 = []
    if loc_biblio.get("a"):
        sub090.append(_sf("a", loc_biblio["a"]))
    if loc_biblio.get("b"):
        sub090.append(_sf("b", loc_biblio["b"]))
    if volume_c:
        sub090.append(_sf("c", volume_c))
    location_d = f"ex.{linha['ordem_exemplar']}"
    sub090.append(_sf("d", location_d))
    # Indicadores '_': é o que HoldingBO.createHoldingMarcRecord grava.
    rec.add_field(Field(tag="090", indicators=["_", "_"], subfields=sub090))

    sub541 = []
    if biblioteca:
        sub541.append(_sf("a", biblioteca))
    if tipo_aquisicao:
        sub541.append(_sf("c", tipo_aquisicao))
    if linha["data_aquisicao"].strip():
        sub541.append(_sf("d", linha["data_aquisicao"].strip()))
    if sub541:
        rec.add_field(Field(tag="541", indicators=["_", "_"], subfields=sub541))

    # 852: localização de estante ($c) e a procedência ($x, nota não pública).
    # ind2='0' porque o formulário de exemplar do BibLivre só oferece 0/1/2
    # para o segundo indicador do 852.
    sub852 = []
    if linha["localizacao"].strip():
        sub852.append(_sf("c", linha["localizacao"].strip()))
    if nota_procedencia:
        nota = nota_procedencia
    else:
        nota = f"Migrado do Biblioteca Fácil: NUMACERVO {linha['numacervo']}"
        if linha["tombo"].strip():
            nota += f"; tombo original {linha['tombo'].strip()}"
    sub852.append(_sf("x", nota))
    rec.add_field(Field(tag="852", indicators=["_", "0"], subfields=sub852))

    # 949 $a = tombo. Indicadores em branco, como MarcUtils.setAccessionNumber.
    rec.add_field(Field(tag="949", indicators=[" ", " "],
                        subfields=[_sf("a", tombo)]))

    return rec, location_d


# --- Consultas ---

def contar(con) -> int:
    with con.cursor() as cur:
        cur.execute("SELECT count(*) FROM biblio_holdings")
        (n,) = cur.fetchone()
    return n


def por_obra(cur, record_ids: list[int]) -> dict[int, int]:
    """Quantos exemplares cada obra já tem — o próximo é ex.N+1."""
    if not record_ids:
        return {}
    cur.execute(
        "SELECT record_id, count(*) FROM biblio_holdings "
        "WHERE record_id = ANY(%s) GROUP BY record_id", (list(record_ids),))
    return dict(cur.fetchall())


def contagem_global(cur) -> dict[int, int]:
    cur.execute("SELECT record_id, count(*) FROM biblio_holdings GROUP BY record_id")
    return dict(cur.fetchall())


# --- Gravação: caminho da catalogação (record_id já conhecido) ---

def inserir_para_obras(con, pedidos: list[dict], schema: str = SCHEMA_PADRAO,
                       biblioteca: str = "", usuario: int = USUARIO_PADRAO,
                       database: str = "main") -> dict:
    """
    Cria N exemplares para cada obra pedida.

    `pedidos`: [{record_id, quantidade, isbn, titulo, localizacao?, volume?,
                 data_aquisicao?, novo?}]

    Não commita: quem chama decide (a inserção de obras e a de exemplares
    fecham na mesma transação).
    """
    pedidos = [p for p in pedidos
               if p.get("record_id") and int(p.get("quantidade") or 0) > 0]
    if not pedidos:
        return {"inseridos": 0, "tombos": [], "por_obra": {}}

    hoje = date.today().strftime("%Y-%m-%d")
    ids = [int(p["record_id"]) for p in pedidos]

    with con.cursor() as cur:
        prefixo, origem_prefixo = ler_prefixo_tombo(cur, schema)
        locs = _obras.localizacoes(con, ids)
        ordens = por_obra(cur, ids)
        contador, existentes = tombos_existentes(cur, prefixo)

    # Uma linha por exemplar físico, no formato que montar_exemplar espera
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
    colisoes = sorted(set(tombos) & existentes)
    if colisoes:
        raise RuntimeError(
            f"{len(colisoes)} tombo(s) gerados já existem no banco (ex.: {colisoes[:3]}). "
            "accession_number é UNIQUE — verifique o prefixo em Administração.")

    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    valores = []
    mapa_obra: dict[int, list[str]] = {}
    for linha, tombo in zip(linhas, tombos):
        rec_id = linha["record_id"]
        origem = ("obra nova" if linha["novo"]
                  else "exemplar acrescentado a obra existente")
        nota = (f"Catalogação por ISBN {linha['isbn'] or 's/ ISBN'} "
                f"em {agora} ({origem})")
        rec, location_d = montar_exemplar(
            linha, locs.get(rec_id, {}), tombo, biblioteca,
            TIPO_AQUISICAO_ISBN, nota_procedencia=nota)
        iso = rec.as_marc().decode("utf-8")
        valores.append((rec_id, iso, AVAILABILITY, database, MATERIAL,
                        tombo, location_d, usuario))
        mapa_obra.setdefault(rec_id, []).append(tombo)

    from psycopg2.extras import execute_batch

    with con.cursor() as cur:
        execute_batch(cur, INSERT_SQL.strip(), valores, page_size=200)

    return {
        "inseridos": len(valores),
        "tombos": tombos,
        "por_obra": {str(k): v for k, v in mapa_obra.items()},
        "prefixo": prefixo,
        "origem_prefixo": origem_prefixo,
        "por_ano": dict(por_ano),
    }


# --- Gravação: caminho da migração (casa pelo 035 $a) ---

def preparar_do_csv(con, linhas: list[dict], schema: str = SCHEMA_PADRAO,
                    prefixo_tombo: str | None = None, ano_tombo: int | None = None,
                    biblioteca: str = "",
                    tipo_aquisicao: str = TIPO_AQUISICAO_MIGRACAO,
                    usuario: int = USUARIO_PADRAO,
                    tombo_de_origem: bool = True) -> dict:
    """
    Monta os exemplares da migração sem escrever nada.

    Devolve tudo que o relatório de dry-run precisa mostrar e que a gravação
    precisa executar — a mesma estrutura serve aos dois, então o que se confere
    é exatamente o que se grava.

    `tombo_de_origem` (o padrão) usa o NUMACERVO como tombo; `prefixo_tombo` e
    `ano_tombo` só valem quando ele é falso e o tombo é gerado.
    """
    with con.cursor() as cur:
        if tombo_de_origem:
            prefixo, origem_prefixo = "", "NUMACERVO do Biblioteca Fácil"
        elif prefixo_tombo:
            prefixo, origem_prefixo = prefixo_tombo, "linha de comando"
        else:
            prefixo, origem_prefixo = ler_prefixo_tombo(cur, schema)
        contador, existentes = tombos_existentes(cur, prefixo or "Bib")

    mapa, duplicados, sem_035 = _obras.mapa_por_035(con)

    if tombo_de_origem:
        tombos, por_ano, anos_invalidos = tombos_de_origem(linhas), Counter(), []
    else:
        tombos, por_ano, anos_invalidos = gerar_tombos(
            linhas, prefixo, ano_tombo, contador)

    colisoes = sorted(set(tombos) & existentes)
    if colisoes:
        raise RuntimeError(
            f"{len(colisoes):,} tombo(s) da carga já existem no banco "
            f"(ex.: {colisoes[:3]}). accession_number é UNIQUE: a base já tem "
            f"estes exemplares — para recarregar, use 'substituir a base'.")
    if len(set(tombos)) != len(tombos):
        repetidos = [t for t, n in Counter(tombos).items() if n > 1]
        raise RuntimeError(
            f"os tombos da carga não são únicos entre si (ex.: {repetidos[:3]}).")

    valores = []
    registros_usados = set()
    nao_casados = []
    for linha, tombo in zip(linhas, tombos):
        achado = mapa.get(linha["id_origem"])
        if achado is None:
            nao_casados.append(linha["id_origem"])
            continue
        rec_id, database, loc_biblio = achado
        registros_usados.add(rec_id)

        rec, location_d = montar_exemplar(
            linha, loc_biblio, tombo, biblioteca, tipo_aquisicao)
        # iso2709 é text: o BibLivre grava o MARC serializado em UTF-8
        # (MarcUtils.recordToIso2709 usa MarcStreamWriter com "UTF-8").
        iso = rec.as_marc().decode("utf-8")
        valores.append((rec_id, iso, AVAILABILITY, database, MATERIAL,
                        tombo, location_d, usuario))

    return {
        "valores": valores,
        "tombos": tombos,
        "mapa": mapa,
        "duplicados": duplicados,
        "sem_035": sem_035,
        "nao_casados": nao_casados,
        "registros_usados": registros_usados,
        "orfaos": len(mapa) - len(registros_usados),
        "anos_invalidos": anos_invalidos,
        "por_ano": por_ano,
        "prefixo": prefixo,
        "origem_prefixo": origem_prefixo,
    }


def gravar(con, valores: list[tuple]) -> int:
    """Executa os INSERTs preparados. Não commita."""
    if not valores:
        return 0
    from psycopg2.extras import execute_batch

    with con.cursor() as cur:
        execute_batch(cur, INSERT_SQL, valores, page_size=500)
    return len(valores)
