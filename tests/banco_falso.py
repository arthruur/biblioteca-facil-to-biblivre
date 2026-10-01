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

SÃO DOIS BANCOS DE MENTIRA NESTE ARQUIVO
----------------------------------------
`BancoFalso` é o da **migração**: escrita em lote, leitura mínima. `BancoBalcao`,
no fim do arquivo, é o da **circulação**: lê muito, escreve pouco e o que
escreve precisa aparecer na leitura seguinte, com transação e sequence de
mentira. Ver o comentário que abre a segunda metade para o porquê de serem dois
objetos e não um.
"""

import copy
import datetime as _dt
import re
import unicodedata


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
        self.rowcount = 0
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

    # `DELETE FROM <tabela>` da substituição -> a lista que guarda a tabela.
    # As de índice e de cache não existem aqui: apagar nelas é apagar nada.
    _TABELAS_APAGAVEIS = {
        "biblio_records": "registros", "biblio_holdings": "holdings",
        "users": "usuarios", "users_values": "valores",
        "lendings": "emprestimos", "lending_fines": "multas",
        "reservations": "reservas",
    }

    def escrever(self, sql: str, args) -> None:
        self.rowcount = 0
        apagar = re.match(r"\s*DELETE FROM (\w+)\s*$", sql)
        if apagar:
            atributo = self._TABELAS_APAGAVEIS.get(apagar.group(1))
            if atributo:
                self.rowcount = len(getattr(self, atributo))
                setattr(self, atributo, [])
            return
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

    @property
    def rowcount(self):
        return self.banco.rowcount

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
        # `(SELECT … ) UNION ALL (SELECT …)` também é consulta, e é a forma da
        # amostra de `verificacao._marc_vazio` — sem o parêntese na lista ela
        # cairia em `escrever` e voltaria vazia.
        if sql.lstrip().upper().startswith(("SELECT", "(SELECT", "WITH")):
            self._resultado = self.banco.consultar(sql, args)
        else:
            # `INSERT … RETURNING` precisa devolver linha: o balcão lê o id que
            # a sequence gerou. Quem não tem RETURNING devolve None e a lista
            # fica vazia, como antes.
            self._resultado = self.banco.escrever(sql, args) or []

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)

    def close(self):
        pass


# ==========================================================================
# O balcão: um segundo banco de mentira, para a circulação
# ==========================================================================
#
# `BancoFalso` acima nasceu para a MIGRAÇÃO, que é escrita em lote e quase não
# lê. A circulação é o contrário: lê muito (exemplar, leitor, situação,
# reservas), escreve pouco e o que escreve tem de aparecer na leitura seguinte
# — `emprestar` grava e `devolver` precisa achar a linha. Por isso o balcão tem
# um objeto próprio, `BancoBalcao`, em vez de mais um `elif` no de cima: são
# duas mentiras com forma diferente, e misturá-las faria a de lá parar de ser
# previsível.
#
# COMO ELE RESPONDE
# -----------------
# Não interpreta SQL: reconhece cada consulta por um pedaço característico do
# texto (normalizado, para indentação não importar) e responde com as colunas
# na ordem exata que o módulo desempacota. A regra que mantém isso honesto:
# consulta que ele NÃO conhece levanta `ConsultaDesconhecida` — nunca devolve
# lista vazia "por educação". Vazio silencioso viraria teste verde por motivo
# errado ("0 órfãos" quando a verdade é "não sei contar órfãos").
#
# O QUE ELE FINGE DE VERDADE (e é o que dá valor ao teste de fumaça)
#   * ids de `lendings` e `lending_fines` saindo de uma sequence, como o
#     `nextval` do BibLivre — e a sequence NÃO volta atrás no rollback, igual
#     ao Postgres;
#   * transação: `abrir()` tira uma foto das tabelas, `rollback()` restaura a
#     foto e `commit()` tira outra. É isso que permite provar que uma falha no
#     meio de uma renovação não deixa o empréstimo antigo fechado sem o novo;
#   * SAVEPOINT / ROLLBACK TO SAVEPOINT / RELEASE: os módulos isolam consulta
#     que pode não existir na instalação (`_tentar`, `_permissoes`) dentro de
#     savepoint, e sem emular isso o "rollback parcial" seria mentira boa
#     demais;
#   * `SELECT … FOR UPDATE` fica registrado em `travas`, para o teste poder
#     dizer que a gravação travou o exemplar antes de revalidar.
#
# O QUE ELE NÃO É
# ---------------
# Não é Postgres: não há tipo, FK, unicidade, concorrência nem plano de
# execução. Ele não prova que o SQL está correto — prova que o caminho entre
# rota, regra e tabela não se desalinhou. Um empréstimo de verdade só é
# provado contra a instalação da biblioteca.

class ConsultaDesconhecida(RuntimeError):
    """
    Consulta que o banco de mentira não sabe responder.

    Levantar é de propósito: dentro de `_tentar`/`_permissoes` (que é onde os
    módulos põem consulta opcional) isso vira exatamente o que uma tabela
    ausente vira na instalação real; fora de savepoint, estoura o teste e
    aponta a consulta que falta — as duas coisas são informação, e devolver
    `[]` no lugar seria ruído.
    """


class ComandoDesconhecido(RuntimeError):
    """Gravação que o banco de mentira não sabe aplicar."""


def _texto(sql) -> str:
    """SQL com espaço em branco normalizado: indentação não muda o sentido."""
    return " ".join(str(sql).split())


def _ascii(txt: str) -> str:
    """`users.name_ascii`, que a busca de leitor usa (`TextUtils`)."""
    return "".join(c for c in unicodedata.normalize("NFD", txt or "")
                   if not unicodedata.combining(c))


def _dia(valor):
    """Qualquer forma de data -> `datetime.date` (ou None)."""
    if valor in (None, ""):
        return None
    if isinstance(valor, _dt.datetime):
        return valor.date()
    if isinstance(valor, _dt.date):
        return valor
    return _dt.date.fromisoformat(str(valor).strip()[:10])


class BancoBalcao:
    """As tabelas que a circulação lê e escreve, em dicionários."""

    # Campos que uma instalação nova já traz em `users_fields`, mais o
    # `registration` que a migração cria (é por ele que `resolver` acha o
    # leitor pela carteirinha impressa).
    CAMPOS_PADRAO = list(BancoFalso.CAMPOS_PADRAO) + ["registration"]

    def __init__(self):
        self.obras: dict[int, dict] = {}
        self.exemplares: dict[int, dict] = {}
        self.leitores: dict[int, dict] = {}
        self.tipos: dict[int, dict] = {}
        self.emprestimos: list[dict] = []
        self.multas: list[dict] = []
        self.reservas: list[dict] = []
        self.logins: dict[str, dict] = {}
        self.valores: list[dict] = []
        self.campos: list[str] = list(self.CAMPOS_PADRAO)
        self.indice: set[int] = set()        # record_id em biblio_idx_fields
        self.configuracoes = {
            # O que o instalador semeia no schema `global`.
            "general.business_days": "2,3,4,5,6",
            "cataloging.accession_number_prefix": "Bib",
        }
        self.schema = "single"

        # Sequences: só o que for sobreposto na mão. O resto sai de max(id),
        # que é o estado de uma base sadia.
        self.sequencias: dict[str, tuple] = {}

        self.commits = 0
        self.rollbacks = 0
        self.gravacoes = 0                   # INSERT/UPDATE/DELETE aplicados
        self.travas: list[int] = []          # SELECT ... FOR UPDATE

        # Os dois defeitos que o teste injeta de propósito: um fragmento de SQL
        # que faz a gravação cair no meio (para provar o rollback) e outro que
        # faz a leitura cegar (é o que uma tabela ausente ou um GRANT que falta
        # produz na instalação real).
        self.explodir_em = ""
        self.cego_em = ""

        self._seq_emprestimo = 0
        self._seq_multa = 0
        self._seq_reserva = 0
        self._foto = None
        self._savepoints: dict[str, dict] = {}

    # --- semear ---------------------------------------------------------

    def tipo(self, tipo_id, nome, limite, dias, multa_dia=0.0):
        """`users_types`: limite de itens, prazo em dias e multa por dia."""
        self.tipos[tipo_id] = {"id": tipo_id, "nome": nome, "limite": limite,
                               "dias": dias, "multa_dia": multa_dia}
        return tipo_id

    def obra(self, record_id, titulo, autor="", iso2709="", database="main",
             indexada=True):
        self.obras[record_id] = {"id": record_id, "titulo": titulo,
                                 "autor": autor, "iso2709": iso2709,
                                 "database": database}
        if indexada:
            self.indice.add(record_id)
        return record_id

    def exemplar(self, holding_id, record_id, tombo, disponibilidade="available",
                 volume="", database="main"):
        self.exemplares[holding_id] = {
            "id": holding_id, "record_id": record_id, "tombo": tombo,
            "disponibilidade": disponibilidade, "volume": volume,
            "database": database, "iso2709": f"exemplar {tombo}",
        }
        return holding_id

    def leitor(self, user_id, nome, status="active", tipo=1, matricula=""):
        self.leitores[user_id] = {"id": user_id, "nome": nome,
                                  "status": status, "tipo": tipo}
        if matricula:
            self.valores.append({"user_id": user_id, "key": "registration",
                                 "value": matricula})
        return user_id

    def emprestimo(self, holding_id, user_id, previsto, criado=None,
                   devolvido=None, operador=1, anterior=None):
        """Uma linha de `lendings` já existente (a base migrada tem 19 mil)."""
        self._seq_emprestimo += 1
        linha = {
            "id": self._seq_emprestimo, "holding_id": holding_id,
            "user_id": user_id, "anterior": anterior,
            "previsto": _dia(previsto),
            "criado": criado or _dt.datetime.now(),
            "devolvido": devolvido, "criado_por": operador,
        }
        self.emprestimos.append(linha)
        return linha["id"]

    def multa(self, user_id, lending_id, valor, pago_em=None, operador=1):
        self._seq_multa += 1
        self.multas.append({"id": self._seq_multa, "user_id": user_id,
                            "lending_id": lending_id, "valor": valor,
                            "pago_em": pago_em, "criado_por": operador})
        return self._seq_multa

    def reserva(self, record_id, user_id, expira=None, criada=None):
        self._seq_reserva += 1
        self.reservas.append({"id": self._seq_reserva, "record_id": record_id,
                              "user_id": user_id, "expira": expira,
                              "criada": criada or _dt.datetime.now()})
        return self._seq_reserva

    def login(self, login, senha_hash, login_id, nome="", employee=True,
              permissoes=()):
        """`logins` + `permissions`, que é onde `operador.autenticar` olha."""
        self.logins[login] = {"id": login_id, "login": login,
                              "senha": senha_hash, "employee": employee,
                              "nome": nome or login,
                              "permissoes": list(permissoes)}
        return login_id

    # --- interface de conexão -------------------------------------------

    def cursor(self):
        return _Cursor(self)

    def abrir(self):
        """
        O que `conexao.conectar()` devolveria: a conexão com transação nova.

        Tirar a foto aqui, e não no primeiro `execute`, é o que faz o
        `rollback` do router desfazer a operação inteira.
        """
        self._foto = self._copia()
        self._savepoints.clear()
        return self

    def commit(self):
        self.commits += 1
        self._foto = self._copia()
        self._savepoints.clear()

    def rollback(self):
        self.rollbacks += 1
        if self._foto is not None:
            self._restaurar(self._foto)
        self._savepoints.clear()

    def close(self):
        pass

    # --- a foto das tabelas ---------------------------------------------

    _TABELAS = ("obras", "exemplares", "leitores", "tipos", "emprestimos",
                "multas", "reservas", "valores", "campos", "indice",
                "configuracoes")

    def _copia(self) -> dict:
        return {nome: copy.deepcopy(getattr(self, nome)) for nome in self._TABELAS}

    def _restaurar(self, foto: dict) -> None:
        for nome, valor in foto.items():
            setattr(self, nome, copy.deepcopy(valor))

    # --- leitura de apoio -----------------------------------------------

    def _por_tombo(self, tombo: str):
        for ex in self.exemplares.values():
            if (ex["tombo"] or "") == tombo:
                return ex
        return None

    def aberto_do_exemplar(self, holding_id):
        """`getCurrentLending`: o último empréstimo sem devolução."""
        abertos = [e for e in self.emprestimos
                   if e["holding_id"] == holding_id and e["devolvido"] is None]
        return max(abertos, key=lambda e: e["id"]) if abertos else None

    def por_id(self, lending_id):
        for e in self.emprestimos:
            if e["id"] == lending_id:
                return e
        return None

    def _tipo_do_leitor(self, leitor: dict) -> dict:
        return self.tipos.get(leitor.get("tipo"), {})

    def _abertos(self, user_id) -> list:
        return [e for e in self.emprestimos
                if e["user_id"] == user_id and e["devolvido"] is None]

    def _atrasados(self, user_id) -> list:
        hoje = _dt.date.today()
        return [e for e in self._abertos(user_id)
                if e["previsto"] and e["previsto"] < hoje]

    def _multas_abertas(self, user_id) -> list:
        return [m for m in self.multas
                if m["user_id"] == user_id and m["valor"] > 0
                and m["pago_em"] is None]

    def _reservas_vivas(self, record_id) -> list:
        agora = _dt.datetime.now()
        vivas = [r for r in self.reservas
                 if r["record_id"] == record_id
                 and (r["expira"] is None or r["expira"] > agora)]
        return sorted(vivas, key=lambda r: r["criada"])

    def _ids(self, tabela: str) -> list:
        if tabela == "biblio_records":
            return list(self.obras)
        if tabela == "biblio_holdings":
            return list(self.exemplares)
        if tabela == "lendings":
            return [e["id"] for e in self.emprestimos]
        if tabela == "users":
            return list(self.leitores)
        raise ConsultaDesconhecida(f"max(id) de tabela desconhecida: {tabela}")

    def _sequencia(self, nome: str) -> tuple:
        if nome in self.sequencias:
            return self.sequencias[nome]
        tabela = nome[:-len("_id_seq")] if nome.endswith("_id_seq") else nome
        maior = max(self._ids(tabela), default=0)
        # Base sadia: a sequence já entregou o maior id gravado.
        return (maior, True)

    # --- gravação -------------------------------------------------------

    def escrever(self, sql: str, args):
        texto = _texto(sql)

        if self.explodir_em and self.explodir_em in texto:
            raise RuntimeError(
                f"banco de mentira caiu de propósito em: {texto[:60]}…")

        if texto.startswith("SAVEPOINT "):
            self._savepoints[texto.split()[-1]] = self._copia()
            return []
        if texto.startswith("ROLLBACK TO SAVEPOINT "):
            foto = self._savepoints.pop(texto.split()[-1], None)
            if foto is not None:
                self._restaurar(foto)
            return []
        if texto.startswith("RELEASE SAVEPOINT "):
            self._savepoints.pop(texto.split()[-1], None)
            return []

        self.gravacoes += 1      # daqui para baixo é escrita de verdade

        if texto.startswith("INSERT INTO lendings"):
            holding_id, user_id, anterior, previsto, criado_por = args
            self._seq_emprestimo += 1        # nextval: não volta no rollback
            linha = {"id": self._seq_emprestimo, "holding_id": holding_id,
                     "user_id": user_id, "anterior": anterior,
                     "previsto": _dia(previsto),
                     "criado": _dt.datetime.now().replace(microsecond=0),
                     "devolvido": None, "criado_por": criado_por}
            self.emprestimos.append(linha)
            # RETURNING id, created, expected_return_date
            return [(linha["id"], linha["criado"], linha["previsto"])]

        if texto.startswith("UPDATE lendings SET return_date"):
            linha = self.por_id(args[0])
            if linha is None or linha["devolvido"] is not None:
                return []                    # o WHERE não pegou nenhuma linha
            linha["devolvido"] = _dt.datetime.now().replace(microsecond=0)
            # RETURNING return_date, expected_return_date, user_id, holding_id
            return [(linha["devolvido"], linha["previsto"], linha["user_id"],
                     linha["holding_id"])]

        if texto.startswith("INSERT INTO lending_fines"):
            user_id, lending_id, valor, criado_por = args
            self._seq_multa += 1
            self.multas.append({"id": self._seq_multa, "user_id": user_id,
                                "lending_id": lending_id, "valor": valor,
                                "pago_em": None, "criado_por": criado_por})
            return [(self._seq_multa,)]

        if texto.startswith("DELETE FROM reservations"):
            # `ReservationDAO.delete`: UMA reserva, a que expira primeiro.
            user_id, record_id = args
            candidatas = [r for r in self.reservas
                          if r["user_id"] == user_id
                          and r["record_id"] == record_id
                          and r["expira"] is not None
                          and r["expira"] > _dt.datetime.now()]
            if candidatas:
                alvo = min(candidatas, key=lambda r: r["expira"])
                self.reservas.remove(alvo)
            return []

        raise ComandoDesconhecido(f"gravação não prevista: {texto[:80]}…")

    # --- leitura --------------------------------------------------------

    def consultar(self, sql: str, args):
        texto = _texto(sql)
        args = tuple(args or ())

        if self.cego_em and self.cego_em in texto:
            raise ConsultaDesconhecida(
                f"tabela indisponível de propósito em: {texto[:60]}…")

        def tem(*pedacos):
            return all(p in texto for p in pedacos)

        # ---------------- circulação: o exemplar e a obra ----------------

        if tem("h.location_d, r.iso2709"):
            return self._q_exemplar(texto, args)
        if tem("WHERE h.record_id = %s"):
            return self._q_exemplares_da_obra(args[0])
        if tem("FROM biblio_holdings WHERE id = %s FOR UPDATE"):
            ex = self.exemplares.get(args[0])
            if ex is None:
                return []
            self.travas.append(ex["id"])
            return [(ex["id"], ex["record_id"], ex["disponibilidade"])]
        if tem("translate(r.iso2709, %s, %s) ILIKE %s"):
            # (acentos, sem acentos, %palavra%) por palavra, e o LIMIT no fim
            palavras = [str(args[i]).strip("%").lower()
                        for i in range(2, len(args) - 1, 3)]
            saida = []
            for obra in sorted(self.obras.values(), key=lambda o: o["id"]):
                cru = _ascii(obra["iso2709"] or "").lower()
                if obra["database"] == "main" and all(w in cru for w in palavras):
                    saida.append((obra["id"], obra["iso2709"]))
            return saida[:args[-1]]
        if tem("iso2709 LIKE %s"):
            alvo = str(args[0]).strip("%")
            for obra in self.obras.values():
                if obra["database"] == "main" and alvo in (obra["iso2709"] or ""):
                    return [(obra["id"], obra["iso2709"])]
            return []

        # ---------------- circulação: o leitor ---------------------------

        if tem("t.lending_time_limit"):
            return self._q_leitor(args[0])
        if tem("FROM lendings WHERE user_id = %s AND return_date IS NULL"):
            return [(len(self._abertos(args[0])), len(self._atrasados(args[0])))]
        if tem("FROM lending_fines WHERE user_id = %s", "payment_date IS NULL"):
            abertas = self._multas_abertas(args[0])
            return [(round(sum(m["valor"] for m in abertas), 2), len(abertas))]
        if tem("WHERE l.user_id = %s AND l.return_date IS NULL"):
            return self._q_emprestimos_do_leitor(args[0])
        if tem("SELECT id FROM users WHERE id = %s"):
            return [(args[0],)] if args[0] in self.leitores else []
        if tem("FROM users_values WHERE key = 'registration'"):
            for v in self.valores:
                if v["key"] == "registration" and v["value"] == args[0]:
                    return [(v["user_id"],)]
            return []
        if tem("u.name_ascii ILIKE %s"):
            return self._q_procurar(por_nome=str(args[1]).strip("%"),
                                    limite=args[2])
        if tem("WHERE u.status <> %s AND u.id = %s"):
            return self._q_procurar(por_id=args[1], limite=args[2])

        # ---------------- circulação: reservas ---------------------------

        if tem("r.user_id <> %s"):
            saida = [(r["id"], r["user_id"],
                      self.leitores.get(r["user_id"], {}).get("nome"),
                      r["expira"], r["criada"])
                     for r in self._reservas_vivas(args[0])
                     if r["user_id"] != args[1]]
            return saida[:5]
        if tem("FROM reservations r", "ORDER BY r.created ASC LIMIT 1"):
            vivas = self._reservas_vivas(args[0])
            if not vivas:
                return []
            r = vivas[0]
            return [(r["id"], r["user_id"],
                     self.leitores.get(r["user_id"], {}).get("nome"),
                     r["expira"])]

        # ---------------- circulação: empréstimos por id -----------------

        if tem("SELECT holding_id, return_date FROM lendings WHERE id = %s"):
            linha = self.por_id(args[0])
            return [] if linha is None else [(linha["holding_id"],
                                              linha["devolvido"])]
        if tem("SELECT holding_id, user_id, return_date, expected_return_date "
               "FROM lendings WHERE id = %s"):
            linha = self.por_id(args[0])
            return [] if linha is None else [
                (linha["holding_id"], linha["user_id"], linha["devolvido"],
                 linha["previsto"])]

        # ---------------- pendências -------------------------------------

        if tem("coalesce(t.fine_value, 0)"):
            return self._q_pendencias(texto, args[-1])
        if tem("SELECT count(*) FROM lendings l WHERE l.return_date IS NULL AND"):
            return [(len(self._pendentes(texto)),)]

        # ---------------- operador ---------------------------------------

        if tem("FROM logins l"):
            achado = self.logins.get(args[0])
            if achado is None:
                return []
            return [(achado["id"], achado["login"], achado["senha"],
                     achado["employee"], achado["nome"])]
        if tem("SELECT permission FROM permissions WHERE login_id = %s"):
            for dados in self.logins.values():
                if dados["id"] == args[0]:
                    return [(p,) for p in dados["permissoes"]]
            return []

        # ---------------- configuração e schema --------------------------

        if tem("configurations WHERE key = %s"):
            valor = self.configuracoes.get(args[0])
            return [(valor,)] if valor is not None else []
        if tem("current_schema()"):
            return [(self.schema,)]

        # ---------------- conferência (verificacao.conferir) -------------

        resposta = self._q_conferencia(texto, tem)
        if resposta is not None:
            return resposta

        raise ConsultaDesconhecida(f"consulta não prevista: {texto[:100]}…")

    # --- circulação: montagem das linhas --------------------------------

    def _q_exemplar(self, texto: str, args) -> list:
        """`_SQL_EXEMPLAR`: 13 colunas, na ordem que `_montar_exemplar` abre."""
        if "WHERE h.accession_number = %s" in texto:
            ex = self._por_tombo(str(args[0]))
        else:
            ex = self.exemplares.get(args[0])
        if ex is None:
            return []
        obra = self.obras.get(ex["record_id"], {})
        aberto = self.aberto_do_exemplar(ex["id"])
        leitor = self.leitores.get(aberto["user_id"], {}) if aberto else {}
        return [(
            ex["id"], ex["record_id"], ex["tombo"], ex["disponibilidade"],
            ex["database"], ex["volume"], obra.get("iso2709"),
            aberto["id"] if aberto else None,
            aberto["user_id"] if aberto else None,
            aberto["previsto"] if aberto else None,
            aberto["criado"] if aberto else None,
            aberto["anterior"] if aberto else None,
            leitor.get("nome") if aberto else None,
        )]

    def _q_exemplares_da_obra(self, record_id) -> list:
        """`_SQL_EXEMPLARES_DA_OBRA`: 9 colunas, ordenado por tombo."""
        itens = sorted((e for e in self.exemplares.values()
                        if e["record_id"] == record_id),
                       key=lambda e: (e["tombo"] or "", e["id"]))
        saida = []
        for ex in itens:
            aberto = self.aberto_do_exemplar(ex["id"])
            leitor = self.leitores.get(aberto["user_id"], {}) if aberto else {}
            saida.append((
                ex["id"], ex["tombo"], ex["disponibilidade"], ex["volume"],
                ex["database"],
                aberto["id"] if aberto else None,
                aberto["user_id"] if aberto else None,
                aberto["previsto"] if aberto else None,
                leitor.get("nome") if aberto else None,
            ))
        return saida

    def _q_leitor(self, user_id) -> list:
        """`_SQL_LEITOR`: 8 colunas (leitor + tipo)."""
        leitor = self.leitores.get(user_id)
        if leitor is None:
            return []
        tipo = self._tipo_do_leitor(leitor)
        return [(leitor["id"], leitor["nome"], leitor["status"], leitor["tipo"],
                 tipo.get("nome"), tipo.get("limite"), tipo.get("dias"),
                 tipo.get("multa_dia"))]

    def _q_emprestimos_do_leitor(self, user_id) -> list:
        """`_SQL_EMPRESTIMOS_DO_LEITOR`: 8 colunas, por prazo."""
        abertos = sorted(self._abertos(user_id),
                         key=lambda e: (e["previsto"] or _dt.date.max, e["id"]))
        saida = []
        for e in abertos:
            ex = self.exemplares.get(e["holding_id"], {})
            obra = self.obras.get(ex.get("record_id"), {})
            saida.append((e["id"], e["holding_id"], e["previsto"], e["criado"],
                          e["anterior"], ex.get("tombo"), ex.get("record_id"),
                          obra.get("iso2709")))
        return saida

    def _q_procurar(self, por_nome=None, por_id=None, limite=20) -> list:
        """`_SQL_PROCURAR_*`: 7 colunas; inativo fica escondido, como no DAO."""
        achados = []
        for leitor in self.leitores.values():
            if leitor["status"] == "inactive":
                continue
            if por_id is not None and leitor["id"] != por_id:
                continue
            if por_nome is not None and _ascii(por_nome).lower() not in \
                    _ascii(leitor["nome"]).lower():
                continue
            achados.append(leitor)
        achados.sort(key=lambda x: (x["nome"] or "").upper())
        saida = []
        for leitor in achados[:limite]:
            tipo = self._tipo_do_leitor(leitor)
            saida.append((leitor["id"], leitor["nome"], leitor["status"],
                          tipo.get("nome"), tipo.get("limite"),
                          len(self._abertos(leitor["id"])),
                          len(self._atrasados(leitor["id"]))))
        return saida

    def _pendentes(self, texto: str) -> list:
        hoje = _dt.date.today()
        abertos = [e for e in self.emprestimos if e["devolvido"] is None]
        if "l.expected_return_date < now()" in texto:
            abertos = [e for e in abertos if e["previsto"] and e["previsto"] < hoje]
        elif "l.expected_return_date::date = current_date" in texto:
            abertos = [e for e in abertos if e["previsto"] == hoje]
        return sorted(abertos, key=lambda e: (e["previsto"] or _dt.date.max,
                                              e["id"]))

    def _q_pendencias(self, texto: str, limite) -> list:
        """`_SQL_PENDENCIAS`: 11 colunas."""
        saida = []
        for e in self._pendentes(texto)[:limite]:
            ex = self.exemplares.get(e["holding_id"], {})
            obra = self.obras.get(ex.get("record_id"), {})
            leitor = self.leitores.get(e["user_id"], {})
            tipo = self._tipo_do_leitor(leitor) if leitor else {}
            saida.append((e["id"], e["holding_id"], e["user_id"], e["previsto"],
                          e["criado"], e["anterior"], ex.get("tombo"),
                          ex.get("record_id"), obra.get("iso2709"),
                          leitor.get("nome"), tipo.get("multa_dia") or 0))
        return saida

    # --- conferência (as consultas de `verificacao.conferir`) -----------

    def _q_conferencia(self, texto: str, tem):
        """
        As consultas de `biblio.biblivre.verificacao`, contadas em Python.

        Devolve None quando não é nenhuma delas — quem chama levanta. Cada
        checagem tem uma consulta de CONTAGEM e, quando ela não dá zero, uma de
        AMOSTRA; as duas estão aqui, senão uma falha injetada no teste voltaria
        como "não deu para verificar" em vez de "falhou".
        """
        obras = list(self.obras.values())
        exemplares = list(self.exemplares.values())

        # 1. o índice: obra sem linha em biblio_idx_fields
        fora = sorted(o["id"] for o in obras if o["id"] not in self.indice)
        if tem("count(*) FROM biblio_records r",
               "NOT EXISTS (SELECT 1 FROM biblio_idx_fields i"):
            return [(len(fora),)]
        if tem("SELECT r.id, r.database FROM biblio_records r",
               "biblio_idx_fields"):
            return [(i, self.obras[i]["database"]) for i in fora[:10]]
        if tem("(SELECT count(*) FROM biblio_idx_fields)"):
            # fields, sort, autocomplete — autocomplete 0 é o correto.
            return [(len(self.indice), len(self.indice), 0)]

        # 2. sequences
        if tem("coalesce(max(id), 0) FROM"):
            tabela = texto.split('"')[1]
            return [(max(self._ids(tabela), default=0),)]
        if tem("SELECT last_value, is_called FROM"):
            return [self._sequencia(texto.split('"')[1])]

        # 3. integridade obra/exemplar
        orfaos = [e for e in exemplares if e["record_id"] not in self.obras]
        if tem("count(*) FROM biblio_holdings h",
               "NOT EXISTS (SELECT 1 FROM biblio_records r"):
            return [(len(orfaos),)]
        if tem("SELECT h.id, h.accession_number, h.record_id FROM biblio_holdings h"):
            return [(e["id"], e["tombo"], e["record_id"]) for e in orfaos[:10]]

        com_exemplar = {e["record_id"] for e in exemplares}
        sem_exemplar = sorted(o["id"] for o in obras
                              if o["database"] == "main"
                              and o["id"] not in com_exemplar)
        if tem("count(*) FROM biblio_records r", "r.database = 'main' AND NOT EXISTS"):
            return [(len(sem_exemplar),)]
        if tem("SELECT r.id FROM biblio_records r",
               "r.database = 'main' AND NOT EXISTS"):
            return [(i,) for i in sem_exemplar[:10]]

        repetidos = {}
        for e in exemplares:
            repetidos[e["tombo"]] = repetidos.get(e["tombo"], 0) + 1
        duplicados = sorted(((t, n) for t, n in repetidos.items() if n > 1),
                            key=lambda tn: (-tn[1], tn[0]))
        if tem("GROUP BY accession_number HAVING count(*) > 1) d"):
            return [(len(duplicados),)]
        if tem("SELECT accession_number, count(*) FROM biblio_holdings"):
            return duplicados[:10]

        brancos = [e for e in exemplares if not (e["tombo"] or "").strip()]
        if tem("count(*) FROM biblio_holdings",
               "btrim(accession_number) = ''"):
            return [(len(brancos),)]
        if tem("SELECT id, record_id FROM biblio_holdings",
               "accession_number IS NULL"):
            return [(e["id"], e["record_id"]) for e in brancos[:10]]

        divergentes = [e for e in exemplares
                       if e["record_id"] in self.obras
                       and (e["database"] or "")
                       != (self.obras[e["record_id"]]["database"] or "")]
        if tem("coalesce(h.database, '') <> coalesce(r.database, '')", "count(*)"):
            return [(len(divergentes),)]
        if tem("SELECT h.id, h.database, r.database"):
            return [(e["id"], e["database"],
                     self.obras[e["record_id"]]["database"])
                    for e in divergentes[:10]]

        obras_sem_marc = [o for o in obras if not (o["iso2709"] or "").strip()]
        ex_sem_marc = [e for e in exemplares if not (e["iso2709"] or "").strip()]
        if tem("(SELECT count(*) FROM biblio_records", "btrim(iso2709) = ''"):
            return [(len(obras_sem_marc), len(ex_sem_marc))]
        if tem("(SELECT 'obra' AS tipo, id FROM biblio_records"):
            return ([("obra", o["id"]) for o in obras_sem_marc[:5]]
                    + [("exemplar", e["id"]) for e in ex_sem_marc[:5]])

        # 4. leitores e circulação
        chaves_orfas = {}
        for v in self.valores:
            if v["key"] not in self.campos:
                chaves_orfas[v["key"]] = chaves_orfas.get(v["key"], 0) + 1
        if tem("count(*) FROM users_values v", "NOT EXISTS"):
            return [(sum(chaves_orfas.values()),)]
        if tem("SELECT v.key, count(*) FROM users_values v"):
            return sorted(chaves_orfas.items(), key=lambda kn: (-kn[1], kn[0]))[:10]

        sem_exemplar_l = [e for e in self.emprestimos
                          if e["holding_id"] not in self.exemplares]
        if tem("count(*) FROM lendings l",
               "NOT EXISTS (SELECT 1 FROM biblio_holdings h"):
            return [(len(sem_exemplar_l),)]
        if tem("SELECT l.id, l.holding_id FROM lendings l", "NOT EXISTS"):
            return [(e["id"], e["holding_id"]) for e in sem_exemplar_l[:10]]

        sem_leitor = [e for e in self.emprestimos
                      if e["user_id"] not in self.leitores]
        if tem("count(*) FROM lendings l", "NOT EXISTS (SELECT 1 FROM users u"):
            return [(len(sem_leitor),)]
        if tem("SELECT l.id, l.user_id FROM lendings l", "NOT EXISTS"):
            return [(e["id"], e["user_id"]) for e in sem_leitor[:10]]

        ids_emprestimo = {e["id"] for e in self.emprestimos}
        multas_orfas = [m for m in self.multas
                        if m["lending_id"] not in ids_emprestimo]
        if tem("count(*) FROM lending_fines f", "NOT EXISTS"):
            return [(len(multas_orfas),)]
        if tem("SELECT f.lending_id, f.user_id FROM lending_fines f"):
            return [(m["lending_id"], m["user_id"]) for m in multas_orfas[:10]]

        reservas_orfas = [r for r in self.reservas
                          if r["record_id"] not in self.obras
                          or r["user_id"] not in self.leitores]
        if tem("count(*) FROM reservations s", "NOT EXISTS"):
            return [(len(reservas_orfas),)]
        if tem("SELECT s.record_id, s.user_id FROM reservations s"):
            return [(r["record_id"], r["user_id"]) for r in reservas_orfas[:10]]

        por_exemplar = {}
        for e in self.emprestimos:
            if e["devolvido"] is None:
                por_exemplar[e["holding_id"]] = por_exemplar.get(e["holding_id"], 0) + 1
        dobrados = sorted(((h, n) for h, n in por_exemplar.items() if n > 1),
                          key=lambda hn: (-hn[1], hn[0]))
        if tem("GROUP BY holding_id HAVING count(*) > 1) d"):
            return [(len(dobrados),)]
        if tem("SELECT l.holding_id, count(*) FROM lendings l",
               "l.return_date IS NULL"):
            return dobrados[:10]

        # 5. contagens de referência
        if tem("SELECT database, count(*) FROM biblio_records"):
            return self._agrupar(o["database"] for o in obras)
        if tem("SELECT availability, count(*) FROM biblio_holdings"):
            return self._agrupar(e["disponibilidade"] for e in exemplares)
        if tem("SELECT status, count(*) FROM users GROUP BY status"):
            return self._agrupar(l["status"] for l in self.leitores.values())
        if tem("sum(CASE WHEN return_date IS NULL THEN 1 ELSE 0 END)"):
            abertos = sum(1 for e in self.emprestimos if e["devolvido"] is None)
            return [(len(self.emprestimos), abertos)]
        if tem("sum(CASE WHEN payment_date IS NOT NULL THEN 1 ELSE 0 END)"):
            pagas = sum(1 for m in self.multas if m["pago_em"] is not None)
            return [(len(self.multas), pagas,
                     round(sum(m["valor"] for m in self.multas), 2))]
        if tem("FROM reservations", "expires < current_date"):
            hoje = _dt.date.today()
            vencidas = sum(1 for r in self.reservas
                           if r["expira"] and _dia(r["expira"]) < hoje)
            return [(len(self.reservas), vencidas)]

        # 6. tombos por prefixo e ano
        if tem("substring(accession_number from"):
            grupos = {}
            for e in exemplares:
                achado = re.match(r"^(.*)\.(\d{4})\.\d+$", e["tombo"] or "")
                chave = (achado.group(1), achado.group(2)) if achado else (None, None)
                grupos[chave] = grupos.get(chave, 0) + 1
            return [(p, a, n) for (p, a), n in sorted(
                grupos.items(), key=lambda item: (item[0][0] or "",
                                                  item[0][1] or ""))]

        return None

    @staticmethod
    def _agrupar(valores) -> list:
        contagem = {}
        for v in valores:
            contagem[v] = contagem.get(v, 0) + 1
        return sorted(contagem.items(), key=lambda kn: (kn[0] or ""))
