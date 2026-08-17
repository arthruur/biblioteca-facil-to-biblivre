"""
Carrega os registros bibliográficos (`obras.mrc`) direto em `biblio_records`,
reproduzindo o que o BibLivre faz ao salvar cada registro importado.

    # relatório, sem escrever nada
    python scripts/inserir_obras.py saida/obras.mrc

    # grava, numa transação só
    python scripts/inserir_obras.py saida/obras.mrc --executar

POR QUE POR SQL, E NÃO PELA TELA
--------------------------------
A tela de importação funciona, mas tem dois gargalos para 14.866 registros:

1. O upload devolve TODOS os registros parseados num único JSON para o
   navegador (`Handler.importUpload`), e o Tomcat da instalação roda com heap
   de 256 MB. Um lote desse tamanho numa tacada é frágil.
2. A importação salva na base de **trabalho** (`RecordDatabase.WORK`), e mover
   para a principal exige selecionar registro por registro nos resultados
   paginados — `CatalogingHandler.moveRecords` recebe uma lista de ids montada
   a mão. Não há "mover todos".

Inserir por SQL evita os dois: grava já em `main`, sem passar pelo navegador.
É o mesmo caminho que o BibLivre usa na migração dele do Biblivre 3
(`RecordDAO.saveFromBiblivre3` insere direto em `biblio_records`).

O QUE ESTE SCRIPT REPRODUZ (verificado no fonte E contra 25 registros que
foram importados pela tela, para conferência):

`BiblioRecordBO.save`:
    id      = nextval('biblio_records_id_seq')          getNextSerial(...)
    001     = id em 7 dígitos com zeros à esquerda       MarcUtils.setCF001
    005     = agora, no formato yyyyMMddHHmmss.SSS        MarcUtils.setCF005
    008     = yyMMdd + "s||||     bl|||||||||||||||||por|u"  (só se não houver)
    iso2709 = MARC serializado em UTF-8                   recordToIso2709

`RecordDAO.save`  (INSERT INTO biblio_records):
    (id, iso2709, material, database, created_by)
    material = 'book'   MaterialType.fromRecord(leader 'a'/'m ') -> BOOK, minúsculo
    database = 'main'   (aqui: já entra na base principal, pulando o WORK->MAIN)
    created_by = 1      o admin

O que o `save()` faz e este script NÃO faz: `indexingBo.reindex(...)`. As
tabelas `biblio_idx_*` não são preenchidas aqui — rode Administração →
Manutenção → Reindexar depois, que reconstrói o índice lendo `biblio_records`
em lotes de 30 (`IndexingBO.reindex`), seguro para o heap de 256 MB. Sem o
reindex, os registros existem mas não aparecem na busca.

O 001/005/008 conferidos contra o banco batem exatamente com o que a tela
gravou; o Leader difere só nas posições recalculadas na serialização (tamanho
e endereço-base), que o pymarc reescreve sozinho.
"""

import argparse
import csv
import io
import os
import re
import sys
from datetime import datetime

from pymarc import Field, MARCReader

MATERIAL = "book"       # MaterialType.BOOK.toString()
DATABASE = "main"       # entra direto na base principal
USUARIO_PADRAO = 1      # logins.id do admin

# Template do 008 idêntico ao de MarcUtils.setCF008 (posições 07-40).
CF008_TAIL = "s||||     bl|||||||||||||||||por|u"

INSERT_SQL = ("INSERT INTO biblio_records (id, iso2709, material, database, created_by) "
              "VALUES (%s, %s, %s, %s, %s)")


def _ident(nome):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
        sys.exit(f"nome de schema inválido: {nome!r}")
    return f'"{nome}"'


def set_cf001(rec, rec_id):
    """001 = id em 7 dígitos (DecimalFormat '0000000')."""
    rec.remove_fields("001")
    rec.add_ordered_field(Field(tag="001", data=f"{rec_id:07d}"))


def set_cf005(rec, agora):
    """005 = yyyyMMddHHmmss.SSS (SimpleDateFormat COMPACT_ISO)."""
    rec.remove_fields("005")
    stamp = agora.strftime("%Y%m%d%H%M%S.") + f"{agora.microsecond // 1000:03d}"
    rec.add_ordered_field(Field(tag="005", data=stamp))


def set_cf008(rec, agora):
    """008 só é criado se ainda não existir (mesma regra do MarcUtils)."""
    if rec.get("008") is not None:
        return
    rec.add_ordered_field(
        Field(tag="008", data=agora.strftime("%y%m%d") + CF008_TAIL))


