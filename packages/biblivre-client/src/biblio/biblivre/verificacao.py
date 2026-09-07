"""
Conferência pós-carga: as perguntas que só o banco inteiro responde.

    from biblio.biblivre import conexao, verificacao

    relatorio = verificacao.conferir(conexao.conectar())

O roteiro de importação termina mandando "conferir em Catalogação → Exemplares
e imprimir uma etiqueta de teste". A etiqueta é conferência de papel — margem,
impressora, se o leitor da biblioteca lê o que saiu — e nenhuma automação
responde isso. Já a conferência de dados é consulta, e automatizada cobre as
14.866 obras e os 16.251 exemplares em vez de uma amostra de olho.

A CHECAGEM QUE JUSTIFICA O MÓDULO
---------------------------------
`biblio_records` sem linha em `biblio_idx_fields` é a única resposta objetiva
para "o reindex funcionou?". Inserir por SQL não passa pelo indexador
(`BiblioRecordBO.save` chama `indexingBo.reindex`, o `obras.inserir` não), e o
sintoma é traiçoeiro: o registro **existe**, aparece na aba Exemplares, é
emprestável pelo tombo — só não aparece na busca. Hoje ninguém sabe se o
reindex pegou sem abrir o BibLivre e procurar um título de cor; um catálogo de
14.866 obras invisível na busca é um acervo perdido, e o `.b5bz` empacota o
índice vazio junto.

E A ARMADILHA DAS SEQUENCES
---------------------------
A migração grava **id explícito** — é o que preserva a numeração de origem
(`users.id` = `T04_NUMLEITOR`, `lendings.id` na ordem cronológica), e é o que o
próprio BibLivre faz em `UserDAO.saveFromBiblivre3` / `LendingDAO.
saveFromBiblivre3`. Só que `INSERT` com id explícito **não avança a sequence**.
Quem carrega sem o `setval` no fim deixa `users_id_seq` em 1 com 2.743 leitores
na tabela — e aí nada acontece. O erro só aparece no primeiro empréstimo ou no
primeiro cadastro feito pela tela (`getNextSerial`), com fila no balcão, e a
mensagem que o BibLivre mostra é uma violação de chave duplicada que não diz
nada sobre migração. Esta conferência é o único lugar em que essa bomba é
visível **antes** de armar.

O restante das checagens é integridade referencial barata: exemplar sem obra,
obra sem exemplar (não empresta — `LendingBO.doLend` opera sobre `HoldingDTO`),
tombo duplicado (`IX_biblio_holdings_accession_number` é UNIQUE), empréstimo
apontando para o vazio, exemplar com duas linhas em aberto (`isLent` acha as
duas e a devolução resolve uma só).

CONTRATO
--------
    conferir(con) -> {"checagens": [{chave, rotulo, ok, valor, esperado,
                                     detalhe}],
                      "resumo": {ok, falhas, nao_verificadas, total}}

    ok = True   passou (ou é contagem informativa, que só relata)
    ok = False  falhou; `detalhe` traz uma amostra de até 10 exemplos
    ok = None   não deu para verificar (tabela ausente, permissão); `detalhe`
                traz o motivo e as outras checagens seguem

Checagem informativa é a que tem `esperado is None`: contagem de referência,
distribuição de tombos, prefixo em vigor. Ela nunca falha — serve para conferir
número com número, não para barrar.

SÓ LEITURA: nenhum INSERT, nenhum UPDATE, nenhum commit. O único efeito
colateral possível é um `rollback`: no PostgreSQL um erro aborta a transação
inteira, então uma checagem que estoura obriga a desfazer para as seguintes
rodarem. Passe uma conexão sem trabalho pendente.
"""

import functools

from . import exemplares as _exemplares
from .conexao import ident

# Quantos exemplos entram no `detalhe` de uma falha: "3 órfãos" sem dizer quais
# não ajuda ninguém a consertar. As consultas de amostra carregam o `LIMIT 10`
# escrito no próprio SQL; aqui é o corte das listas montadas em Python.
AMOSTRA = 10

# As tabelas com id gravado explicitamente pela migração e a sequence que o
# BibLivre consulta ao gravar pela tela (`RecordDAO.getNextSerial`).
SEQUENCES = [
    ("biblio_records", "biblio_records_id_seq"),
    ("biblio_holdings", "biblio_holdings_id_seq"),
    ("lendings", "lendings_id_seq"),
    ("users", "users_id_seq"),
]

