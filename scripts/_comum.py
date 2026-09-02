"""
O que todo CLI de migração repetia: console em UTF-8, argumentos de banco e o
prompt de senha.

Os CLIs desta pasta são casca fina. Toda a lógica mora em `biblio.legado` e
`biblio.biblivre` — aqui só se lê argumento, se imprime relatório e se decide
entre o dry-run e o `--executar`.
"""

import getpass
import os
import sys


def console_utf8() -> None:
    """
    Os relatórios imprimem títulos e nomes acentuados. Num console do Windows
    com codepage legada isso viraria UnicodeEncodeError no meio da execução.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def args_db(p) -> None:
    """Acrescenta os argumentos de conexão, iguais em todos os passos."""
    g = p.add_argument_group("banco do BibLivre")
    g.add_argument("--host", default="localhost")
    g.add_argument("--port", default="5432")
    g.add_argument("--dbname", default="biblivre4")
    g.add_argument("--user", default="biblivre")
    g.add_argument("--senha", help="senha do PostgreSQL (ou use PGPASSWORD)")
    g.add_argument("--schema", default="single",
                   help="schema da biblioteca (padrão: single)")


def conectar(args):
    """
    Abre a conexão, pedindo a senha no terminal se ela não veio.

    O prompt fica aqui, e não na biblioteca: `biblio.biblivre.conexao` também
    roda dentro do servidor web, onde não existe terminal para perguntar.
    """
    from biblio.biblivre import conexao

    senha = args.senha or os.environ.get("PGPASSWORD")
    if not senha:
        senha = getpass.getpass(f"Senha de {args.user}@{args.host}: ")

    return conexao.conectar({
        "host": args.host, "port": int(args.port), "dbname": args.dbname,
        "user": args.user, "senha": senha, "schema": args.schema,
    }, timeout=30)


def encerrar(msg: str) -> None:
    sys.exit(f"ERRO: {msg}")
