"""
Um PostgreSQL de mentira, do tamanho exato do que a migração pergunta a ele.

O QUE ELE É
-----------
Um objeto com a cara de uma conexão psycopg2 que guarda em memória as quatro
tabelas que a carga escreve e responde às consultas que ela faz. Serve para
rodar `biblio.migracao.pipeline.gravar` inteiro — inclusive o casamento do
exemplar com a obra pelo 035 $a, que passa pelo MARC de verdade, serializado e
lido de volta.

O QUE ELE NÃO É
---------------
Não é um banco: não valida SQL, não tem tipo, chave estrangeira, unicidade nem
transação. Ele **não** substitui rodar contra um BibLivre real — a carga em
campo é que provou o SQL. O que ele impede é a regressão silenciosa do outro
lado: um argumento trocado, uma chave que mudou de nome, um mapa montado ao
contrário. Isso quebra na hora aqui, em vez de quebrar na biblioteca.

`execute_batch` (psycopg2.extras) monta o lote com `cur.mogrify` e manda tudo
numa `execute` só, então é no `mogrify` que as linhas são capturadas — não no
`execute`, que recebe os comandos já concatenados em bytes.
"""


class BancoFalso:
    """As tabelas que a migração escreve, em dicionários."""

    # O que uma instalação nova do BibLivre já traz em `users_fields`. Os nove
    # campos de `leitores.CAMPOS_NOVOS` não estão aqui de propósito: é o que
    # faz a carga exercitar a criação de campo e de tradução.
    CAMPOS_PADRAO = ["email", "id_rg", "id_cpf", "address", "address_number",
                     "address_zip", "address_city", "address_state",
                     "phone_home", "phone_cel", "gender", "birthday", "obs"]

    def __init__(self):
        self.registros: list[tuple] = []      # biblio_records
        self.holdings: list[tuple] = []       # biblio_holdings
        self.usuarios: list[tuple] = []
        self.valores: list[tuple] = []
        self.campos: list[str] = list(self.CAMPOS_PADRAO)
        self.traducoes: list[tuple] = []
        self.emprestimos: list[tuple] = []
        self.multas: list[tuple] = []
        self.reservas: list[tuple] = []
        self.commits = 0
        self.rollbacks = 0
        self._proximo_record = 0
        self._proximo_holding = 0

    # --- interface de conexão ---

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass

    # --- escrita ---

    def escrever(self, sql: str, args) -> None:
        if "INSERT INTO biblio_records" in sql:
            self.registros.append(args)              # (id, iso2709, ...)
        elif "INSERT INTO biblio_holdings" in sql:
            self._proximo_holding += 1
            self.holdings.append((self._proximo_holding, args))
        elif "INSERT INTO users_values" in sql:
            self.valores.append(args)
        elif "INSERT INTO users_fields" in sql:
            self.campos.append(args[0])
        elif "INSERT INTO users" in sql:
            self.usuarios.append(args)
        elif "INSERT INTO global.translations" in sql:
            self.traducoes.append(args)
        elif "INSERT INTO lendings" in sql:
            self.emprestimos.append(args)
        elif "INSERT INTO lending_fines" in sql:
            self.multas.append(args)
        elif "INSERT INTO reservations" in sql:
            self.reservas.append(args)

    # --- leitura ---

    def consultar(self, sql: str, args) -> list[tuple]:
        if "nextval('biblio_records_id_seq')" in sql:
            quantos = args[0] if args else 1
            inicio = self._proximo_record
            self._proximo_record += quantos
            return [(inicio + i + 1,) for i in range(quantos)]
        if "FROM biblio_records" in sql and "count(" not in sql:
            # (id, database, iso2709) — a ordem que `mapa_por_035` espera.
            return [(r[0], r[3], r[1]) for r in self.registros]
        if "SELECT accession_number, id FROM biblio_holdings" in sql:
            return [(args_[5], hid) for hid, args_ in self.holdings]
        if "SELECT accession_number FROM biblio_holdings" in sql:
            return [(args_[5],) for _, args_ in self.holdings]
        if "SELECT key FROM users_fields" in sql:
            return [(k,) for k in self.campos]
        if "SELECT id FROM users" in sql:
            return [(u[0],) for u in self.usuarios]
        if "coalesce(max(id), 0) FROM lendings" in sql:
            return [(0,)]
        if "count(*)" in sql:
            return [(0,)]
        # `configurations` (prefixo do tombo) e `translations` respondem vazio:
        # é uma base recém-instalada, sem prefixo alterado e sem tradução
        # customizada — o caminho que a migração de verdade encontra.
        return []


class _Cursor:
    def __init__(self, banco: BancoFalso):
        self.banco = banco
        self._resultado: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def mogrify(self, sql, args=None):
        self.banco.escrever(sql, args)
        return b"-- lote"

    def execute(self, sql, args=None):
        if isinstance(sql, (bytes, bytearray)):
            return  # lote de `execute_batch`: já capturado no mogrify
        if sql.lstrip().upper().startswith("SELECT"):
            self._resultado = self.banco.consultar(sql, args)
        else:
            self._resultado = []
            self.banco.escrever(sql, args)

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)

    def close(self):
        pass