# `pgcode` -> o que dizer para quem lê o relatório. O texto do psycopg2 vem
# junto, mas sozinho ele não distingue "esta instalação não tem a tabela" de
# "esta conta não enxerga a tabela".
MOTIVOS = {
    "42P01": "tabela não existe neste schema",
    "42703": "coluna não existe (schema do BibLivre diferente do esperado)",
    "42501": "sem permissão de leitura",
    "3F000": "schema não existe",
}


# --------------------------------------------------------------- helpers

def _motivo(erro: Exception) -> str:
    """Por que a checagem não rodou, numa linha."""
    texto = str(erro).strip().splitlines()
    texto = texto[0] if texto else erro.__class__.__name__
    prefixo = MOTIVOS.get(getattr(erro, "pgcode", None))
    return f"{prefixo} — {texto}" if prefixo else texto


def _exemplos(linhas, molde: str) -> str:
    """As linhas da amostra viradas texto, no molde de cada checagem."""
    itens = [molde.format(*["?" if v is None else v for v in linha])
             for linha in linhas]
    return ("ex.: " + "; ".join(itens)) if itens else ""


def _zero(cur, sql_contagem: str, sql_amostra: str = "", molde: str = "",
          dica: str = "") -> dict:
    """
    A forma de quase toda checagem daqui: uma contagem que precisa dar 0.

    A contagem é feita no banco (nada de trazer 16 mil linhas para contar em
    Python) e a amostra só é buscada quando já se sabe que falhou.
    """
    cur.execute(sql_contagem)
    linha = cur.fetchone()
    total = int(linha[0]) if linha else 0
    if total == 0:
        return {"ok": True, "valor": 0}

    detalhe = ""
    if sql_amostra:
        cur.execute(sql_amostra)
        detalhe = _exemplos(cur.fetchall(), molde)
    if dica:
        detalhe = f"{detalhe}  {dica}".strip()
    return {"ok": False, "valor": total, "detalhe": detalhe}


def _linha_unica(cur, sql: str, quantas: int) -> tuple:
    """Uma linha com N colunas, ou um erro que explica o que veio no lugar."""
    cur.execute(sql)
    linha = cur.fetchone()
    if not linha or len(linha) != quantas:
        raise RuntimeError(
            f"resposta inesperada do banco para: {' '.join(sql.split())[:60]}…")
    return tuple(linha)


# ------------------------------------------- 1. o índice (o reindex pegou?)

def _indice_reindex(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM biblio_records r
            WHERE NOT EXISTS (SELECT 1 FROM biblio_idx_fields i
                               WHERE i.record_id = r.id)""",
        """SELECT r.id, r.database FROM biblio_records r
            WHERE NOT EXISTS (SELECT 1 FROM biblio_idx_fields i
                               WHERE i.record_id = r.id)
            ORDER BY r.id LIMIT 10""",
        "id {0} (base {1})",
        "estes registros existem mas NÃO aparecem na busca: rode "
        "Administração → Manutenção → Reindexar base bibliográfica e confira "
        "de novo antes de gerar o .b5bz.")


def _tabelas_de_indice(cur) -> dict:
    """
    Tamanho das três tabelas de índice — contexto para a checagem acima.

    `biblio_idx_autocomplete` em 0 é o esperado e não é defeito: a configuração
    de formulário padrão não tem subcampo `previous_values`, os únicos que
    alimentam essa tabela (`Fields.loadAutocompleteSubFields`).
    """
    campos, ordenacao, autocompletar = _linha_unica(cur, """
        SELECT (SELECT count(*) FROM biblio_idx_fields),
               (SELECT count(*) FROM biblio_idx_sort),
               (SELECT count(*) FROM biblio_idx_autocomplete)
    """, 3)
    return {
        "ok": True,
        "valor": campos,
        "detalhe": (f"biblio_idx_fields: {campos:,}; biblio_idx_sort: "
                    f"{ordenacao:,}; biblio_idx_autocomplete: "
                    f"{autocompletar:,} (0 aqui é correto)"),
    }


# ------------------------------------------------------- 2. as sequences

def _sequencia(cur, tabela: str, sequencia: str) -> dict:
    """
    A sequence entrega um id maior do que o maior já gravado?

    Se não, o próximo INSERT feito pelo BibLivre (empréstimo no balcão, leitor
    novo, obra nova) estoura chave duplicada. Ver o topo do módulo.
    """
    (maior,) = _linha_unica(
        cur, f"SELECT coalesce(max(id), 0) FROM {ident(tabela)}", 1)
    ultimo, chamada = _linha_unica(
        cur, f"SELECT last_value, is_called FROM {ident(sequencia)}", 2)

    proximo = ultimo + 1 if chamada else ultimo
    esperado = f"> {maior:,}"
    if proximo > maior:
        return {"ok": True, "valor": proximo, "esperado": esperado}
    return {
        "ok": False,
        "valor": proximo,
        "esperado": esperado,
        "detalhe": (f"{sequencia} entregaria {proximo:,} e {tabela}.id já vai "
                    f"até {maior:,} — o primeiro registro gravado pela tela do "
                    f"BibLivre estoura chave duplicada. Corrija com: "
                    f"SELECT setval('{sequencia}', {maior}, true);"),
    }


# ------------------------------------------- 3. integridade obra/exemplar

def _exemplares_orfaos(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM biblio_holdings h
            WHERE NOT EXISTS (SELECT 1 FROM biblio_records r
                               WHERE r.id = h.record_id)""",
        """SELECT h.id, h.accession_number, h.record_id FROM biblio_holdings h
            WHERE NOT EXISTS (SELECT 1 FROM biblio_records r
                               WHERE r.id = h.record_id)
            ORDER BY h.id LIMIT 10""",
        "holding {0} (tombo {1}) aponta para record_id {2}",
        "exemplar sem obra não tem ficha: some do catálogo e da tela de "
        "Exemplares.")


