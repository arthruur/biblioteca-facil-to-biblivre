"""
Quem está no balcão: autenticação contra a tabela `logins` do BibLivre.

    from biblio.biblivre import conexao, operador

    con = conexao.conectar()
    quem = operador.autenticar(con, "bibliotecaria", "...")
    token = operador.abrir_sessao(quem)     # vive em memória, some no restart

POR QUE ISTO PASSOU A EXISTIR
-----------------------------
O app não tinha login, e não precisava: ele catalogava, e catálogo errado se
conserta. Registrar empréstimo muda duas coisas.

  * `lendings.created_by` precisa dizer **quem** emprestou. A migração grava
    `1` (o admin do instalador, ver `conexao.USUARIO_PADRAO`), e para o dia a
    dia isso é perder informação de balcão.
  * Sem barreira nenhuma, qualquer celular na rede da biblioteca registra
    empréstimo em nome de qualquer leitor.

A saída é não inventar cadastro: o BibLivre já tem `logins`. Autenticar contra
ela dá o `logins.id` verdadeiro — o `created_by` passa a fazer sentido dentro
do próprio BibLivre, inclusive nas telas dele — e é uma senha a menos para a
biblioteca administrar: quem sai de férias é desligado num lugar só.

O HASH, VERIFICADO NO FONTE
---------------------------
`login/LoginBO.java:44` chama `TextUtils.encodePassword(password)` e manda o
resultado para o `WHERE`. Em `core/utils/TextUtils.java:39-53`:

    MessageDigest md = MessageDigest.getInstance("SHA");   // "SHA" == SHA-1
    md.update(password.getBytes("UTF-8"));                 // UTF-8, sem trim
    byte[] pass = new Base64().encode(md.digest());        // Base64 padrão

Ou seja: **SHA-1 do texto em UTF-8, em Base64 padrão** (com o `=` de padding,
sem quebra de linha). Nada de salt, nada de iteração — é fraco, mas é o que o
BibLivre grava, e o objetivo aqui é falar a mesma língua que ele, não inventar
um esquema que a tela dele não entenderia.

A prova cabe numa linha e está no `if __name__ == "__main__"` do fim do
arquivo: `WebContent/biblivre_template_4.0.0.sql` (linha 3019) semeia

    INSERT INTO logins (id, login, employee, password, ...) VALUES
        (1, 'admin', true, 'C4wx3TpMHnSwdk1bUQ/V6qwAQmw=', ...);

e `hash_senha("abracadabra")` tem de dar exatamente essa string. Se der, o
módulo inteiro está certo; se não der, nenhum login do BibLivre entra aqui.

A TABELA `logins` (mesmo arquivo, linhas 1184-1193)
---------------------------------------------------
    id, login, employee, password, created, created_by, modified, modified_by

Repare no que **não** existe:

  * não há coluna `name`. O nome que a tela mostra vem de `users`, pelo
    `LEFT JOIN users U ON U.login_id = L.id` de `LoginDAO.login`
    (`login/LoginDAO.java:79-81`), com `coalesce(U.name, L.login)`. Login de
    funcionário sem ficha de leitor mostra o próprio login, e está certo.
  * não há coluna de status/ativo. Desativar alguém no BibLivre é **apagar** a
    linha (`LoginDAO.delete` zera `users.login_id` e faz `DELETE FROM logins`).
    Não existe login desabilitado — existe login ou não existe.
  * não há contador de tentativas nem expiração de senha. Bloqueio por força
    bruta não existe no BibLivre; a única sessão dele é a do Tomcat
    (JSESSIONID). Este módulo também não implementa bloqueio — fica registrado
    como decisão consciente, não como esquecimento.

`employee` é o que separa funcionário de leitor com senha: em
`core/auth/AuthorizationPoints.java:353-373`, um login com `employee = false`
sequer recebe os pontos de autorização de escopo EMPLOYEE — entre eles
`CIRCULATION_LENDING_LEND`. Daí `autenticar` devolver `employee`, `permissoes`
e o derivado `pode_emprestar`: quem monta a resposta HTTP (o router de sessão,
pacote A8) tem como recusar um leitor tentando abrir o balcão sem reler o fonte
Java. `admin` é `logins.id == 1`, como faz `login/Handler.java:66`.

SESSÃO EM MEMÓRIA, E POR QUÊ
----------------------------
Mesma postura da senha do Postgres em `conexao.py`: **nada em disco**. Token
guardado em arquivo ou em tabela é token que sobrevive ao processo, vaza em
backup e pede rotina de limpeza. Aqui o dicionário morre com o processo, e
reiniciar o servidor desloga todo mundo — o custo é a bibliotecária digitar a
senha de novo, uma vez, o que numa biblioteca de um balcão é troco perto de
manter credencial persistida.

A expiração é por **inatividade**, não por idade: 12h, o turno da biblioteca.
Sessão parada além disso morre; sessão em uso não incomoda ninguém no meio do
expediente.

REGRA DO PACOTE: nada aqui commita — e este módulo nem escreve: só lê
`logins`, `users` e `permissions`.
"""

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

