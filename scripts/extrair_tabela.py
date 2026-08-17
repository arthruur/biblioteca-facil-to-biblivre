"""
Exporta qualquer tabela do Biblioteca Fácil para CSV, usando o layout
declarado no próprio cabeçalho do `.dat` (ver scripts/bf_tabela.py).

Substitui os antigos `extrair_acervo.py` e `extrair_autores.py`, que
dependiam de offsets descobertos à mão — e que, por causa disso, rotulavam
o campo T09_SUBTITULO como se fosse o título.

Uso:
    # lista as tabelas disponíveis e o layout de cada uma
    python scripts/extrair_tabela.py pasta_das_tabelas --listar

    # exporta uma tabela
    python scripts/extrair_tabela.py pasta_das_tabelas T09_ACER.dat acervo.csv
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bf_tabela as bf  # noqa: E402


def main():
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
        for tab in bf.carregar_todas(args.pasta).values():
            print(tab.resumo())
            print()
        return

    tab = bf.carregar(args.pasta, args.tabela)
    if not tab.validar():
        print(f"aviso: layout de {args.tabela} não passou na validação",
              file=sys.stderr)

    saida = Path(args.saida or f"{Path(args.tabela).stem.lower()}.csv")
    campos_data = {c.nome for c in tab.campos if c.tipo == bf.TIPO_DATE}
    colunas = [c.nome for c in tab.campos]

    n = 0
    with open(saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        w.writeheader()
        for linha in tab.registros():
            if args.datas_iso:
                for nome in campos_data:
                    linha[nome] = bf.data_para_iso(linha[nome])
            w.writerow(linha)
            n += 1

    print(f"{n:,} registros de {args.tabela} ({tab.descricao})")
    print(f"CSV gerado em: {saida.resolve()}")


if __name__ == "__main__":
    main()