def _obras_sem_exemplar(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM biblio_records r
            WHERE r.database = 'main'
              AND NOT EXISTS (SELECT 1 FROM biblio_holdings h
                               WHERE h.record_id = r.id)""",
        """SELECT r.id FROM biblio_records r
            WHERE r.database = 'main'
              AND NOT EXISTS (SELECT 1 FROM biblio_holdings h
                               WHERE h.record_id = r.id)
            ORDER BY r.id LIMIT 10""",
        "record_id {0}",
        "obra sem exemplar aparece no catálogo e NÃO empresta "
        "(LendingBO.doLend opera sobre HoldingDTO).")


def _tombos_duplicados(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM (SELECT accession_number
                                   FROM biblio_holdings
                                  GROUP BY accession_number
                                 HAVING count(*) > 1) d""",
        """SELECT accession_number, count(*) FROM biblio_holdings
            GROUP BY accession_number HAVING count(*) > 1
            ORDER BY count(*) DESC, accession_number LIMIT 10""",
        "{0} ({1}x)",
        "accession_number tem índice UNIQUE "
        "(IX_biblio_holdings_accession_number): com duplicata o restore do "
        "próprio .b5bz falha na criação do índice.")


def _tombos_em_branco(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM biblio_holdings
            WHERE accession_number IS NULL OR btrim(accession_number) = ''""",
        """SELECT id, record_id FROM biblio_holdings
            WHERE accession_number IS NULL OR btrim(accession_number) = ''
            ORDER BY id LIMIT 10""",
        "holding {0} (obra {1})",
        "o tombo é o código que o balcão bipa; sem ele o exemplar só é "
        "achável pelo id.")


def _base_divergente(cur) -> dict:
    """
    `HoldingDAO.save` copia o `database` do bibliográfico
    (`setRecordDatabase(autoDto.getDatabase())`). Divergir esconde o exemplar:
    a busca só enxerga `RecordDatabase.MAIN`.
    """
    return _zero(
        cur,
        """SELECT count(*) FROM biblio_holdings h
            JOIN biblio_records r ON r.id = h.record_id
           WHERE coalesce(h.database, '') <> coalesce(r.database, '')""",
        """SELECT h.id, h.database, r.database FROM biblio_holdings h
            JOIN biblio_records r ON r.id = h.record_id
           WHERE coalesce(h.database, '') <> coalesce(r.database, '')
           ORDER BY h.id LIMIT 10""",
        "holding {0} está em {1} e a obra em {2}",
        "exemplar em base diferente da obra não aparece junto dela.")


def _marc_vazio(cur) -> dict:
    """`iso2709` vazio passa no NOT NULL e quebra a ficha na tela."""
    obras, exemplares = _linha_unica(cur, """
        SELECT (SELECT count(*) FROM biblio_records
                 WHERE iso2709 IS NULL OR btrim(iso2709) = ''),
               (SELECT count(*) FROM biblio_holdings
                 WHERE iso2709 IS NULL OR btrim(iso2709) = '')
    """, 2)
    total = obras + exemplares
    if total == 0:
        return {"ok": True, "valor": 0}

    cur.execute("""
        (SELECT 'obra' AS tipo, id FROM biblio_records
          WHERE iso2709 IS NULL OR btrim(iso2709) = '' ORDER BY id LIMIT 5)
        UNION ALL
        (SELECT 'exemplar' AS tipo, id FROM biblio_holdings
          WHERE iso2709 IS NULL OR btrim(iso2709) = '' ORDER BY id LIMIT 5)
    """)
    return {
        "ok": False,
        "valor": total,
        "detalhe": (f"{obras:,} obra(s) e {exemplares:,} exemplar(es) sem MARC. "
                    + _exemplos(cur.fetchall(), "{0} {1}")),
    }


# ------------------------------------------------ 4. leitores e circulação

def _chaves_orfas(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM users_values v
            WHERE NOT EXISTS (SELECT 1 FROM users_fields f WHERE f.key = v.key)""",
        """SELECT v.key, count(*) FROM users_values v
            WHERE NOT EXISTS (SELECT 1 FROM users_fields f WHERE f.key = v.key)
            GROUP BY v.key ORDER BY count(*) DESC, v.key LIMIT 10""",
        "{0} ({1} leitor(es))",
        "há FK de users_values.key para users_fields.key: uma chave órfã "
        "significa campo apagado depois da carga, e o dado fica invisível na "
        "tela de Circulação.")


