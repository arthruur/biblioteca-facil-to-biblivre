"""
Conexão com o PostgreSQL do BibLivre 5.

Existe porque cinco lugares diferentes precisavam abrir a mesma conexão e cada
um tinha a sua cópia de `conectar()` e de `_ident()` — divergindo em detalhes
que importam (timeout, `search_path`, validação do nome do schema). Agora é um
lugar só.

CREDENCIAIS
-----------
A senha **nunca é persistida em disco**. Ela entra por variável de ambiente ao
subir o processo, por argumento de linha de comando, ou pela tela (que chama
`definir_db`), e vive só na memória do processo.

O `search_path` é fixado no schema da biblioteca a cada conexão. Numa
instalação de biblioteca única o schema é `single` (`Constants.SINGLE_SCHEMA`);
o schema `global` guarda o que é comum a todas (traduções, configurações
semeadas pelo instalador).
"""

import os
import re
import threading

from .ambiente import carregar_env

# Antes de montar `_db`: o `.env` da raiz precisa estar no ambiente na hora em
# que as variaveis sao lidas, senao o processo local sobe sem senha e a
# checagem de ISBN ja catalogado fica desligada em silencio. O que ja estava no
# ambiente (compose, shell, secret) tem precedencia — ver `ambiente.py`.
carregar_env()

SCHEMA_PADRAO = "single"
SCHEMA_GLOBAL = "global"

# `logins.id` do admin criado na instalação (sql/biblivre4.sql). É o
# `created_by` de tudo que inserimos.
USUARIO_PADRAO = 1

_lock = threading.Lock()


def _env(*nomes: str, padrao: str = "") -> str:
    """Primeiro nome preenchido vence. Aceita BIBLIVRE_DB_* e os PG* padrão
    (que o docker-compose já define)."""
    for n in nomes:
        v = os.environ.get(n)
        if v:
            return v
    return padrao


_db: dict = {
    "host": _env("BIBLIVRE_DB_HOST", "PGHOST", padrao="localhost"),
    "port": int(_env("BIBLIVRE_DB_PORT", "PGPORT", padrao="5432")),
    "dbname": _env("BIBLIVRE_DB_NAME", "PGDATABASE", padrao="biblivre4"),
    "user": _env("BIBLIVRE_DB_USER", "PGUSER", padrao="biblivre"),
    "senha": _env("BIBLIVRE_DB_SENHA", "PGPASSWORD"),
    "schema": _env("BIBLIVRE_DB_SCHEMA", padrao=SCHEMA_PADRAO),
}

CHAVES = ("host", "port", "dbname", "user", "senha", "schema")


def db_config() -> dict:
    """Cópia da configuração atual, senha inclusa. Para exibir, use `sem_senha`."""
    with _lock:
        return dict(_db)


def sem_senha(cfg: dict | None = None) -> dict:
    """A config sem o campo `senha` — é isso que pode ir para a tela ou o log."""
    return {k: v for k, v in (cfg or db_config()).items() if k != "senha"}


def definir_db(novo: dict) -> dict:
    """Atualiza só as chaves informadas; devolve a config sem a senha."""
    with _lock:
        for chave in ("host", "dbname", "user", "senha", "schema"):
            if novo.get(chave) is not None and novo.get(chave) != "":
                _db[chave] = novo[chave]
        if novo.get("port"):
            _db["port"] = int(novo["port"])
        resumo = {k: v for k, v in _db.items() if k != "senha"}
    # Fora do `_lock`: `invalidar_sonda` toma o dela, e aninhar os dois em
    # ordens diferentes em dois lugares e como se escreve um deadlock.
    invalidar_sonda()
    return resumo


