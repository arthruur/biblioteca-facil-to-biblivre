"""
Extrai as 16 tabelas de um backup `.bkp` do Biblioteca Fácil.

    python scripts/extrair_bkp.py backup.bkp saida/

Formato documentado em docs/FORMATO_BKP.md; a lógica está em
`biblio.legado.bkp`.
"""

import argparse

from biblio.legado import bkp

from _comum import console_utf8


def main():
    console_utf8()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("bkp", help="arquivo .bkp do Biblioteca Fácil")
    p.add_argument("saida", nargs="?", default="tabelas_extraidas",
                   help="pasta de destino (padrão: tabelas_extraidas)")
    args = p.parse_args()

    tamanhos = bkp.extrair_para_pasta(args.bkp, args.saida)

    print(f"{len(tamanhos)} arquivos de tabela extraídos:\n")
    for nome, tamanho in tamanhos.items():
        print(f"  {nome:20s} {tamanho:>10,d} bytes")
    print(f"\nArquivos salvos em: {args.saida}")


if __name__ == "__main__":
    main()
