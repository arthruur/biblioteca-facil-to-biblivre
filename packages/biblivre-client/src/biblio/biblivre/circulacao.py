"""
Circulação no BibLivre 5: empréstimos (`lendings`), multas (`lending_fines`)
e reservas (`reservations`).

    from biblio.biblivre import circulacao, conexao

    plano = circulacao.montar(movm, movi, rese, tombo_de, record_de,
                              user_de, holding_de, id_base=0)
    con = conexao.conectar()
    circulacao.inserir(con, plano)
    con.commit()

Depende dos dois passos anteriores da migração terem gerado os mapas: o de
exemplares (para achar o exemplar pelo tombo) e o de leitores (para achar o
`user_id`).

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

import csv
import os
from collections import Counter, defaultdict

from biblio.legado import tabela as bf

from .conexao import USUARIO_PADRAO

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


def ler_mapa(caminho, coluna_chave, coluna_valor, rotulo):
    """Lê um dos CSVs de mapa gerados pelos passos anteriores."""
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"{rotulo} não encontrado em {caminho}. Rode o passo anterior com "
            f"--mapa-out, ou aponte o caminho certo.")
    mapa = {}
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f):
            chave, valor = linha[coluna_chave], linha[coluna_valor]
            if chave and valor:
                mapa[int(chave)] = valor
    if not mapa:
        raise ValueError(f"{rotulo} ({caminho}) está vazio.")
    return mapa


def montar(movm, movi, rese, tombo_de, record_de, user_de, holding_de,
           id_base: int = 0, incluir_excluidos: bool = False,
           apenas_abertos: bool = False, reservas_desde: int = 2026) -> dict:
    """
    Monta empréstimos, multas e reservas sem tocar no banco.

    Os ids de `lendings` são sequenciais a partir de `id_base`, porque as
    multas precisam referenciar o empréstimo antes de ele existir no banco.
    """
    est = Counter()
    descartes = defaultdict(list)
    lendings, multas = [], []
    proximo_id = id_base + 1

    # Uma movimentação por vez, na ordem do número do movimento — assim os ids
    # de `lendings` saem na mesma ordem cronológica do sistema antigo.
    for m in sorted(movi, key=lambda r: r["T11_NUMMOVIMENTO"]):
        num = m["T11_NUMMOVIMENTO"]

        if m["T11_EXCLUSAO"] and not incluir_excluidos:
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

        if apenas_abertos and devolucao:
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
        if not criada or int(criada[:4]) < reservas_desde:
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

    # Duas linhas em aberto para o mesmo exemplar deixariam o acervo
    # incoerente: `LendingBO.isLent` acha as duas e a devolução resolveria só
    # uma. Não acontece no backup atual, mas é barato garantir.
    abertos = Counter(l[1] for l in lendings if l[4] is None)
    duplo_aberto = [h for h, n in abertos.items() if n > 1]

    return {
        "lendings": lendings,
        "multas": multas,
        "reservas": reservas,
        "estatisticas": est,
        "descartes": dict(descartes),
        "duplo_aberto": duplo_aberto,
    }


def contar(con) -> dict:
    with con.cursor() as cur:
        cur.execute("SELECT count(*) FROM lendings")
        (emprestimos,) = cur.fetchone()
        cur.execute("SELECT count(*) FROM lendings WHERE return_date IS NULL")
        (abertos,) = cur.fetchone()
    return {"emprestimos": emprestimos, "abertos": abertos}


def contexto_do_banco(con) -> dict:
    """
    O que a montagem precisa saber do destino: tombo -> holding_id, o maior
    `lendings.id` já usado (base dos ids novos) e os usuários existentes.
    """
    with con.cursor() as cur:
        cur.execute("SELECT accession_number, id FROM biblio_holdings")
        holding_de = {t: i for t, i in cur.fetchall()}
        cur.execute("SELECT coalesce(max(id), 0) FROM lendings")
        (id_base,) = cur.fetchone()
        cur.execute("SELECT id FROM users")
        ids_usuarios = {i for (i,) in cur.fetchall()}
    return {"holding_de": holding_de, "id_base": id_base,
            "ids_usuarios": ids_usuarios}


def inserir(con, plano: dict, usuario: int = USUARIO_PADRAO) -> dict:
    """
    Grava empréstimos, multas e reservas. Não commita.

    Ajusta `lendings_id_seq` no fim: os ids foram atribuídos por nós, e sem o
    setval o primeiro empréstimo feito pela tela colidiria.
    """
    from psycopg2.extras import execute_batch

    lendings = plano["lendings"]
    multas = plano["multas"]
    reservas = plano["reservas"]
    if not lendings:
        return {"emprestimos": 0, "multas": 0, "reservas": 0}

    with con.cursor() as cur:
        execute_batch(cur, SQL_LENDING, lendings, page_size=1000)
        if multas:
            execute_batch(cur, SQL_MULTA, multas, page_size=100)
        if reservas:
            execute_batch(cur, SQL_RESERVA, reservas, page_size=100)
        cur.execute("SELECT setval('lendings_id_seq', %s, true)",
                    (max(l[0] for l in lendings),))

    return {"emprestimos": len(lendings), "multas": len(multas),
            "reservas": len(reservas)}


def carregar_tabelas(pasta, sem_reservas: bool = False) -> dict:
    """Lê T13_MOVM, T11_MOVI e T15_RESE da pasta de tabelas extraídas."""
    movm = {r["T13_NUMEMPRESTIMO"]: r
            for r in bf.carregar(pasta, "T13_MOVM.dat").registros()}
    movi = list(bf.carregar(pasta, "T11_MOVI.dat").registros())
    rese = [] if sem_reservas else list(
        bf.carregar(pasta, "T15_RESE.dat").registros())
    return {"movm": movm, "movi": movi, "rese": rese}
