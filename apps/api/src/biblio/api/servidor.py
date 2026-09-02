"""
Sobe o servidor.

    biblio-servidor                      # https://0.0.0.0:8000
    biblio-servidor --porta 9000
    biblio-servidor --sem-ssl            # http://localhost:8000
    biblio-servidor --db-senha SENHA     # liga a checagem de ISBN já catalogado

HTTPS é o padrão, e não é preciosismo: `getUserMedia` (a câmera do navegador)
só funciona em contexto seguro, então sem HTTPS não há scanner no celular. O
certificado é autoassinado e gerado na primeira execução; o navegador vai
reclamar uma vez, e é só aceitar.
"""

import argparse
import os
import sys

import uvicorn

from biblio.biblivre import acervo, conexao
from biblio.catalogacao import config
from biblio.catalogacao.cert import gerar_certificado
from biblio.catalogacao.fila import reconsultar_acervo
from biblio.catalogacao.rede import obter_ip_local

from .main import app, preparar


def _argumentos():
    p = argparse.ArgumentParser(description="Servidor de catalogação por ISBN")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--sem-ssl", action="store_true",
                   help="HTTP em localhost (sem HTTPS — a câmera não funciona)")
    p.add_argument("--db-senha", help="senha do Postgres do BibLivre (ou PGPASSWORD)")
    p.add_argument("--db-host", help="host do Postgres (padrão: localhost)")
    p.add_argument("--db-nome", help="banco (padrão: biblivre4)")
    p.add_argument("--db-usuario", help="usuário (padrão: biblivre)")
    p.add_argument("--db-schema", help="schema da biblioteca (padrão: single)")
    return p.parse_args()


def _conectar_acervo() -> None:
    """
    Liga a checagem de ISBN já catalogado, se houver senha.

    Sem banco o app funciona igual, mas trata todo livro como obra nova — e a
    tela avisa disso em vez de degradar em silêncio.
    """
    if not (conexao.db_config().get("senha") or os.environ.get("PGPASSWORD")):
        print("  Sem senha do Postgres: checagem de ISBN já catalogado desligada "
              "(configure na tela de revisão ou use --db-senha)")
        return

    teste = conexao.testar_conexao()
    if not teste.get("conectado"):
        print(f"  Acervo indisponível ({teste.get('erro')}) — a checagem de "
              "ISBN já catalogado fica desligada até configurar na tela")
        return

    total = len(acervo.indice(forcar=True))
    print(f"  Acervo conectado: {teste['obras']:,} obras, "
          f"{teste['exemplares']:,} exemplares — {total:,} ISBNs indexados")
    reconsultar_acervo()


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

    pendentes = preparar()
    print(f"\n  Fila carregada do disco: {pendentes} item(ns)")
    _conectar_acervo()

    if args.sem_ssl:
        config.SERVER_URL = f"http://localhost:{args.porta}"
        print(f"\n  Rodando em HTTP: {config.SERVER_URL}")
        print("  A câmera do celular NÃO vai funcionar sem HTTPS.\n")
        uvicorn.run(app, host="127.0.0.1", port=args.porta)
    else:
        cert, key = gerar_certificado()
        config.SERVER_URL = f"https://{obter_ip_local()}:{args.porta}"
        print("\n  === Catalogação ISBN ===")
        print(f"  No celular: {config.SERVER_URL}  (aceite o certificado)")
        print(f"  No PC:      {config.SERVER_URL}/fila")
        print(f"  API:        {config.SERVER_URL}/docs\n")
        uvicorn.run(app, host=args.host, port=args.porta,
                    ssl_certfile=cert, ssl_keyfile=key)


if __name__ == "__main__":
    main()