def _emprestimos_sem_exemplar(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM lendings l
            WHERE NOT EXISTS (SELECT 1 FROM biblio_holdings h
                               WHERE h.id = l.holding_id)""",
        """SELECT l.id, l.holding_id FROM lendings l
            WHERE NOT EXISTS (SELECT 1 FROM biblio_holdings h
                               WHERE h.id = l.holding_id)
            ORDER BY l.id LIMIT 10""",
        "lending {0} -> holding {1}",
        "a devolução não acha o exemplar e a tela de Circulação quebra ao "
        "abrir o leitor.")


def _emprestimos_sem_leitor(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM lendings l
            WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = l.user_id)""",
        """SELECT l.id, l.user_id FROM lendings l
            WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = l.user_id)
            ORDER BY l.id LIMIT 10""",
        "lending {0} -> user {1}",
        "empréstimo sem leitor não é cobrável nem devolvível pela tela.")


def _multas_sem_emprestimo(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM lending_fines f
            WHERE NOT EXISTS (SELECT 1 FROM lendings l WHERE l.id = f.lending_id)""",
        """SELECT f.lending_id, f.user_id FROM lending_fines f
            WHERE NOT EXISTS (SELECT 1 FROM lendings l WHERE l.id = f.lending_id)
            ORDER BY f.lending_id LIMIT 10""",
        "multa do lending {0} (user {1})",
        "multa órfã aparece na dívida do leitor sem o item que a gerou.")


def _reservas_sem_vinculo(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM reservations s
            WHERE NOT EXISTS (SELECT 1 FROM biblio_records r WHERE r.id = s.record_id)
               OR NOT EXISTS (SELECT 1 FROM users u WHERE u.id = s.user_id)""",
        """SELECT s.record_id, s.user_id FROM reservations s
            WHERE NOT EXISTS (SELECT 1 FROM biblio_records r WHERE r.id = s.record_id)
               OR NOT EXISTS (SELECT 1 FROM users u WHERE u.id = s.user_id)
            ORDER BY s.record_id LIMIT 10""",
        "reserva da obra {0} pelo leitor {1}",
        "reserva é ligada ao registro (record_id), não ao exemplar.")


def _duplo_emprestimo_aberto(cur) -> dict:
    return _zero(
        cur,
        """SELECT count(*) FROM (SELECT holding_id FROM lendings
                                  WHERE return_date IS NULL
                                  GROUP BY holding_id
                                 HAVING count(*) > 1) d""",
        """SELECT l.holding_id, count(*) FROM lendings l
            WHERE l.return_date IS NULL
            GROUP BY l.holding_id HAVING count(*) > 1
            ORDER BY count(*) DESC, l.holding_id LIMIT 10""",
        "holding {0} com {1} em aberto",
        "'emprestado' é estado derivado (return_date IS NULL): LendingBO."
        "isLent acha as duas linhas e a devolução resolve só uma.")


# --------------------------------------------- 5. contagens de referência

