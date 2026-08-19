"""
Carrega a circulação do Biblioteca Fácil no BibLivre 5: empréstimos
(`T13_MOVM` + `T11_MOVI`), multas e reservas (`T15_RESE`).

    # 1. relatório, sem escrever nada
    python scripts/inserir_emprestimos.py saida

    # 2. grava de verdade (uma única transação)
    python scripts/inserir_emprestimos.py saida --executar

Depende dos dois passos anteriores: `inserir_exemplares.py --mapa-out` (para
achar o exemplar) e `inserir_leitores.py --mapa-out` (para achar o leitor).

COMO OS DOIS MODELOS SE ENCAIXAM
--------------------------------
No Biblioteca Fácil o empréstimo é em duas tabelas: `T13_MOVM` é o cabeçalho
(leitor + data) e `T11_MOVI` é uma linha por item levado, com previsão,
devolução e multa. No BibLivre, `lendings` já é uma linha por exemplar
(holding_id, user_id, expected_return_date, return_date) — então cada
`T11_MOVI` vira um `lendings`, herdando o leitor e a data do seu cabeçalho.

O elo que faltava era o exemplar: `T11_NUMACERVO` aponta para um registro de
acervo do Biblioteca Fácil, que é uma cópia física. O `exemplares_mapa.csv`
guarda `numacervo -> tombo`, e o tombo é UNIQUE em `biblio_holdings` — daí sai
o `holding_id` exato. A cobertura é de 19.707 das 19.711 movimentações; as 4
restantes são de um registro de acervo excluído, e nenhuma está em aberto.

EMPRÉSTIMO EM ABERTO NÃO MEXE NO EXEMPLAR
-----------------------------------------
Conferido no fonte: `LendingBO.doLend` não altera
`biblio_holdings.availability`. "Emprestado" é estado derivado — `isLent` /
`LendingDAO` consultam `lendings.return_date IS NULL`, e `availability` diz
outra coisa (se o exemplar pode circular). Logo, os empréstimos em aberto
entram só como linha em `lendings`, sem UPDATE em exemplar.

Como o BibLivre também faz isto por SQL na migração dele do Biblivre 3
(`LendingDAO.saveFromBiblivre3`, que grava id, created e return_date
explícitos), os ids aqui também são atribuídos por nós e a sequence é ajustada
no fim.

O QUE FICA DE FORA, E POR QUE
-----------------------------
  * 113 movimentações com `T11_EXCLUSAO` preenchido — foram apagadas pelo
    bibliotecário no sistema antigo (`EXCLUSAO` é a data da exclusão, não um
    booleano). Use `--incluir-excluidos` para trazê-las.
  * 2 movimentações cujo `T11_NUMEMPRESTIMO` não existe em `T13_MOVM`: sem
    cabeçalho não há leitor, e `lendings.user_id` é NOT NULL.
  * `previous_lending_id` fica nulo: o Biblioteca Fácil não guarda cadeia de
    renovação, cada renovação virou (ou não) uma movimentação nova.
  * Reservas anteriores a `--reservas-desde` (padrão 2026): das 115 pendentes,
    103 são de 2016-2020 — reserva vencida há anos não é intenção viva.
"""

import argparse
import csv
import getpass
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bf_tabela as bf

USUARIO_PADRAO = 1       # logins.id do admin da instalação

SQL_LENDING = """
INSERT INTO lendings (id, holding_id, user_id, previous_lending_id,
                      expected_return_date, return_date, created, created_by)
VALUES (%s, %s, %s, NULL, %s, %s, %s, %s)
"""
SQL_MULTA = """
INSERT INTO lending_fines (lending_id, user_id, fine_value, payment_date,
                           created, created_by)
VALUES (%s, %s, %s, %s, %s, %s)
"""
SQL_RESERVA = """
INSERT INTO reservations (record_id, user_id, expires, created, created_by)
VALUES (%s, %s, %s, %s, %s)
"""


def _ident(nome):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
        sys.exit(f"nome de schema inválido: {nome!r}")
    return f'"{nome}"'


