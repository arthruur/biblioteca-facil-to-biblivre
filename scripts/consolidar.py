"""
Cruza Acervo + Autores + Editoras + Idiomas + Tipos + Classificação num único
CSV, com os nomes de coluna que a geração do MARC21 espera.

    python scripts/consolidar.py saida/ acervo_consolidado.csv

Chaves, relacionamentos e o tratamento da exclusão lógica estão documentados em
`biblio.legado.consolidar`.
"""

import argparse
from pathlib import Path

from biblio.legado.consolidar import consolidar

from _comum import console_utf8


def main():
    console_utf8()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("pasta", help="pasta com os .dat extraídos do .bkp")
    p.add_argument("saida", nargs="?", default="acervo_consolidado.csv")
    p.add_argument("--incluir-excluidos", action="store_true",
                   help="mantém registros com exclusão lógica")
    args = p.parse_args()

    df = consolidar(args.pasta, args.incluir_excluidos)
    df.to_csv(args.saida, index=False, encoding="utf-8-sig")

    print(f"{len(df):,} registros de acervo")
    print(f"{df['chave_obra'].nunique():,} obras distintas (exemplares agrupados)")
    print(f"{(df['autor_principal'] != '').sum():,} com autor")
    print(f"{(df['editora'] != '').sum():,} com editora")
    print(f"{(df['isbn'] != '').sum():,} com ISBN")
    print(f"{(df['cdd'] != '').sum():,} com CDD")
    print(f"\nCSV gerado em: {Path(args.saida).resolve()}")


if __name__ == "__main__":
    main()