# O hash que o instalador semeia para `admin` / `abracadabra`
# (WebContent/biblivre_template_4.0.0.sql). É a prova de `hash_senha` e também
# um aviso: instalação que ainda tem este hash está com a senha pública do
# BibLivre em vigor.
HASH_ADMIN_PADRAO = "C4wx3TpMHnSwdk1bUQ/V6qwAQmw="
SENHA_PADRAO = "abracadabra"

# Permissões da tabela `permissions` que o BibLivre exige no balcão
# (`AuthorizationPointTypes`).
PERMISSAO_EMPRESTAR = "CIRCULATION_LENDING_LEND"
PERMISSAO_DEVOLVER = "CIRCULATION_LENDING_RETURN"

# `logins.id` do admin do instalador: o BibLivre trata este id como
# administrador sem consultar `permissions` (login/Handler.java:66).
ID_ADMIN = 1


def _horas_inatividade() -> float:
    """12h por padrão — o turno da biblioteca. `BIBLIO_SESSAO_HORAS` ajusta."""
    try:
        horas = float(os.environ.get("BIBLIO_SESSAO_HORAS") or "")
    except ValueError:
        return 12.0
    return horas if horas > 0 else 12.0


INATIVIDADE_SEGUNDOS = _horas_inatividade() * 3600

# Teto de sessões vivas. Não é regra de negócio: é para um cliente em laço não
# transformar o dicionário em vazamento de memória.
MAX_SESSOES = 200

_lock = threading.Lock()
_sessoes: dict[str, dict] = {}


# --- hash ---------------------------------------------------------------