def ident(nome: str) -> str:
    """
    Identificador SQL entre aspas.

    Nomes de schema chegam da linha de comando e da tela, e vão para dentro de
    um `SET search_path` que não aceita parâmetro ligado — então o nome é
    validado antes de ser interpolado, não escapado depois.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome or ""):
        raise ValueError(f"nome de schema inválido: {nome!r}")
    return f'"{nome}"'


def conectar(sobrepor: dict | None = None, timeout: int = 5):
    """
    Abre conexão com o Postgres do BibLivre, com `search_path` no schema da
    biblioteca. Levanta em caso de falha; `autocommit` fica desligado, porque
    toda carga daqui é transacional.
    """
    try:
        import psycopg2
    except ImportError as e:  # pragma: no cover - ambiente sem a dependência
        raise RuntimeError(
            "psycopg2 não instalado. Rode: pip install -r requirements.txt") from e

    cfg = {**db_config(), **(sobrepor or {})}
    senha = cfg.get("senha") or cfg.get("password") or os.environ.get("PGPASSWORD") or ""
    if not senha:
        raise RuntimeError(
            "Senha do Postgres não configurada "
            "(POST /api/db, --db-senha, ou PGPASSWORD no ambiente)")

    schema = ident(cfg.get("schema") or SCHEMA_PADRAO)
    con = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
        user=cfg["user"], password=senha, connect_timeout=timeout,
    )
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public")
    return con


def testar_conexao(sobrepor: dict | None = None) -> dict:
    """
    Valida credenciais e devolve as contagens do acervo. Não levanta exceção —
    é o que a tela chama para decidir se mostra a pílula verde ou âmbar.
    """
    try:
        con = conectar(sobrepor)
    except Exception as e:
        return {"conectado": False, "erro": str(e)}
    try:
        try:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM biblio_records WHERE database = 'main'")
                (obras,) = cur.fetchone()
                cur.execute("SELECT count(*) FROM biblio_holdings")
                (exemplares,) = cur.fetchone()
        except Exception as e:
            return {"conectado": False, "erro": str(e)}

        resultado = {"conectado": True, "erro": "", "obras": obras,
                     "exemplares": exemplares}

        # Circulação é diagnóstico extra, não critério de conexão: numa
        # instância com o acervo carregado e a circulação ainda não, ou num
        # Postgres de demonstração, isto pode falhar sem que a conexão esteja
        # ruim.
        try:
            con.rollback()
            with con.cursor() as cur:
                cur.execute("SELECT count(*) FROM users")
                (resultado["leitores"],) = cur.fetchone()
                cur.execute(
                    "SELECT count(*) FROM lendings WHERE return_date IS NULL")
                (resultado["emprestimos_abertos"],) = cur.fetchone()
        except Exception:
            con.rollback()
        return resultado
    finally:
        try:
            con.close()
        except Exception:
            pass


# --- Sonda de conectividade ---
#
# A tela precisa saber se o banco esta de pe, e ela pergunta em laco. Antes ela
# inferia isso do tamanho do indice de ISBN (`acervo.estado()["indexados"]`), o
# que da falso negativo sempre que o indice e montado sob demanda — o padrao em
# desenvolvimento, onde `--reload` liga BIBLIO_SEM_INDICE=1. Resultado: pilula
# ambar "Acervo indisponivel" com o Postgres conectado.
#
# Agora a resposta vem de uma conexao de verdade, com TTL curto para o laco da
# tela nao abrir conexao a cada dois segundos.

TTL_SONDA = 15.0

_sonda_lock = threading.Lock()
_sonda: dict = {}
_sonda_em: float = 0.0


def sondar(forcar: bool = False) -> dict:
    """
    `{conectado, erro, obras, exemplares}` — com cache de `TTL_SONDA`.

    Nao levanta: banco fora do ar e um estado normal desta aplicacao, nao uma
    excecao. Sem senha configurada devolve `conectado: False` sem nem tentar
    abrir socket.
    """
    global _sonda, _sonda_em
    import time as _time

    with _sonda_lock:
        fresco = _sonda and (_time.time() - _sonda_em) < TTL_SONDA
        if fresco and not forcar:
            return dict(_sonda)

    cfg = db_config()
    if not (cfg.get("senha") or os.environ.get("PGPASSWORD")):
        resultado = {"conectado": False, "erro": "senha do Postgres nao configurada"}
    else:
        resultado = testar_conexao()

    with _sonda_lock:
        _sonda = dict(resultado)
        _sonda_em = _time.time()
        return dict(resultado)


def invalidar_sonda() -> None:
    """Forca a proxima `sondar()` a ir ao banco. Chamar depois de `definir_db`."""
    global _sonda_em
    with _sonda_lock:
        _sonda_em = 0.0
