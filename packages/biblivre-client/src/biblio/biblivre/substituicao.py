"""
Substituir a base: apagar o que a migração carrega, para carregar de novo.

POR QUE EXISTE
--------------
A migração é carga de base nova: rodar um segundo `.bkp` por cima do primeiro
duplicaria o acervo, colidiria os ids explícitos de leitor e de empréstimo e —
com o tombo vindo do NUMACERVO — bateria no UNIQUE de `accession_number`. Só
que a biblioteca pode continuar no Biblioteca Fácil enquanto o BibLivre não
assume, e aí o natural é recarregar de tempos em tempos, valendo **o último
backup**. Este módulo é a metade "apagar" disso; a outra metade é a carga de
sempre, na mesma transação (`biblio.migracao.pipeline.gravar`).

O QUE APAGA — E O QUE NÃO
-------------------------
Tudo o que a migração escreve, inclusive o que foi feito no BibLivre ou no
balcão do app depois da carga anterior: obras (também as catalogadas por ISBN),
exemplares, leitores, empréstimos, multas e reservas. Recarregar é declarar que
o backup é a verdade, e uma obra nova que sobrevivesse ficaria com exemplar
apontando para o nada ou com empréstimo de leitor que não existe mais.

As tabelas de índice (`biblio_idx_*`) vão junto: índice apontando para
registro apagado é exatamente o "BibLivre bugado" — a busca acha o id e a
tela não acha a obra. Depois da carga o reindex reconstrói tudo.

Não toca em `logins` (os operadores continuam entrando), em `users_fields` e
nas traduções (os campos que a primeira carga criou continuam valendo, e por
isso a recarga não exige restart do Tomcat), em `users_types` nem em
`configurations`.

Sequences não voltam atrás: obra e exemplar continuam numerando de onde
estavam, e leitor e empréstimo — que entram com id explícito — já têm o
`setval` no fim da própria carga.

FALHA É ALTA, NUNCA PARCIAL
---------------------------
Não commita. Uma tabela do BibLivre que este módulo não conhece e que aponte
para uma das apagadas faz o `DELETE` estourar a FK; o erro sobe, quem chamou faz
`ROLLBACK`, e nada foi apagado. É de propósito que não há `TRUNCATE … CASCADE`:
cascata apagaria em silêncio o que ninguém conferiu.
"""

# Na ordem das FKs: quem aponta vem antes de quem é apontado.
# (tabela, rótulo para o relatório, obrigatória)
TABELAS = [
    ("lending_fines", "multas", True),
    ("lendings", "empréstimos", True),
    ("reservations", "reservas", True),
    ("biblio_idx_fields", "índice de busca", True),
    ("biblio_idx_sort", "índice de ordenação", True),
    ("biblio_idx_autocomplete", "índice de autocompletar", True),
    # Resultado de busca guardado pelo BibLivre: cache, com id de registro
    # dentro. Nem toda instalação tem; quando não tem, não é erro.
    ("biblio_search_results", "buscas em cache", False),
    ("biblio_holdings", "exemplares", True),
    ("biblio_records", "registros bibliográficos", True),
    ("users_values", "valores de campo de leitor", True),
    ("users", "leitores", True),
]


def contar(con) -> dict:
    """
    Quanto a substituição apagaria — para o relatório, antes de qualquer
    escrita. `obras_fora_da_migracao` é o que não veio de um `.bkp` (sem o
    `035 (BF)`): normalmente o que foi catalogado por ISBN depois da carga.
    """
    quantos: dict = {}
    with con.cursor() as cur:
        for tabela, _rotulo, obrigatoria in TABELAS:
            if not obrigatoria:
                continue
            cur.execute(f"SELECT count(*) FROM {tabela}")
            (quantos[tabela],) = cur.fetchone()
        cur.execute("SELECT count(*) FROM biblio_records "
                    "WHERE iso2709 NOT LIKE %s", ("%(BF)%",))
        (quantos["obras_fora_da_migracao"],) = cur.fetchone()
    return quantos


def apagar(con) -> dict:
    """
    Esvazia as tabelas da migração. Não commita.

    -> {tabela: linhas apagadas}. Tabela opcional ausente na instalação fica
    de fora do dicionário.
    """
    apagadas: dict = {}
    with con.cursor() as cur:
        for tabela, rotulo, obrigatoria in TABELAS:
            if obrigatoria:
                apagadas[tabela] = _apagar(cur, tabela, rotulo)
                continue
            # Opcional: isolada em savepoint, porque no PostgreSQL um erro
            # aborta a transação inteira — e tabela ausente não é motivo para
            # perder a carga.
            cur.execute("SAVEPOINT substituicao_opcional")
            try:
                apagadas[tabela] = _apagar(cur, tabela, rotulo)
            except Exception as e:
                if getattr(e, "pgcode", None) != "42P01":   # undefined_table
                    raise
                cur.execute("ROLLBACK TO SAVEPOINT substituicao_opcional")
            else:
                cur.execute("RELEASE SAVEPOINT substituicao_opcional")
    return apagadas


def _apagar(cur, tabela: str, rotulo: str) -> int:
    try:
        cur.execute(f"DELETE FROM {tabela}")
    except Exception as e:
        if getattr(e, "pgcode", None) == "23503":           # foreign_key_violation
            raise RuntimeError(
                f"Não deu para apagar {rotulo} ({tabela}): outra tabela do "
                f"BibLivre aponta para elas ({str(e).strip().splitlines()[0]}). "
                f"Nada foi apagado nem gravado.") from e
        raise
    return max(cur.rowcount or 0, 0)