def conectar(args):
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 não instalado. Rode: pip install -r requirements.txt")

    senha = args.senha or os.environ.get("PGPASSWORD")
    if not senha:
        import getpass
        senha = getpass.getpass(f"Senha de {args.user}@{args.host}: ")

    con = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname,
                           user=args.user, password=senha)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(f"SET search_path TO {_ident(args.schema)}, public")
    return con


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        description="Carrega obras.mrc direto em biblio_records (base principal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.")
    p.add_argument("mrc", help="obras.mrc gerado por gerar_marc.py")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--database", default=DATABASE,
                   help=f"base de destino (padrão: {DATABASE})")
    p.add_argument("--usuario", type=int, default=USUARIO_PADRAO,
                   help=f"created_by (padrão: {USUARIO_PADRAO}, o admin)")
    p.add_argument("--mapa-out", metavar="ARQUIVO",
                   help="CSV de conferência: 035, record_id")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", default="5432")
    p.add_argument("--dbname", default="biblivre4")
    p.add_argument("--user", default="biblivre")
    p.add_argument("--senha", help="senha do PostgreSQL (ou use PGPASSWORD)")
    p.add_argument("--schema", default="single")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com registros já na base (risco de duplicar)")
    args = p.parse_args()

    with open(args.mrc, "rb") as f:
        registros = list(MARCReader(f, to_unicode=True, force_utf8=True))
    print(f"{len(registros):,} registros em {args.mrc}")

    faltando_035 = [i for i, r in enumerate(registros)
                    if not (r.get("035") and r["035"]["a"])]
    if faltando_035:
        sys.exit(f"ERRO: {len(faltando_035)} registro(s) sem 035 $a — o "
                 f"casamento dos exemplares depende dele. Índices: {faltando_035[:5]}")

    con = conectar(args)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) FROM biblio_records")
            (ja_existem,) = cur.fetchone()
            if ja_existem and not args.permitir_existentes:
                sys.exit(f"ERRO: já existem {ja_existem:,} registros em "
                         f"{args.schema}.biblio_records. A amostra de teste "
                         f"precisa ser removida antes da carga real (ver README). "
                         f"Use --permitir-existentes se for intencional.")

        # ATENÇÃO: nextval() NÃO é revertido por rollback no PostgreSQL. Por
        # isso o dry-run não pode consumir a sequence — ele apenas projeta os
        # ids a partir do valor atual. O consumo real acontece só no --executar.
        with con.cursor() as cur:
            cur.execute("SELECT last_value, is_called FROM biblio_records_id_seq")
            last_value, is_called = cur.fetchone()
        id_inicial = last_value + 1 if is_called else last_value

        agora = datetime.now()
        valores = []
        mapa = []
        for offset, rec in enumerate(registros):
            rec_id = id_inicial + offset
            set_cf001(rec, rec_id)
            set_cf005(rec, agora)
            set_cf008(rec, agora)
            iso = rec.as_marc().decode("utf-8")
            valores.append((rec_id, iso, MATERIAL, args.database, args.usuario))
            mapa.append((rec["035"]["a"], rec_id))

        print(f"ids atribuídos: {valores[0][0]}..{valores[-1][0]}  "
              f"database={args.database}  material={MATERIAL}  created_by={args.usuario}")
        print("\nexemplo do primeiro registro a gravar:")
        primeiro = next(MARCReader(io.BytesIO(valores[0][1].encode("utf-8")),
                                   to_unicode=True, force_utf8=True))
        print(primeiro)

        if args.mapa_out:
            with open(args.mapa_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id_origem", "record_id"])
                w.writerows(mapa)
            print(f"\nmapa de conferência -> {args.mapa_out}")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            print("Os ids acima são uma PROJEÇÃO do valor atual da sequence; "
                  "o dry-run não a consome.")
            con.rollback()
            return

        # Consome a sequence de fato e confirma que casa com o projetado (nada
        # mais deveria estar gravando nesta base durante a migração).
        with con.cursor() as cur:
            cur.execute("SELECT nextval('biblio_records_id_seq') "
                        "FROM generate_series(1, %s)", (len(valores),))
            ids_reais = [r[0] for r in cur.fetchall()]
        if ids_reais != [v[0] for v in valores]:
            sys.exit("ERRO: a sequence avançou entre a projeção e a gravação "
                     "(há outra sessão escrevendo?). Nada foi gravado.")

        from psycopg2.extras import execute_batch
        with con.cursor() as cur:
            execute_batch(cur, INSERT_SQL, valores, page_size=500)
        con.commit()
        print(f"\n{len(valores):,} registros inseridos em "
              f"{args.schema}.biblio_records (database={args.database}).")
        print("PRÓXIMO PASSO: Administração → Manutenção → Reindexar. Sem isso "
              "os registros não aparecem na busca.")
        print("Depois do reindex, rode o inserir_exemplares.py.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