def _total_obras(cur) -> dict:
    cur.execute("""SELECT database, count(*) FROM biblio_records
                    GROUP BY database ORDER BY database""")
    linhas = cur.fetchall()
    por_base = {(base or "?"): n for base, n in linhas}
    return {
        "ok": True,
        "valor": por_base.get("main", 0),
        "detalhe": ", ".join(f"{base}: {n:,}" for base, n in sorted(por_base.items()))
                   or "tabela vazia",
    }


def _total_exemplares(cur) -> dict:
    cur.execute("""SELECT availability, count(*) FROM biblio_holdings
                    GROUP BY availability ORDER BY availability""")
    linhas = cur.fetchall()
    return {
        "ok": True,
        "valor": sum(n for _, n in linhas),
        "detalhe": ", ".join(f"{(a or '?')}: {n:,}" for a, n in linhas)
                   or "tabela vazia",
    }


def _total_leitores(cur) -> dict:
    """`UserStatus`: active, pending_issues, inactive, blocked. Os dois últimos
    não emprestam (`LendingBO.checkLending`), e inactive some da busca."""
    cur.execute("SELECT status, count(*) FROM users GROUP BY status ORDER BY status")
    linhas = cur.fetchall()
    return {
        "ok": True,
        "valor": sum(n for _, n in linhas),
        "detalhe": ", ".join(f"{(s or '?')}: {n:,}" for s, n in linhas)
                   or "tabela vazia",
    }


def _total_emprestimos(cur) -> dict:
    total, abertos = _linha_unica(cur, """
        SELECT count(*),
               sum(CASE WHEN return_date IS NULL THEN 1 ELSE 0 END)
          FROM lendings
    """, 2)
    abertos = abertos or 0
    return {"ok": True, "valor": total,
            "detalhe": f"{abertos:,} em aberto, {total - abertos:,} devolvidos"}


def _total_multas(cur) -> dict:
    total, pagas, soma = _linha_unica(cur, """
        SELECT count(*),
               sum(CASE WHEN payment_date IS NOT NULL THEN 1 ELSE 0 END),
               coalesce(sum(fine_value), 0)
          FROM lending_fines
    """, 3)
    pagas = pagas or 0
    return {"ok": True, "valor": total,
            "detalhe": f"{pagas:,} pagas, {total - pagas:,} em aberto; "
                       f"total R$ {float(soma):,.2f}"}


def _total_reservas(cur) -> dict:
    total, vencidas = _linha_unica(cur, """
        SELECT count(*),
               sum(CASE WHEN expires IS NOT NULL AND expires < current_date
                        THEN 1 ELSE 0 END)
          FROM reservations
    """, 2)
    vencidas = vencidas or 0
    return {"ok": True, "valor": total,
            "detalhe": f"{vencidas:,} já vencidas (expires < hoje)"}


# ------------------------------------------------------------ 6. tombos

def _tombos_por_ano(cur) -> dict:
    """
    A distribuição no formato `<prefixo>.<ano>.<contador>` que
    `HoldingBO.getNextAccessionNumber` produz e continua.
    """
    cur.execute("""
        SELECT substring(accession_number from '^(.*)[.][0-9]{4}[.][0-9]+$'),
               substring(accession_number from '[.]([0-9]{4})[.][0-9]+$'),
               count(*)
          FROM biblio_holdings
         GROUP BY 1, 2
         ORDER BY 1, 2
    """)
    linhas = cur.fetchall()
    no_formato = [(p, a, n) for p, a, n in linhas if a]
    fora = sum(n for _, a, n in linhas if not a)

    partes = [f"{p}.{a}: {n:,}" for p, a, n in no_formato[:AMOSTRA + 2]]
    if len(no_formato) > AMOSTRA + 2:
        partes.append(f"… (+{len(no_formato) - AMOSTRA - 2} grupos)")
    if fora:
        partes.append(f"fora do formato <prefixo>.<ano>.<n>: {fora:,}")
    return {"ok": True, "valor": sum(n for _, _, n in no_formato),
            "detalhe": ", ".join(partes) or "nenhum tombo"}


def _prefixo_em_vigor(cur) -> dict:
    """
    `configurations['cataloging.accession_number_prefix']`, na mesma ordem de
    busca do `Configurations.get`: schema da biblioteca e depois `global`.
    """
    (schema,) = _linha_unica(cur, "SELECT current_schema()", 1)
    prefixo, origem = _exemplares.ler_prefixo_tombo(cur, schema)
    return {
        "ok": True,
        "valor": prefixo,
        "detalhe": (f"lido de {origem}; o BibLivre continua a numeração em "
                    f"{prefixo}.<ano corrente>.<max+1>, então tombos gerados "
                    f"com outro prefixo não colidem — e também não continuam."),
    }


