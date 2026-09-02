"""
Cria os exemplares (holdings) no BibLivre 5, a partir do `exemplares.csv`
gerado por `gerar_marc.py`.

    # 1. confere o que seria feito, sem escrever nada
    python scripts/inserir_exemplares.py saida/exemplares.csv

    # 2. executa de verdade (uma única transação)
    python scripts/inserir_exemplares.py saida/exemplares.csv --executar

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

O QUE ESTE SCRIPT REPRODUZ DO BIBLIVRE (verificado no fonte)
------------------------------------------------------------
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

O CASAMENTO É PELO 035 $a
-------------------------
O BibLivre sobrescreve 001/005/008 ao salvar (`BiblioRecordBO.save`), então o
`NUMACERVO` de origem foi gravado no 035 $a como `(BF)<numero>`. Este script lê
`biblio_records.iso2709`, extrai o 035 $a de cada registro e monta o mapa
`(BF)N -> biblio_records.id`.

TOMBOS SÃO GERADOS
------------------
`accession_number` é NOT NULL e tem índice UNIQUE global
(`IX_biblio_holdings_accession_number`). No acervo de origem só 188 dos 16.251
exemplares têm tombo, e entre esses há apenas 4 valores distintos — não dá para
aproveitar. Geramos no mesmo formato que o BibLivre usa
(`HoldingBO.getNextAccessionNumber`): `<prefixo>.<ano>.<contador>`, com o
prefixo lido da tabela `configurations` e o ano vindo da data de aquisição do
exemplar. Assim o contador do próprio BibLivre continua de onde paramos: ele
faz `max(digitos finais) + 1` dentro do prefixo `<prefixo>.<ano atual>.`.

O tombo original, quando existe, e o NUMACERVO vão para o 852 $x (nota não
pública, editável no formulário de exemplar), junto com o código de
localização de estante em 852 $c.
"""

import argparse
import csv
import getpass
import io
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

from pymarc import Field, MARCReader, Record, Subfield

# Leader de exemplar, exatamente como MarcUtils.createBasicLeader o monta para
# MaterialType.HOLDINGS + RecordStatus.NEW. pymarc recalcula pos/00-04 e
# pos/12-16 ao serializar.
LEADER_HOLDING = "00000nu  a2200000un 4500"

# Valores das colunas, vindos dos enums do BibLivre (todos com toString() em
# minúsculas): HoldingAvailability.AVAILABLE, MaterialType.HOLDINGS.
AVAILABILITY = "available"
MATERIAL = "holdings"

# `logins.id` do admin criado na instalação (sql/biblivre4.sql).
USUARIO_PADRAO = 1

ANO_MIN, ANO_MAX = 1900, date.today().year + 1

INSERT_SQL = """
INSERT INTO biblio_holdings
    (record_id, iso2709, availability, database, material,
     accession_number, location_d, created_by)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def _sf(codigo, valor):
    return Subfield(code=codigo, value=valor)


def ler_prefixo_tombo(cur, schema):
    """
    Prefixo do tombo, na mesma ordem de busca do BibLivre: `Configurations.get`
    procura no schema da biblioteca e, não achando, cai para o schema `global`
    (é lá que `sql/biblivre4.sql` semeia a chave, com o valor 'Bib'; ela só
    aparece no schema da biblioteca se alguém a alterar pela tela de
    Administração).
    """
    for esquema in (schema, "global"):
        cur.execute(
            "SELECT value FROM {}.configurations WHERE key = %s".format(
                _ident(esquema)),
            ("cataloging.accession_number_prefix",),
        )
        achado = cur.fetchone()
        if achado and achado[0].strip():
            return achado[0].strip(), esquema
    return "Bib", "padrão do BibLivre"


def _ident(nome):
    """Identificador SQL entre aspas — os nomes de schema vêm da linha de comando."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
        sys.exit(f"nome de schema inválido: {nome!r}")
    return f'"{nome}"'


def ler_registros(cur):
    """
    Mapa `(BF)N -> (record_id, database, subcampos do 090)`, lido dos registros
    bibliográficos já importados.
    """
    cur.execute("SELECT id, database, iso2709 FROM biblio_records")
    mapa = {}
    duplicados = defaultdict(list)
    sem_035 = []

    for rec_id, database, iso in cur.fetchall():
        leitor = MARCReader(io.BytesIO(iso.encode("utf-8")),
                            to_unicode=True, force_utf8=True)
        registro = next(leitor, None)
        if registro is None:
            sem_035.append(rec_id)
            continue

        # pymarc 5.x: record["035"] lança KeyError se o campo não existir; use
        # .get(), que devolve None.
        campo035 = registro.get("035")
        origem = campo035.get("a") if campo035 is not None else None
        if not origem:
            sem_035.append(rec_id)
            continue

        campo090 = registro.get("090")
        loc = ({c: (campo090.get(c) or "").strip() for c in "abc"}
               if campo090 is not None else {})

        if origem in mapa:
            duplicados[origem].append(rec_id)
        else:
            mapa[origem] = (rec_id, database, loc)

    return mapa, duplicados, sem_035


