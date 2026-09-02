"""
Cria os exemplares (holdings) no BibLivre 5, a partir do `exemplares.csv`.

    # 1. confere o que seria feito, sem escrever nada
    python scripts/inserir_exemplares.py saida/exemplares.csv

    # 2. executa de verdade (uma única transação)
    python scripts/inserir_exemplares.py saida/exemplares.csv --executar

Por que este passo existe (a importação por arquivo do BibLivre só cria
registros bibliográficos, nunca exemplares), o que o MARC do exemplar reproduz
e por que os tombos são gerados: `biblio.biblivre.exemplares`.
"""

import argparse
import csv

from biblio.biblivre import exemplares

from _comum import args_db, conectar, console_utf8, encerrar


def main():
    console_utf8()
    p = argparse.ArgumentParser(
        description="Cria os exemplares no BibLivre 5 a partir do exemplares.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.")
    p.add_argument("csv_exemplares", help="exemplares.csv gerado por gerar_marc.py")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--mapa-out", metavar="ARQUIVO",
                   help="CSV de conferência: numacervo, record_id, tombo")
    p.add_argument("--prefixo-tombo",
                   help="padrão: lido de configurations.cataloging.accession_number_prefix")
    p.add_argument("--ano-tombo", type=int,
                   help="usa este ano em todos os tombos, em vez do ano de aquisição")
    p.add_argument("--biblioteca", default="",
                   help="541 $a — biblioteca depositária (padrão: não preenche)")
    p.add_argument("--tipo-aquisicao", default=exemplares.TIPO_AQUISICAO_MIGRACAO,
                   help="541 $c — tipo de aquisição")
    p.add_argument("--usuario", type=int, default=1,
                   help="created_by (padrão: 1, o admin)")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com exemplares já na base (risco de duplicar)")
    args_db(p)
    args = p.parse_args()

    with open(args.csv_exemplares, encoding="utf-8-sig", newline="") as f:
        linhas = [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(f)]
    print(f"{len(linhas):,} exemplares no CSV")

    con = conectar(args)
    try:
        ja_existem = exemplares.contar(con)
        if ja_existem and not args.permitir_existentes:
            encerrar(f"já existem {ja_existem:,} exemplares em "
                     f"{args.schema}.biblio_holdings. Rodar de novo duplicaria "
                     f"tudo. Use --permitir-existentes se for intencional.")

        plano = exemplares.preparar_do_csv(
            con, linhas, schema=args.schema, prefixo_tombo=args.prefixo_tombo,
            ano_tombo=args.ano_tombo, biblioteca=args.biblioteca,
            tipo_aquisicao=args.tipo_aquisicao, usuario=args.usuario)

        print(f"prefixo de tombo: {plano['prefixo']!r} "
              f"(de {plano['origem_prefixo']})")
        print(f"{len(plano['mapa']):,} registros bibliográficos com 035 $a legível")
        if plano["sem_035"]:
            print(f"  ATENÇÃO: {len(plano['sem_035']):,} registros sem 035 $a "
                  f"(ids: {plano['sem_035'][:5]})")
        if plano["duplicados"]:
            print(f"  ATENÇÃO: {len(plano['duplicados']):,} valores de 035 $a "
                  f"repetidos — usando o primeiro de cada. Exemplos: "
                  f"{list(plano['duplicados'])[:3]}")

        valores = plano["valores"]
        print(f"{len(valores):,} exemplares casados com "
              f"{len(plano['registros_usados']):,} registros bibliográficos")
        if plano["nao_casados"]:
            faltando = sorted(set(plano["nao_casados"]))
            print(f"  ATENÇÃO: {len(plano['nao_casados']):,} exemplares sem "
                  f"registro correspondente ({len(faltando):,} ids distintos, "
                  f"ex.: {faltando[:5]})")
        if plano["orfaos"] > 0:
            print(f"  {plano['orfaos']:,} registros bibliográficos ficariam "
                  f"sem exemplar")
        if plano["anos_invalidos"]:
            amostra = [(n, d) for _, d, n in plano["anos_invalidos"][:3]]
            print(f"  {len(plano['anos_invalidos'])} data(s) de aquisição fora "
                  f"de {exemplares.ANO_MIN}-{exemplares.ANO_MAX}, tombo emitido "
                  f"no ano corrente: {amostra}")
        print("tombos por ano: " + ", ".join(
            f"{ano}:{qtd:,}" for ano, qtd in sorted(plano["por_ano"].items())))

        if args.mapa_out:
            with open(args.mapa_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["numacervo", "id_origem", "record_id", "tombo"])
                for linha, tombo in zip(linhas, plano["tombos"]):
                    achado = plano["mapa"].get(linha["id_origem"])
                    w.writerow([linha["numacervo"], linha["id_origem"],
                                achado[0] if achado else "", tombo])
            print(f"\nmapa de conferência -> {args.mapa_out}")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            return
        if not valores:
            encerrar("nada a inserir.")

        exemplares.gravar(con, valores)
        con.commit()
        print(f"\n{len(valores):,} exemplares inseridos em "
              f"{args.schema}.biblio_holdings.")
        print("Confira em Catalogação → Exemplares e imprima uma etiqueta de "
              "teste antes de gerar o backup.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