def ler_mapa(caminho, coluna_chave, coluna_valor, rotulo):
    """Lê um dos CSVs de mapa gerados pelos passos anteriores."""
    if not os.path.exists(caminho):
        sys.exit(f"ERRO: {rotulo} não encontrado em {caminho}. Rode o passo "
                 f"anterior com --mapa-out, ou aponte o caminho certo.")
    mapa = {}
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f):
            chave, valor = linha[coluna_chave], linha[coluna_valor]
            if chave and valor:
                mapa[int(chave)] = valor
    if not mapa:
        sys.exit(f"ERRO: {rotulo} ({caminho}) está vazio.")
    return mapa


def montar(movm, movi, rese, tombo_de, record_de, user_de, holding_de, args):
    """
    Devolve (lendings, multas, reservas, estatísticas, descartes).

    Os ids de `lendings` são sequenciais a partir de `args.id_base`, porque as
    multas precisam referenciar o empréstimo antes de ele existir no banco.
    """
    est = Counter()
    descartes = defaultdict(list)
    lendings, multas = [], []
    proximo_id = args.id_base + 1

    # Uma movimentação por vez, na ordem do número do movimento — assim os ids
    # de `lendings` saem na mesma ordem cronológica do sistema antigo.
    for m in sorted(movi, key=lambda r: r["T11_NUMMOVIMENTO"]):
        num = m["T11_NUMMOVIMENTO"]

        if m["T11_EXCLUSAO"] and not args.incluir_excluidos:
            est["excluidos"] += 1
            continue

        mestre = movm.get(m["T11_NUMEMPRESTIMO"])
        if mestre is None:
            descartes["sem_cabecalho"].append(num)
            continue

        user_id = user_de.get(mestre["T13_NUMLEITOR"])
        if user_id is None:
            descartes["leitor_ausente"].append((num, mestre["T13_NUMLEITOR"]))
            continue

        tombo = tombo_de.get(m["T11_NUMACERVO"])
        holding_id = holding_de.get(tombo) if tombo else None
        if holding_id is None:
            descartes["exemplar_ausente"].append((num, m["T11_NUMACERVO"]))
            continue

        criado = bf.data_para_iso(mestre["T13_DATA"])
        previsao = bf.data_para_iso(m["T11_PREVISAO"]) or None
        devolucao = bf.data_para_iso(m["T11_DEVOLUCAO"]) or None
        if not criado:
            # Nenhum caso no backup de 2026-07-30, mas `created` é NOT NULL.
            criado = previsao or devolucao
            est["sem_data_emprestimo"] += 1

        if args.apenas_abertos and devolucao:
            est["devolvidos_ignorados"] += 1
            continue

        lending_id = proximo_id
        proximo_id += 1
        lendings.append((lending_id, holding_id, user_id, previsao, devolucao,
                         criado, USUARIO_PADRAO))
        est["abertos" if devolucao is None else "devolvidos"] += 1
        if criado:
            est[f"ano:{criado[:4]}"] += 1

        # Multa: o Biblioteca Fácil guarda o valor na movimentação, com a data
        # de pagamento e uma data de cancelamento. Multa cancelada não vira
        # dívida no BibLivre.
        if m["T11_MULTA"] > 0 and not m["T11_MultaCancelada"]:
            multas.append((lending_id, user_id, round(m["T11_MULTA"], 2),
                           bf.data_para_iso(m["T11_PGTOMULTA"]) or None,
                           criado, USUARIO_PADRAO))
        elif m["T11_MULTA"] > 0:
            est["multas_canceladas"] += 1

    reservas = []
    for r in rese:
        if r["T15_EXCLUSAO"] or r["T15_UTILIZOU"]:
            est["reservas_encerradas"] += 1
            continue
        criada = bf.data_para_iso(r["T15_DATA"])
        if not criada or int(criada[:4]) < args.reservas_desde:
            est["reservas_antigas"] += 1
            continue
        user_id = user_de.get(r["T15_NUMLEITOR"])
        record_id = record_de.get(r["T15_NUMACERVO"])
        if user_id is None or record_id is None:
            descartes["reserva_sem_vinculo"].append(r["T15_NUMRESERVA"])
            continue
        expira = (bf.data_para_iso(r["T15_VALIDADE2"])
                  or bf.data_para_iso(r["T15_VALIDADE1"]) or None)
        reservas.append((record_id, user_id, expira, criada, USUARIO_PADRAO))

    return lendings, multas, reservas, est, descartes


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
        cur.execute(f"SET search_path TO {_ident(args.schema)}, public")
    return con


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        description="Carrega empréstimos, multas e reservas no BibLivre 5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.")
    p.add_argument("pasta", nargs="?", default="saida",
                   help="pasta com os .dat extraídos do .bkp (padrão: saida)")
    p.add_argument("--mapa-exemplares", default=None,
                   help="padrão: <pasta>/exemplares_mapa.csv")
    p.add_argument("--mapa-leitores", default=None,
                   help="padrão: <pasta>/leitores_mapa.csv")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--apenas-abertos", action="store_true",
                   help="migra só os empréstimos não devolvidos")
    p.add_argument("--incluir-excluidos", action="store_true",
                   help="inclui as movimentações apagadas no sistema antigo")
    p.add_argument("--reservas-desde", type=int, default=2026, metavar="ANO",
                   help="só migra reservas pendentes deste ano em diante "
                        "(padrão: 2026; use 0 para todas)")
    p.add_argument("--sem-reservas", action="store_true",
                   help="não migra reserva nenhuma")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com empréstimos já na base")

    p.add_argument("--host", default="localhost")
    p.add_argument("--port", default="5432")
    p.add_argument("--dbname", default="biblivre4")
    p.add_argument("--user", default="biblivre")
    p.add_argument("--senha", help="senha do PostgreSQL (ou use PGPASSWORD)")
    p.add_argument("--schema", default="single")
    args = p.parse_args()

    movm = {r["T13_NUMEMPRESTIMO"]: r
            for r in bf.carregar(args.pasta, "T13_MOVM.dat").registros()}
    movi = list(bf.carregar(args.pasta, "T11_MOVI.dat").registros())
    rese = [] if args.sem_reservas else list(
        bf.carregar(args.pasta, "T15_RESE.dat").registros())
    print(f"{len(movi):,} movimentações (T11_MOVI) sob {len(movm):,} "
          f"empréstimos (T13_MOVM), {len(rese):,} reservas (T15_RESE)")

    caminho_ex = args.mapa_exemplares or os.path.join(args.pasta,
                                                      "exemplares_mapa.csv")
    caminho_le = args.mapa_leitores or os.path.join(args.pasta,
                                                    "leitores_mapa.csv")
    tombo_de = ler_mapa(caminho_ex, "numacervo", "tombo", "mapa de exemplares")
    record_de = {k: int(v) for k, v in
                 ler_mapa(caminho_ex, "numacervo", "record_id",
                          "mapa de exemplares").items()}
    user_de = {k: int(v) for k, v in
               ler_mapa(caminho_le, "numleitor", "user_id",
                        "mapa de leitores").items()}
    print(f"  mapas: {len(tombo_de):,} exemplares, {len(user_de):,} leitores")

    con = conectar(args)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) FROM lendings")
            (ja,) = cur.fetchone()
            if ja and not args.permitir_existentes:
                # Só barra na gravação; em relatório o dry-run segue.
                recado = (f"já existem {ja:,} empréstimos em "
                          f"{args.schema}.lendings (o empréstimo de teste da "
                          f"conferência conta). Apague-os ou use "
                          f"--permitir-existentes.")
                if args.executar:
                    sys.exit(f"ERRO: {recado}")
                print(f"  ATENÇÃO: {recado}")

            cur.execute("SELECT accession_number, id FROM biblio_holdings")
            holding_de = {t: i for t, i in cur.fetchall()}
            cur.execute("SELECT coalesce(max(id), 0) FROM lendings")
            (args.id_base,) = cur.fetchone()
            cur.execute("SELECT id FROM users")
            ids_usuarios = {i for (i,) in cur.fetchall()}
        print(f"  banco: {len(holding_de):,} exemplares, "
              f"{len(ids_usuarios):,} usuários")

        faltam = sorted(set(user_de.values()) - ids_usuarios)
        if faltam:
            recado = (f"{len(faltam):,} user_id do mapa de leitores não existem "
                      f"em {args.schema}.users (ex.: {faltam[:5]}). Rode o "
                      f"inserir_leitores.py --executar primeiro.")
            if args.executar:
                sys.exit(f"ERRO: {recado}")
            print(f"  ATENÇÃO: {recado}")

        lendings, multas, reservas, est, descartes = montar(
            movm, movi, rese, tombo_de, record_de, user_de, holding_de, args)

        print(f"\n{len(lendings):,} empréstimos a inserir "
              f"({est['abertos']:,} em aberto, {est['devolvidos']:,} devolvidos)")
        print(f"  {len(multas):,} multas, {len(reservas):,} reservas")
        if est["excluidos"]:
            print(f"  {est['excluidos']:,} movimentações excluídas no sistema "
                  f"antigo, fora (use --incluir-excluidos)")
        if est["devolvidos_ignorados"]:
            print(f"  {est['devolvidos_ignorados']:,} devolvidos ignorados "
                  f"(--apenas-abertos)")
        for motivo, itens in descartes.items():
            print(f"  ATENÇÃO: {len(itens):,} descartados por {motivo} "
                  f"(ex.: {itens[:3]})")
        if est["sem_data_emprestimo"]:
            print(f"  {est['sem_data_emprestimo']:,} sem data de empréstimo, "
                  f"usando a previsão/devolução como created")
        if est["multas_canceladas"]:
            print(f"  {est['multas_canceladas']} multa(s) cancelada(s) no "
                  f"sistema antigo, fora")
        if not args.sem_reservas:
            print(f"  reservas: {est['reservas_encerradas']:,} já encerradas e "
                  f"{est['reservas_antigas']:,} anteriores a "
                  f"{args.reservas_desde} ficaram fora")
        print("  empréstimos por ano: " + ", ".join(
            f"{k.split(':', 1)[1]}:{v:,}"
            for k, v in sorted(est.items()) if k.startswith("ano:")))

        # Duas linhas em aberto para o mesmo exemplar deixariam o acervo
        # incoerente: `LendingBO.isLent` acha as duas e a devolução resolveria só
        # uma. Isto não acontece no backup atual, mas é barato garantir.
        abertos = Counter(l[1] for l in lendings if l[4] is None)
        repetidos = [h for h, n in abertos.items() if n > 1]
        if repetidos:
            sys.exit(f"ERRO: {len(repetidos)} exemplar(es) com mais de um "
                     f"empréstimo em aberto (holding_id {repetidos[:5]}). "
                     f"Resolva na origem antes de carregar.")

        if lendings:
            l = lendings[0]
            print(f"\nexemplo do primeiro empréstimo: id={l[0]} "
                  f"holding_id={l[1]} user_id={l[2]} previsão={l[3]} "
                  f"devolução={l[4]} created={l[5]}")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            return

        if not lendings:
            sys.exit("Nada a inserir.")

        from psycopg2.extras import execute_batch
        with con.cursor() as cur:
            execute_batch(cur, SQL_LENDING, lendings, page_size=1000)
            if multas:
                execute_batch(cur, SQL_MULTA, multas, page_size=100)
            if reservas:
                execute_batch(cur, SQL_RESERVA, reservas, page_size=100)
            # `lendings.id` foi atribuído por nós; a sequence precisa passar do
            # último, senão o primeiro empréstimo feito pela tela colide.
            cur.execute("SELECT setval('lendings_id_seq', %s, true)",
                        (max(l[0] for l in lendings),))
        con.commit()

        print(f"\n{len(lendings):,} empréstimos, {len(multas):,} multas e "
              f"{len(reservas):,} reservas inseridos.")
        print("Confira em Circulação → Empréstimo: abra um leitor com "
              "pendência e veja a lista de itens em atraso; e em Administração "
              "→ Relatórios, o de devoluções em atraso.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