def montar_exemplar(linha, loc_biblio, tombo, biblioteca, tipo_aquisicao,
                    nota_procedencia=None):
    """
    O registro MARC do exemplar, no molde de HoldingBO.

    `nota_procedencia` sobrescreve o 852 $x. O padrão é a nota da migração;
    a catalogação por ISBN passa a sua (ver catalogacao/holdings.py).
    """
    rec = Record(force_utf8=True, leader=LEADER_HOLDING)

    # 090: o BibLivre copia $a/$b/$c do bibliográfico e acrescenta $d = ex.N.
    # Quando o bibliográfico não tem 090 $c mas o exemplar tem volume, o
    # BibLivre usa "v.N" — aqui o volume vem do CSV.
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

    # 852: localização de estante ($c) e a procedência da migração ($x, nota
    # não pública). ind2='0' porque o formulário de exemplar do BibLivre só
    # oferece 0/1/2 para o segundo indicador do 852.
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


def gerar_tombos(linhas, prefixo, ano_fixo, contador_inicial=None):
    """
    Um tombo `<prefixo>.<ano>.<contador>` por linha, com contador por ano —
    mesmo formato de HoldingBO.getNextAccessionNumber.
    Se contador_inicial for dado, continua de onde parou (para lotes incrementais).
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


def conectar(args):
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 não instalado. Rode: pip install -r requirements.txt")

    senha = args.senha or os.environ.get("PGPASSWORD")
    if not senha:
        senha = getpass.getpass(f"Senha de {args.user}@{args.host}: ")

    con = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname,
                           user=args.user, password=senha)
    con.autocommit = False
    with con.cursor() as cur:
        # O schema da biblioteca única é "single" (Constants.SINGLE_SCHEMA).
        cur.execute(f"SET search_path TO {_ident(args.schema)}, public")
    return con


def main():
    # O relatório imprime títulos e notas acentuados. Num console do Windows
    # com codepage legada, isso viraria UnicodeEncodeError no meio da execução.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        description="Cria os exemplares no BibLivre 5 a partir do exemplares.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.",
    )
    p.add_argument("csv_exemplares", help="exemplares.csv gerado por gerar_marc.py")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--sql-out", metavar="ARQUIVO",
                   help="escreve os INSERTs num .sql em vez de executá-los")
    p.add_argument("--mapa-out", metavar="ARQUIVO",
                   help="CSV de conferência: numacervo, record_id, tombo")

    p.add_argument("--host", default="localhost")
    p.add_argument("--port", default="5432")
    p.add_argument("--dbname", default="biblivre4")
    p.add_argument("--user", default="biblivre")
    p.add_argument("--senha", help="senha do PostgreSQL (ou use PGPASSWORD)")
    p.add_argument("--schema", default="single",
                   help="schema da biblioteca (padrão: single)")

    p.add_argument("--prefixo-tombo",
                   help="padrão: lido de configurations.cataloging.accession_number_prefix")
    p.add_argument("--ano-tombo", type=int,
                   help="usa este ano em todos os tombos, em vez do ano de aquisição")
    p.add_argument("--biblioteca", default="",
                   help="541 $a — biblioteca depositária (padrão: não preenche)")
    p.add_argument("--tipo-aquisicao", default="Migração Biblioteca Fácil",
                   help="541 $c — tipo de aquisição")
    p.add_argument("--usuario", type=int, default=USUARIO_PADRAO,
                   help=f"created_by (padrão: {USUARIO_PADRAO}, o admin)")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com exemplares já na base (risco de duplicar)")
    args = p.parse_args()

    with open(args.csv_exemplares, encoding="utf-8-sig", newline="") as f:
        linhas = [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(f)]
    print(f"{len(linhas):,} exemplares no CSV")

    con = conectar(args)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) FROM biblio_holdings")
            (ja_existem,) = cur.fetchone()
            if ja_existem and not args.permitir_existentes:
                sys.exit(f"ERRO: já existem {ja_existem:,} exemplares em "
                         f"{args.schema}.biblio_holdings. Rodar de novo duplicaria "
                         f"tudo. Use --permitir-existentes se for intencional.")

            if args.prefixo_tombo:
                prefixo, origem_prefixo = args.prefixo_tombo, "linha de comando"
            else:
                prefixo, origem_prefixo = ler_prefixo_tombo(cur, args.schema)
            print(f"prefixo de tombo: {prefixo!r} (de {origem_prefixo})")

            mapa, duplicados, sem_035 = ler_registros(cur)
            print(f"{len(mapa):,} registros bibliográficos com 035 $a legível")
            if sem_035:
                print(f"  ATENÇÃO: {len(sem_035):,} registros sem 035 $a "
                      f"(ids: {sem_035[:5]}{'...' if len(sem_035) > 5 else ''})")
            if duplicados:
                print(f"  ATENÇÃO: {len(duplicados):,} valores de 035 $a repetidos "
                      f"— usando o primeiro de cada. Exemplos: "
                      f"{list(duplicados)[:3]}")

            cur.execute("SELECT accession_number FROM biblio_holdings")
            tombos_existentes = {t for (t,) in cur.fetchall()}

            # continua contador por ano a partir do existente (lotes incrementais)
            contador_inicial = Counter()
            for t in tombos_existentes:
                m = re.match(rf"{re.escape(prefixo)}\.(\d{{4}})\.(\d+)", t)
                if m:
                    ano_e, num = int(m.group(1)), int(m.group(2))
                    if num > contador_inicial[ano_e]:
                        contador_inicial[ano_e] = num

        tombos, por_ano, anos_invalidos = gerar_tombos(
            linhas, prefixo, args.ano_tombo, contador_inicial)

        colisoes = sorted(set(tombos) & tombos_existentes)
        if colisoes:
            sys.exit(f"ERRO: {len(colisoes):,} tombos gerados já existem no banco "
                     f"(ex.: {colisoes[:3]}). accession_number é UNIQUE; use "
                     f"--prefixo-tombo ou --ano-tombo para separar.")
        if len(set(tombos)) != len(tombos):
            sys.exit("ERRO: os tombos gerados não são únicos entre si.")

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
                linha, loc_biblio, tombo, args.biblioteca, args.tipo_aquisicao)
            # iso2709 é text: o BibLivre grava o MARC serializado em UTF-8
            # (MarcUtils.recordToIso2709 usa MarcStreamWriter com "UTF-8").
            iso = rec.as_marc().decode("utf-8")
            valores.append((rec_id, iso, AVAILABILITY, database, MATERIAL,
                            tombo, location_d, args.usuario))

        print(f"{len(valores):,} exemplares casados com "
              f"{len(registros_usados):,} registros bibliográficos")
        if nao_casados:
            faltando = sorted(set(nao_casados))
            print(f"  ATENÇÃO: {len(nao_casados):,} exemplares sem registro "
                  f"correspondente ({len(faltando):,} ids distintos, "
                  f"ex.: {faltando[:5]})")
        orfaos = len(mapa) - len(registros_usados)
        if orfaos > 0:
            print(f"  {orfaos:,} registros bibliográficos ficariam sem exemplar")
        if anos_invalidos:
            print(f"  {len(anos_invalidos)} data(s) de aquisição fora de "
                  f"{ANO_MIN}-{ANO_MAX}, tombo emitido no ano corrente: "
                  f"{[(n, d) for _, d, n in anos_invalidos[:3]]}")
        print("tombos por ano: " + ", ".join(
            f"{ano}:{qtd:,}" for ano, qtd in sorted(por_ano.items())))

        if valores:
            print("\nexemplo do primeiro exemplar:")
            primeiro = next(MARCReader(io.BytesIO(valores[0][1].encode("utf-8")),
                                       to_unicode=True, force_utf8=True))
            print(primeiro)
            print(f"  record_id={valores[0][0]}  database={valores[0][3]}  "
                  f"accession_number={valores[0][5]}  location_d={valores[0][6]}")

        if args.mapa_out:
            with open(args.mapa_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["numacervo", "id_origem", "record_id", "tombo"])
                for linha, tombo in zip(linhas, tombos):
                    achado = mapa.get(linha["id_origem"])
                    w.writerow([linha["numacervo"], linha["id_origem"],
                                achado[0] if achado else "", tombo])
            print(f"\nmapa de conferência -> {args.mapa_out}")

        if args.sql_out:
            with con.cursor() as cur, open(args.sql_out, "w",
                                           encoding="utf-8") as f:
                f.write("BEGIN;\n")
                f.write(f"SET search_path TO {_ident(args.schema)}, public;\n")
                for v in valores:
                    f.write(cur.mogrify(INSERT_SQL.strip(), v).decode("utf-8")
                            + ";\n")
                f.write("COMMIT;\n")
            print(f"SQL -> {args.sql_out} ({len(valores):,} INSERTs)")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            return

        if not valores:
            sys.exit("Nada a inserir.")

        from psycopg2.extras import execute_batch
        with con.cursor() as cur:
            execute_batch(cur, INSERT_SQL, valores, page_size=500)
        con.commit()
        print(f"\n{len(valores):,} exemplares inseridos em "
              f"{args.schema}.biblio_holdings.")
        print("Confira em Catalogação → Exemplares e imprima uma etiqueta de "
              "teste antes de gerar o backup.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