# ------------------------------------------------------- a lista completa
#
# (chave, rótulo, esperado, função). `esperado is None` marca a checagem
# informativa: ela relata, não barra. O esperado fica aqui, e não só no
# retorno da função, para que a checagem que NÃO rodou continue sabendo o que
# deveria ter respondido.

_CHECAGENS = [
    ("indice_reindex", "ÍNDICE: obras fora de biblio_idx_fields", 0,
     _indice_reindex),
] + [
    (f"sequence_{tabela}", f"sequence de {tabela}", "à frente do max(id)",
     functools.partial(_sequencia, tabela=tabela, sequencia=sequencia))
    for tabela, sequencia in SEQUENCES
] + [
    ("exemplares_orfaos", "exemplares órfãos (sem obra)", 0, _exemplares_orfaos),
    ("obras_sem_exemplar", "obras sem exemplar (base main)", 0,
     _obras_sem_exemplar),
    ("tombos_duplicados", "tombos duplicados", 0, _tombos_duplicados),
    ("tombos_em_branco", "tombos em branco", 0, _tombos_em_branco),
    ("base_divergente", "exemplar em base diferente da obra", 0, _base_divergente),
    ("marc_vazio", "MARC vazio em obra ou exemplar", 0, _marc_vazio),
    ("chaves_orfas", "users_values com chave fora de users_fields", 0,
     _chaves_orfas),
    ("emprestimos_sem_exemplar", "empréstimos sem exemplar", 0,
     _emprestimos_sem_exemplar),
    ("emprestimos_sem_leitor", "empréstimos sem leitor", 0,
     _emprestimos_sem_leitor),
    ("multas_sem_emprestimo", "multas sem empréstimo", 0, _multas_sem_emprestimo),
    ("reservas_sem_vinculo", "reservas sem obra ou sem leitor", 0,
     _reservas_sem_vinculo),
    ("duplo_emprestimo_aberto", "exemplar com 2 empréstimos em aberto", 0,
     _duplo_emprestimo_aberto),

    # Informativas: contagem para conferir número com número.
    ("tabelas_de_indice", "tabelas de índice (fields/sort/autocomplete)", None,
     _tabelas_de_indice),
    ("total_obras", "obras (biblio_records)", None, _total_obras),
    ("total_exemplares", "exemplares (biblio_holdings)", None, _total_exemplares),
    ("total_leitores", "leitores (users)", None, _total_leitores),
    ("total_emprestimos", "empréstimos (lendings)", None, _total_emprestimos),
    ("total_multas", "multas (lending_fines)", None, _total_multas),
    ("total_reservas", "reservas (reservations)", None, _total_reservas),
    ("tombos_por_ano", "tombos por prefixo e ano", None, _tombos_por_ano),
    ("prefixo_tombo", "prefixo de tombo em vigor", None, _prefixo_em_vigor),
]


def _desfazer(con) -> None:
    """Um erro aborta a transação no PostgreSQL; sem isto as checagens
    seguintes morrem todas com 'current transaction is aborted'."""
    try:
        con.rollback()
    except Exception:
        pass


def _rodar(con, chave: str, rotulo: str, esperado, funcao) -> dict:
    base = {"chave": chave, "rotulo": rotulo, "ok": None, "valor": None,
            "esperado": esperado, "detalhe": ""}
    try:
        with con.cursor() as cur:
            resultado = funcao(cur)
    except Exception as e:
        _desfazer(con)
        return {**base, "detalhe": _motivo(e)}
    return {**base, **resultado}


def conferir(con) -> dict:
    """
    -> {"checagens": [{"chave","rotulo","ok","valor","esperado","detalhe"}],
        "resumo": {"ok": n, "falhas": n, "nao_verificadas": n, "total": n}}

    Checagem que não pôde rodar (tabela ausente, permissão) volta com
    `ok=None` e o motivo — nunca derruba as outras. Só leitura.
    """
    checagens = [_rodar(con, *registro) for registro in _CHECAGENS]
    return {
        "checagens": checagens,
        "resumo": {
            "ok": sum(1 for c in checagens if c["ok"] is True),
            "falhas": sum(1 for c in checagens if c["ok"] is False),
            "nao_verificadas": sum(1 for c in checagens if c["ok"] is None),
            "total": len(checagens),
        },
    }
