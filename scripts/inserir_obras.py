"""
Carrega `obras.mrc` direto em `biblio_records`, na base principal.

    # relatório, sem escrever nada
    python scripts/inserir_obras.py saida/obras.mrc

    # grava, numa transação só
    python scripts/inserir_obras.py saida/obras.mrc --executar

Por que por SQL e não pela tela, e o que exatamente isto reproduz do
`BiblioRecordBO.save`: `biblio.biblivre.obras` e docs/IMPORTACAO_BIBLIVRE.md.

DEPOIS DESTE PASSO: Administração → Manutenção → Reindexar. Sem isso os
registros existem mas não aparecem na busca.
"""

import argparse
import csv

from biblio.biblivre import marc, obras

from _comum import args_db, conectar, console_utf8, encerrar


def main():
    console_utf8()
    p = argparse.ArgumentParser(
        description="Carrega obras.mrc direto em biblio_records (base principal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.")
    p.add_argument("mrc", help="obras.mrc gerado por gerar_marc.py")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--database", default=obras.DATABASE,
                   help=f"base de destino (padrão: {obras.DATABASE})")
    p.add_argument("--usuario", type=int, default=1,
                   help="created_by (padrão: 1, o admin)")
    p.add_argument("--mapa-out", metavar="ARQUIVO",
                   help="CSV de conferência: 035, record_id")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com registros já na base (risco de duplicar)")
    args_db(p)
    args = p.parse_args()

    registros = marc.ler_mrc(args.mrc)
    print(f"{len(registros):,} registros em {args.mrc}")

    # Sem 035 $a o exemplar não acha a sua obra depois — barra antes de gravar.
    faltando = [i for i, r in enumerate(registros)
                if not (r.get("035") and r["035"]["a"])]
    if faltando:
        encerrar(f"{len(faltando)} registro(s) sem 035 $a — o casamento dos "
                 f"exemplares depende dele. Índices: {faltando[:5]}")

    con = conectar(args)
    try:
        ja_existem = obras.contar_todos(con)
        if ja_existem and not args.permitir_existentes:
            encerrar(f"já existem {ja_existem:,} registros em "
                     f"{args.schema}.biblio_records. A amostra de teste precisa "
                     f"ser removida antes da carga real. Use "
                     f"--permitir-existentes se for intencional.")

        # nextval() NÃO é revertido por rollback no PostgreSQL, então o dry-run
        # projeta os ids em vez de consumi-los.
        ids = obras.projetar_ids(con, len(registros))
        print(f"ids atribuídos: {ids[0]}..{ids[-1]}  database={args.database}  "
              f"material={obras.MATERIAL}  created_by={args.usuario}")

        if args.mapa_out:
            with open(args.mapa_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id_origem", "record_id"])
                w.writerows((r["035"]["a"], i) for r, i in zip(registros, ids))
            print(f"mapa de conferência -> {args.mapa_out}")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            print("Os ids acima são uma PROJEÇÃO do valor atual da sequence; "
                  "o dry-run não a consome.")
            con.rollback()
            return

        # Consome a sequence de fato e confere que casa com o projetado (nada
        # mais deveria estar gravando nesta base durante a migração).
        reais = obras.reservar_ids(con, len(registros))
        if reais != ids:
            encerrar("a sequence avançou entre a projeção e a gravação "
                     "(há outra sessão escrevendo?). Nada foi gravado.")

        obras.inserir(con, registros, database=args.database,
                      usuario=args.usuario, ids=reais)
        con.commit()

        print(f"\n{len(registros):,} registros inseridos em "
              f"{args.schema}.biblio_records (database={args.database}).")
        print("PRÓXIMO PASSO: Administração → Manutenção → Reindexar. Sem isso "
              "os registros não aparecem na busca.")
        print("Depois do reindex, rode o inserir_exemplares.py.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