def hash_senha(senha: str) -> str:
    """
    O mesmo hash que o BibLivre grava em `logins.password`.

    SHA-1 do texto em **UTF-8**, em Base64 padrão — `TextUtils.encodePassword`.
    A senha NÃO é normalizada nem aparada antes do digest: espaço no fim faz
    parte da senha, tanto lá quanto aqui.

    Levanta `ValueError` para senha em branco, que é o que o BibLivre faz
    (`IllegalArgumentException("Password is null")` no mesmo método, e o
    `StringUtils.isBlank` de `login/Handler.java:53`).
    """
    if not (senha or "").strip():
        raise ValueError("senha em branco")
    digest = hashlib.sha1(senha.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


# Hash de uma senha aleatória, para comparar contra login inexistente. Sem
# isto, "usuário não existe" volta na hora e "senha errada" volta depois da
# comparação — a diferença de tempo diz qual metade falhou, exatamente o que a
# mensagem se esforça para não dizer.
_HASH_INEXISTENTE = hash_senha(secrets.token_urlsafe(32))


def _iguais(guardado: str, calculado: str) -> bool:
    """
    Comparação em tempo constante.

    Em bytes, e não em `str`: `logins.password` é `text` e, num banco remendado
    à mão, pode ter qualquer coisa dentro — `compare_digest` com `str` recusa
    caractere fora do ASCII.
    """
    return hmac.compare_digest(
        (guardado or "").encode("utf-8"), calculado.encode("utf-8"))


# --- autenticação -------------------------------------------------------

_SQL_LOGIN = """
    SELECT l.id, l.login, l.password, l.employee,
           coalesce(u.name, l.login) AS nome
      FROM logins l
      LEFT JOIN users u ON u.login_id = l.id
     WHERE l.login = %s
     ORDER BY u.id NULLS LAST
     LIMIT 1
"""


def _permissoes(con, login_id: int) -> list:
    """
    As linhas de `permissions` do login.

    Dentro de SAVEPOINT: instalação sem a tabela (ou sem GRANT nela) não pode
    derrubar a transação de quem chamou — a autenticação já terminou nesse
    ponto, e a permissão é informação a mais, não critério de login.

    Em conexão com `autocommit` ligado não há transação para proteger, e aí o
    SAVEPOINT é que seria o erro ("can only be used in transaction blocks") —
    por isso o teste antes.
    """
    em_transacao = not getattr(con, "autocommit", False)
    try:
        with con.cursor() as cur:
            if em_transacao:
                cur.execute("SAVEPOINT operador_permissoes")
            try:
                cur.execute(
                    "SELECT permission FROM permissions WHERE login_id = %s",
                    (login_id,))
                linhas = cur.fetchall() or []
            except Exception:
                if em_transacao:
                    cur.execute("ROLLBACK TO SAVEPOINT operador_permissoes")
                return []
            if em_transacao:
                cur.execute("RELEASE SAVEPOINT operador_permissoes")
        return sorted({str(linha[0]) for linha in linhas if linha and linha[0]})
    except Exception:
        return []


def autenticar(con, usuario: str, senha: str) -> dict | None:
    """
    -> `{"id", "login", "nome", "employee", "admin", "permissoes",
    "pode_emprestar", "senha_padrao"}` ou `None`.

    `None` para usuário inexistente E para senha errada, sem distinção: quem
    chama não tem como saber qual metade falhou, e a mensagem da tela é uma só
    ("usuário ou senha inválidos"). Enumerar logins é o primeiro passo de quem
    vai tentar adivinhar senha, e a tela não ganha nada com o detalhe.

    A comparação do hash acontece aqui, com `hmac.compare_digest`, e não no
    `WHERE` como faz o `LoginDAO.login`: o resultado é o mesmo, mas o caminho
    daqui não conta o tempo. A senha em claro não sai desta função — nem para
    o dict devolvido, nem para log.

    O casamento do login é exato, como no BibLivre (`WHERE login = ?`, sem
    `lower()`); só o espaço em volta é aparado, porque teclado de celular
    acrescenta um sozinho.

    Erro de banco (tabela ausente, sem permissão, conexão caída) SOBE. Para
    quem está na tela isso não é "senha errada", e transformar em `None` seria
    dizer a coisa errada; quem traduz em 503 é o router.
    """
    login = (usuario or "").strip()
    if not login or not (senha or "").strip():
        return None

    calculado = hash_senha(senha)

    with con.cursor() as cur:
        cur.execute(_SQL_LOGIN, (login,))
        linha = cur.fetchone()

    guardado = linha[2] if linha else _HASH_INEXISTENTE
    if not _iguais(guardado, calculado):
        return None

    login_id = int(linha[0])
    permissoes = _permissoes(con, login_id)
    employee = bool(linha[3])
    admin = login_id == ID_ADMIN

    return {
        "id": login_id,
        "login": linha[1],
        "nome": linha[4] or linha[1],
        "employee": employee,
        "admin": admin,
        "permissoes": permissoes,
        # `AuthorizationPoints` não registra ponto de escopo EMPLOYEE para quem
        # tem `employee = false` — nem o admin passaria por ali. Daí o `and`.
        "pode_emprestar": employee and (
            admin or PERMISSAO_EMPRESTAR in permissoes),
        # Aviso, não impedimento — o mesmo que o BibLivre mostra a quem entra
        # com a senha do instalador (login/Handler.java:74).
        "senha_padrao": _iguais(guardado, HASH_ADMIN_PADRAO),
    }


# --- sessões ------------------------------------------------------------

def _expirada(registro: dict, agora: float) -> bool:
    return (agora - registro["_visto"]) > INATIVIDADE_SEGUNDOS


def _limpar(agora: float) -> None:
    """Varre o dicionário. Só é chamada de dentro do `_lock`."""
    for token in [t for t, r in _sessoes.items() if _expirada(r, agora)]:
        _sessoes.pop(token, None)


def _publica(registro: dict, com_token: bool) -> dict:
    """
    A sessão como ela pode sair daqui.

    `ativas()` não leva o token: a tela do PC mostra quem está no balcão, não a
    credencial de cada um.
    """
    visto = registro["visto_em"]
    saida = {
        "operador": dict(registro["operador"]),
        "criada_em": registro["criada_em"],
        "visto_em": visto,
        "expira_em": visto + INATIVIDADE_SEGUNDOS,
    }
    if com_token:
        saida["token"] = registro["token"]
    return saida


def abrir_sessao(operador: dict) -> str:
    """
    Token opaco (`secrets.token_urlsafe`), guardado só em memória.

    Reiniciar o servidor desloga todo mundo — ver o docstring do topo: é o
    preço de não persistir credencial.

    Recebe o dict que veio de `autenticar`. A senha não entra aqui em nenhuma
    forma: o que fica guardado é id, login, nome e os três sinalizadores que a
    tela usa.
    """
    if not operador or not operador.get("id"):
        raise ValueError("operador sem id — chame autenticar() antes")

    token = secrets.token_urlsafe(32)
    agora_mono = time.monotonic()
    agora = time.time()

    # Campo a campo, e não `dict(operador)`: é o que garante que uma senha em
    # claro não entre na sessão por descuido de quem mexer nisto amanhã.
    limpo = {
        "id": int(operador["id"]),
        "login": operador.get("login") or "",
        "nome": operador.get("nome") or operador.get("login") or "",
        "employee": bool(operador.get("employee", True)),
        "admin": bool(operador.get("admin", False)),
        "pode_emprestar": bool(operador.get("pode_emprestar", True)),
    }

    with _lock:
        _limpar(agora_mono)
        if len(_sessoes) >= MAX_SESSOES:
            # Desempata pela mais parada: quem está usando não perde a sessão.
            parada = min(_sessoes.items(), key=lambda kv: kv[1]["_visto"])
            _sessoes.pop(parada[0], None)
        _sessoes[token] = {
            "token": token,
            "operador": limpo,
            "criada_em": agora,
            "visto_em": agora,
            "_visto": agora_mono,
        }
    return token


def sessao(token: str) -> dict | None:
    """
    `{"token", "operador", "criada_em", "visto_em", "expira_em"}` ou `None`.

    Renova o "visto por último" — é isso que faz a expiração ser por
    inatividade. O relógio é `time.monotonic()`, não `time.time()`: ajuste de
    horário de verão, ou um acerto de NTP no meio do expediente, não pode
    deslogar o balcão inteiro.
    """
    if not token:
        return None
    agora_mono = time.monotonic()
    agora = time.time()
    with _lock:
        registro = _sessoes.get(token)
        if registro is None:
            return None
        if _expirada(registro, agora_mono):
            _sessoes.pop(token, None)
            return None
        registro["_visto"] = agora_mono
        registro["visto_em"] = agora
        return _publica(registro, com_token=True)


def encerrar(token: str) -> None:
    """Sai. Idempotente: token que já morreu não é erro."""
    if not token:
        return
    with _lock:
        _sessoes.pop(token, None)


def ativas() -> list:
    """
    Quem está no balcão agora, da mais recente para a mais antiga — sem token.

    Aproveita a passada para varrer o que expirou; sem isso o dicionário só
    encolheria quando alguém tentasse usar um token morto.
    """
    agora_mono = time.monotonic()
    with _lock:
        _limpar(agora_mono)
        registros = list(_sessoes.values())
    registros.sort(key=lambda r: r["visto_em"], reverse=True)
    return [_publica(r, com_token=False) for r in registros]


def esquecer_tudo() -> int:
    """
    Derruba todas as sessões e devolve quantas caíram.

    Existe para o teste e para o caso real de a senha do BibLivre ser trocada
    com gente logada.
    """
    with _lock:
        n = len(_sessoes)
        _sessoes.clear()
    return n


# --- prova ---------------------------------------------------------------
#
# O arquivo de fumaça (tests/verificar.py) é de outro pacote e não conhece
# `logins`, então a prova mora aqui:
#
#     python packages/biblivre-client/src/biblio/biblivre/operador.py
#
# O caso que vale o módulo inteiro é o primeiro: se `hash_senha("abracadabra")`
# bate com o hash que o SQL de criação do BibLivre traz para o admin, então
# algoritmo, encoding e Base64 estão todos certos de uma vez.

if __name__ == "__main__":  # pragma: no cover
    import sys

    _falhas: list[str] = []

    def checar(rotulo, condicao, extra=""):
        print(("  ok   " if condicao else "  FALHA") + f"  {rotulo}"
              + (f"   {extra}" if extra and not condicao else ""))
        if not condicao:
            _falhas.append(rotulo)

    class _CursorFalso:
        """O mínimo de cursor psycopg2 que `autenticar` usa."""

        def __init__(self, banco):
            self._banco = banco
            self._linhas: list[tuple] = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, args=None):
            texto = " ".join(sql.split()).lower()
            self._banco.sqls.append(texto)
            if texto.startswith(("savepoint", "release", "rollback to")):
                self._linhas = []
            elif "from logins" in texto:
                nome = args[0]
                self._linhas = [
                    linha for linha in self._banco.logins if linha[1] == nome]
            elif "from permissions" in texto:
                if self._banco.sem_permissions:
                    raise RuntimeError('relation "permissions" does not exist')
                self._linhas = [
                    (p,) for (login_id, p) in self._banco.permissoes
                    if login_id == args[0]]
            else:
                raise AssertionError(f"consulta inesperada: {texto}")

        def fetchone(self):
            return self._linhas[0] if self._linhas else None

        def fetchall(self):
            return list(self._linhas)

    class _BancoFalso:
        """`logins` + `permissions` como a instalação do instalador as traz."""

        def __init__(self):
            # (id, login, password, employee, nome)
            self.logins = [
                (1, "admin", HASH_ADMIN_PADRAO, True, "Administrador"),
                (7, "balcao", hash_senha("senha do balcao"), True, "Maria"),
                (9, "leitora", hash_senha("outra senha"), False, "Joana"),
            ]
            self.permissoes = [(7, PERMISSAO_EMPRESTAR)]
            self.sqls: list[str] = []
            self.autocommit = False
            self.sem_permissions = False

        def cursor(self):
            return _CursorFalso(self)

    print("\nhash — o par do instalador (a prova do módulo)")
    checar("hash_senha('abracadabra') == o hash do SQL de criação",
           hash_senha(SENHA_PADRAO) == HASH_ADMIN_PADRAO,
           f"saiu {hash_senha(SENHA_PADRAO)!r}, esperado {HASH_ADMIN_PADRAO!r}")
    checar("acento vai como UTF-8 (não latin-1)",
           hash_senha("ação") == base64.b64encode(
               hashlib.sha1("ação".encode("utf-8")).digest()).decode())
    checar("Base64 padrão, com padding", hash_senha("x").endswith("="))
    checar("senha não é aparada antes do digest",
           hash_senha("abracadabra ") != HASH_ADMIN_PADRAO)
    try:
        hash_senha("   ")
        checar("senha em branco levanta ValueError", False)
    except ValueError:
        checar("senha em branco levanta ValueError", True)

    print("\nautenticar — contra um `logins` de mentira")
    banco = _BancoFalso()
    quem = autenticar(banco, "admin", SENHA_PADRAO)
    checar("admin entra", quem is not None)
    checar("devolve o logins.id real", quem and quem["id"] == 1)
    checar("nome vem do coalesce(users.name, login)",
           quem and quem["nome"] == "Administrador")
    checar("admin é o id 1", quem and quem["admin"] is True)
    checar("avisa que a senha ainda é a do instalador",
           quem and quem["senha_padrao"] is True)
    checar("a senha em claro não volta na resposta",
           quem and SENHA_PADRAO not in repr(quem))

    checar("senha errada não entra",
           autenticar(banco, "admin", "abracadabro") is None)
    checar("usuário inexistente não entra",
           autenticar(banco, "ninguem", SENHA_PADRAO) is None)
    checar("login é exato, como no BibLivre",
           autenticar(banco, "ADMIN", SENHA_PADRAO) is None)
    checar("espaço em volta do login é aparado",
           autenticar(banco, "  admin  ", SENHA_PADRAO) is not None)
    checar("senha vazia não entra", autenticar(banco, "admin", "") is None)

    balcao = autenticar(banco, "balcao", "senha do balcao")
    checar("funcionário com CIRCULATION_LENDING_LEND pode emprestar",
           balcao and balcao["pode_emprestar"] is True)
    checar("funcionário não é admin por acidente",
           balcao and balcao["admin"] is False)
    leitora = autenticar(banco, "leitora", "outra senha")
    checar("leitora (employee=false) entra mas não empresta",
           leitora and leitora["pode_emprestar"] is False)
    checar("`permissions` é consultada dentro de SAVEPOINT",
           any(s.startswith("savepoint") for s in banco.sqls))

    banco_auto = _BancoFalso()
    banco_auto.autocommit = True
    auto = autenticar(banco_auto, "balcao", "senha do balcao")
    checar("com autocommit não sai SAVEPOINT",
           not any(s.startswith("savepoint") for s in banco_auto.sqls))
    checar("...e as permissões continuam sendo lidas",
           auto and auto["pode_emprestar"] is True)

    banco_sem = _BancoFalso()
    banco_sem.sem_permissions = True
    sem = autenticar(banco_sem, "admin", SENHA_PADRAO)
    checar("instalação sem a tabela `permissions` não impede o login",
           sem is not None and sem["permissoes"] == [])
    checar("...e o admin continua podendo emprestar",
           sem and sem["pode_emprestar"] is True)
    checar("a falha foi desfeita com ROLLBACK TO SAVEPOINT",
           any(s.startswith("rollback to") for s in banco_sem.sqls))

    print("\nsessão — memória, inatividade e vazamento")
    esquecer_tudo()
    token = abrir_sessao(quem)
    checar("token é opaco e longo", isinstance(token, str) and len(token) >= 32)
    viva = sessao(token)
    checar("a sessão volta pelo token", viva is not None)
    checar("com o operador dentro", viva and viva["operador"]["id"] == 1)
    checar("ativas() não vaza o token",
           all("token" not in s for s in ativas()))
    checar("ativas() lista quem está no balcão", len(ativas()) == 1)
    checar("token desconhecido é None", sessao("nao-existe") is None)
    checar("token vazio é None", sessao("") is None)

    _tokens = {abrir_sessao(quem) for _ in range(5)}
    checar("tokens não se repetem", len(_tokens) == 5)

    encerrar(token)
    checar("encerrar derruba a sessão", sessao(token) is None)
    encerrar(token)  # idempotente: não pode levantar
    checar("encerrar duas vezes não é erro", True)

    esquecer_tudo()
    token = abrir_sessao(quem)
    with _lock:
        # Empurra o "visto por último" para além da inatividade, sem esperar
        # 12 horas nem mexer no relógio do sistema.
        _sessoes[token]["_visto"] -= INATIVIDADE_SEGUNDOS + 1
    checar("sessão parada além da inatividade expira", sessao(token) is None)
    checar("e sai do dicionário", not _sessoes)

    token = abrir_sessao(quem)
    with _lock:
        _sessoes[token]["_visto"] -= INATIVIDADE_SEGUNDOS - 60
    checar("sessão em uso não expira no meio do turno", sessao(token) is not None)
    with _lock:
        parado = time.monotonic() - _sessoes[token]["_visto"]
    checar("...porque o 'visto por último' foi renovado", parado < 1)

    esquecer_tudo()
    for _ in range(MAX_SESSOES + 10):
        abrir_sessao(quem)
    checar("o dicionário tem teto", len(_sessoes) <= MAX_SESSOES,
           f"ficaram {len(_sessoes)}")
    checar("esquecer_tudo() limpa", esquecer_tudo() > 0 and not _sessoes)

    print()
    if _falhas:
        print(f"{len(_falhas)} falha(s): " + ", ".join(_falhas))
        sys.exit(1)
    print("tudo certo")
