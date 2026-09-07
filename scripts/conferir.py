"""
Confere o banco do BibLivre depois da carga. Só leitura, nada é escrito.

    python scripts/conferir.py
    python scripts/conferir.py --estrito     # falha também no que não verificou
    python scripts/conferir.py --json        # o relatório cru, para automação

É o portão antes de **Administração → Backup → Full**: o `.b5bz` empacota o que
estiver no banco, índice vazio e sequence atrasada inclusive, e o restore na
máquina final apaga o schema de destino — não há segunda chance de conferir lá.
Sai com código 1 se alguma checagem falhar.

O que cada checagem responde, e por que a do índice e a das sequences são as
que doem: `biblio.biblivre.verificacao`.
"""

import argparse
import json
import textwrap

from biblio.biblivre import verificacao

from _comum import args_db, conectar, console_utf8

LARGURA = 78
MARCAS = {True: "ok   ", False: "FALHA", None: "?    "}


def _valor(checagem) -> str:
    if checagem["valor"] is None:
        return "—"
    if isinstance(checagem["valor"], bool):
        return str(checagem["valor"])
    if isinstance(checagem["valor"], int):
        return f"{checagem['valor']:,}"
    return str(checagem["valor"])


def _imprimir(checagem) -> None:
    marca = MARCAS[checagem["ok"]]
    rotulo = checagem["rotulo"]
    if len(rotulo) > 46:
        rotulo = rotulo[:45] + "…"
    print(f"  {marca}  {rotulo:<46} {_valor(checagem)}")

    detalhe = checagem["detalhe"]
    if detalhe:
        for linha in textwrap.wrap(detalhe, LARGURA - 11):
            print(f"           {linha}")


def main():
    console_utf8()
    p = argparse.ArgumentParser(
        description="Confere o banco do BibLivre depois da carga (só leitura)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Código de saída 1 se houver falha — rode antes de gerar o .b5bz.")
    p.add_argument("--estrito", action="store_true",
                   help="trata 'não verificada' (tabela ausente, permissão) "
                        "como falha")
    p.add_argument("--json", action="store_true",
                   help="imprime o relatório em JSON, sem o texto")
    args_db(p)
    args = p.parse_args()

    con = conectar(args)
    try:
        relatorio = verificacao.conferir(con)
    finally:
        con.close()

    if args.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2, default=str))
    else:
        _relatar(relatorio, args)

    resumo = relatorio["resumo"]
    ruim = resumo["falhas"] or (args.estrito and resumo["nao_verificadas"])
    return 1 if ruim else 0


def _relatar(relatorio: dict, args) -> None:
    print(f"\n{args.dbname}@{args.host}:{args.port}  schema {args.schema}\n")

    checagens = relatorio["checagens"]
    informativas = [c for c in checagens if c["esperado"] is None]
    conferencias = [c for c in checagens if c["esperado"] is not None]

    print("conferências")
    for c in conferencias:
        _imprimir(c)

    print("\ncontagens de referência (informativas, nunca falham)")
    for c in informativas:
        _imprimir(c)

    resumo = relatorio["resumo"]
    print(f"\n{resumo['ok']} ok, {resumo['falhas']} falha(s), "
          f"{resumo['nao_verificadas']} não verificada(s) "
          f"de {resumo['total']} checagens")

    nao_verificadas = [c for c in checagens if c["ok"] is None]
    if nao_verificadas:
        print("  não verificadas: "
              + ", ".join(c["chave"] for c in nao_verificadas)
              + ("  (--estrito faz disto uma falha)" if not args.estrito else ""))

    falhas = [c for c in checagens if c["ok"] is False]
    if falhas:
        print("\nFALHOU: " + ", ".join(c["chave"] for c in falhas))
        print("Resolva antes de Administração → Backup → Full: o .b5bz "
              "empacota o banco como ele está.")
    else:
        print("\nNada a corrigir nas checagens que rodaram. "
              "A etiqueta de teste ainda é conferência de papel — imprima uma.")


if __name__ == "__main__":
    raise SystemExit(main())
