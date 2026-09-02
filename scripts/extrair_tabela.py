"""
Exporta qualquer tabela do Biblioteca Fácil para CSV.

    # lista as tabelas disponíveis e o layout de cada uma
    python scripts/extrair_tabela.py saida/ --listar

    # exporta uma tabela
    python scripts/extrair_tabela.py saida/ T09_ACER.dat acervo.csv

O layout vem do cabeçalho do próprio `.dat` — nada de offset caçado à mão. Ver
docs/TABELAS.md e `biblio.legado.tabela`.
"""

import argparse
import sys
from pathlib import Path

from biblio.legado import tabela

from _comum import console_utf8


def main():
    console_utf8()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("pasta", help="pasta com os .dat extraídos do .bkp")
    p.add_argument("tabela", nargs="?", help="ex.: T09_ACER.dat")
    p.add_argument("saida", nargs="?", help="arquivo CSV de saída")
    p.add_argument("--listar", action="store_true",
                   help="mostra o layout de todas as tabelas e sai")
    p.add_argument("--datas-iso", action="store_true",
                   help="converte campos de data para AAAA-MM-DD")
    args = p.parse_args()

    if args.listar or not args.tabela:
        for tab in tabela.carregar_todas(args.pasta).values():
            print(tab.resumo())
            print()
        return

    tab = tabela.carregar(args.pasta, args.tabela)
    if not tab.validar():
        print(f"aviso: layout de {args.tabela} não passou na validação",
              file=sys.stderr)

    saida = Path(args.saida or f"{Path(args.tabela).stem.lower()}.csv")
    n = tabela.exportar_csv(tab, saida, datas_iso=args.datas_iso)

    print(f"{n:,} registros de {args.tabela} ({tab.descricao})")
    print(f"CSV gerado em: {saida.resolve()}")


if __name__ == "__main__":
    main()
