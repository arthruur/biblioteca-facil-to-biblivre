"""
Sobe o servidor.

    biblio-servidor                      # https://0.0.0.0:8000
    biblio-servidor --porta 9000
    biblio-servidor --sem-ssl            # http://localhost:8000
    biblio-servidor --reload             # desenvolvimento: reinicia ao salvar
    biblio-servidor --db-senha SENHA     # liga a checagem de ISBN já catalogado

HTTPS é o padrão, e não é preciosismo: `getUserMedia` (a câmera do navegador)
só funciona em contexto seguro, então sem HTTPS não há scanner no celular. O
certificado é autoassinado e gerado na primeira execução; o navegador vai
reclamar uma vez, e é só aceitar.

Credenciais do banco entram por `--db-*`, por variável de ambiente ou pelo
`.env` da raiz (ver `biblio.biblivre.ambiente`). Nunca vão para disco.
"""

import argparse
import os
import sys

import uvicorn

from biblio.biblivre import conexao
from biblio.catalogacao import config
from biblio.catalogacao.cert import gerar_certificado
from biblio.catalogacao.rede import obter_ip_local

# A aplicação em si; em modo `--reload` o uvicorn a reimporta por string.
APP = "biblio.api.main:app"

# O que o watcher observa. Sem isto o uvicorn vigia o cwd inteiro — e o cwd
# tem `data/` (a fila grava um JSON por item, a cada bipe) e `apps/web`
# (node_modules, dist), o que transformaria cada captura num restart.
def _pastas_vigiadas() -> list[str]:
    return [str(config.ROOT / "packages"), str(config.ROOT / "apps" / "api")]


def _argumentos():
    p = argparse.ArgumentParser(description="Servidor de catalogação por ISBN")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--sem-ssl", action="store_true",
                   help="HTTP em localhost (sem HTTPS — a câmera não funciona)")
    p.add_argument("--reload", action="store_true",
                   help="reinicia ao salvar .py (desenvolvimento); o índice de "
                        "ISBN passa a ser montado sob demanda")
    p.add_argument("--sem-indice", action="store_true",
                   help="não varre o acervo na subida; monta no primeiro ISBN")
    p.add_argument("--db-senha", help="senha do Postgres do BibLivre (ou PGPASSWORD)")
    p.add_argument("--db-host", help="host do Postgres (padrão: localhost)")
    p.add_argument("--db-nome", help="banco (padrão: biblivre4)")
    p.add_argument("--db-usuario", help="usuário (padrão: biblivre)")
    p.add_argument("--db-schema", help="schema da biblioteca (padrão: single)")
    return p.parse_args()


def _credenciais_para_ambiente(args) -> None:
    """
    Em modo reload, quem serve é um subprocesso — e ele não herda o estado que
    `definir_db` guarda em memória. As credenciais precisam viajar pelo
    ambiente, que é de onde `conexao` as lê no import.
    """
    equivalentes = {
        "BIBLIVRE_DB_SENHA": args.db_senha,
        "BIBLIVRE_DB_HOST": args.db_host,
        "BIBLIVRE_DB_NAME": args.db_nome,
        "BIBLIVRE_DB_USER": args.db_usuario,
        "BIBLIVRE_DB_SCHEMA": args.db_schema,
    }
    for chave, valor in equivalentes.items():
        if valor:
            os.environ[chave] = valor


def main():
    # As mensagens de subida têm acento. Num console do Windows com codepage
    # legada isso viraria UnicodeEncodeError logo no arranque.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = _argumentos()

    conexao.definir_db({
        "senha": args.db_senha, "host": args.db_host, "dbname": args.db_nome,
        "user": args.db_usuario, "schema": args.db_schema,
    })

    # `--reload` implica índice sob demanda: a varredura da `biblio_records`
    # inteira a cada save é a diferença entre um restart de 1s e um de 10s.
    # Quem quiser o contrário define BIBLIO_SEM_INDICE=0 no ambiente — o valor
    # já presente é respeitado.
    if (args.sem_indice or args.reload) and "BIBLIO_SEM_INDICE" not in os.environ:
        os.environ["BIBLIO_SEM_INDICE"] = "1"

    if args.sem_ssl:
        alvo = f"http://localhost:{args.porta}"
        ssl = {}
        host = "127.0.0.1"
    else:
        cert, key = gerar_certificado()
        alvo = f"https://{obter_ip_local()}:{args.porta}"
        ssl = {"ssl_certfile": cert, "ssl_keyfile": key}
        host = args.host

    # O processo que serve lê isto do ambiente (o QR code da tela usa a URL).
    config.SERVER_URL = alvo
    os.environ["BIBLIO_SERVER_URL"] = alvo

    print("")
    print("  === Catalogação ISBN ===")
    if args.sem_ssl:
        print(f"  Rodando em HTTP: {alvo}")
        print("  A câmera do celular NÃO vai funcionar sem HTTPS.")
    else:
        print(f"  No celular: {alvo}  (aceite o certificado)")
        print(f"  No PC:      {alvo}/fila")
    print(f"  API:        {alvo}/docs")
    if args.reload:
        print("  Reload ligado: salvar um .py em packages/ ou apps/api/ reinicia.")
    print("")

    if args.reload:
        _credenciais_para_ambiente(args)
        uvicorn.run(APP, host=host, port=args.porta, reload=True,
                    reload_dirs=_pastas_vigiadas(), reload_includes=["*.py"],
                    **ssl)
    else:
        from .main import app
        uvicorn.run(app, host=host, port=args.porta, **ssl)


if __name__ == "__main__":
    main()
