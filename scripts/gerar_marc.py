"""
Gera o MARC21 / ISO 2709 para o BibLivre 5, a partir do CSV do `consolidar.py`.

    python scripts/gerar_marc.py acervo_consolidado.csv obras.mrc

Saídas:
    obras.mrc       registros bibliográficos (1 por OBRA) — é o que se importa
    exemplares.csv  1 linha por exemplar físico, para o passo dos exemplares

Por que 1 registro por obra e não 1 por exemplar, e por que o agrupamento é por
conteúdo e nunca por ISBN: `biblio.biblivre.marc` e docs/ROADMAP.md.
"""

import argparse
from collections import Counter

from biblio.biblivre import marc

from _comum import console_utf8


def main():
    console_utf8()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("csv_entrada", help="CSV gerado por consolidar.py")
    p.add_argument("mrc_saida", nargs="?", default="obras.mrc")
    p.add_argument("--exemplares", default="exemplares.csv")
    args = p.parse_args()

    linhas = marc.ler_csv_consolidado(args.csv_entrada)
    grupos = marc.agrupar_por_obra(linhas)

    marc.escrever_mrc((marc.montar_registro(g) for g in grupos), args.mrc_saida)
    n_ex = marc.escrever_csv_exemplares(grupos, args.exemplares)

    tamanhos = Counter(len(g) for g in grupos)
    print(f"{len(linhas):,} registros de acervo lidos")
    print(f"{len(grupos):,} obras -> {args.mrc_saida}")
    print(f"{n_ex:,} exemplares -> {args.exemplares}")
    print(f"  obras com 1 exemplar : {tamanhos[1]:,}")
    print(f"  obras com 2+         : "
          f"{sum(v for k, v in tamanhos.items() if k > 1):,}"
          f"  (maior grupo: {max(tamanhos)} exemplares)")


if __name__ == "__main__":
    main()
