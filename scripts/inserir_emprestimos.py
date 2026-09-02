"""
Carrega a circulação do Biblioteca Fácil no BibLivre 5: empréstimos
(`T13_MOVM` + `T11_MOVI`), multas e reservas (`T15_RESE`).

    # 1. relatório, sem escrever nada
    python scripts/inserir_emprestimos.py saida

    # 2. grava de verdade (uma única transação)
    python scripts/inserir_emprestimos.py saida --executar

Depende dos dois passos anteriores terem rodado com `--mapa-out`: é do mapa de
exemplares que sai o `holding_id` (pelo tombo) e do de leitores que sai o
`user_id`. Como os dois modelos se encaixam e o que fica de fora:
`biblio.biblivre.circulacao`.
"""

import argparse
import os

from biblio.biblivre import circulacao

from _comum import args_db, conectar, console_utf8, encerrar


def main():
    console_utf8()
    p = argparse.ArgumentParser(
        description="Carrega empréstimos, multas e reservas no BibLivre 5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.")
    p.add_argument("pasta", nargs="?", default="saida",
                   help="pasta com os .dat extraídos do .bkp (padrão: saida)")
    p.add_argument("--mapa-exemplares", help="padrão: <pasta>/exemplares_mapa.csv")
    p.add_argument("--mapa-leitores", help="padrão: <pasta>/leitores_mapa.csv")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--apenas-abertos", action="store_true",
                   help="migra só os empréstimos não devolvidos")
    p.add_argument("--incluir-excluidos", action="store_true",
                   help="inclui as movimentações apagadas no sistema antigo")
    p.add_argument("--reservas-desde", type=int, default=2026, metavar="ANO",
                   help="só migra reservas pendentes deste ano em diante "
                        "(padrão: 2026; use 0 para todas)")
    p.add_argument("--sem-reservas", action="store_true",
                   help="não migra reserva nenhuma")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com empréstimos já na base")
    args_db(p)
    args = p.parse_args()

    tabelas = circulacao.carregar_tabelas(args.pasta, args.sem_reservas)
    print(f"{len(tabelas['movi']):,} movimentações (T11_MOVI) sob "
          f"{len(tabelas['movm']):,} empréstimos (T13_MOVM), "
          f"{len(tabelas['rese']):,} reservas (T15_RESE)")

    caminho_ex = args.mapa_exemplares or os.path.join(args.pasta,
                                                      "exemplares_mapa.csv")
    caminho_le = args.mapa_leitores or os.path.join(args.pasta,
                                                    "leitores_mapa.csv")
    try:
        tombo_de = circulacao.ler_mapa(caminho_ex, "numacervo", "tombo",
                                       "mapa de exemplares")
        record_de = {k: int(v) for k, v in circulacao.ler_mapa(
            caminho_ex, "numacervo", "record_id", "mapa de exemplares").items()}
        user_de = {k: int(v) for k, v in circulacao.ler_mapa(
            caminho_le, "numleitor", "user_id", "mapa de leitores").items()}
    except (FileNotFoundError, ValueError) as e:
        encerrar(str(e))
    print(f"  mapas: {len(tombo_de):,} exemplares, {len(user_de):,} leitores")

    con = conectar(args)
    try:
        contagem = circulacao.contar(con)
        if contagem["emprestimos"] and not args.permitir_existentes:
            recado = (f"já existem {contagem['emprestimos']:,} empréstimos em "
                      f"{args.schema}.lendings (o empréstimo de teste da "
                      f"conferência conta). Apague-os ou use "
                      f"--permitir-existentes.")
            # Só barra na gravação; em relatório o dry-run segue.
            if args.executar:
                encerrar(recado)
            print(f"  ATENÇÃO: {recado}")

        ctx = circulacao.contexto_do_banco(con)
        print(f"  banco: {len(ctx['holding_de']):,} exemplares, "
              f"{len(ctx['ids_usuarios']):,} usuários")

        faltam = sorted(set(user_de.values()) - ctx["ids_usuarios"])
        if faltam:
            recado = (f"{len(faltam):,} user_id do mapa de leitores não existem "
                      f"em {args.schema}.users (ex.: {faltam[:5]}). Rode o "
                      f"inserir_leitores.py --executar primeiro.")
            if args.executar:
                encerrar(recado)
            print(f"  ATENÇÃO: {recado}")

        plano = circulacao.montar(
            tabelas["movm"], tabelas["movi"], tabelas["rese"],
            tombo_de, record_de, user_de, ctx["holding_de"],
            id_base=ctx["id_base"], incluir_excluidos=args.incluir_excluidos,
            apenas_abertos=args.apenas_abertos,
            reservas_desde=args.reservas_desde)

        est = plano["estatisticas"]
        lendings = plano["lendings"]
        print(f"\n{len(lendings):,} empréstimos a inserir "
              f"({est['abertos']:,} em aberto, {est['devolvidos']:,} devolvidos)")
        print(f"  {len(plano['multas']):,} multas, "
              f"{len(plano['reservas']):,} reservas")
        if est["excluidos"]:
            print(f"  {est['excluidos']:,} movimentações excluídas no sistema "
                  f"antigo, fora (use --incluir-excluidos)")
        if est["devolvidos_ignorados"]:
            print(f"  {est['devolvidos_ignorados']:,} devolvidos ignorados "
                  f"(--apenas-abertos)")
        for motivo, itens in plano["descartes"].items():
            print(f"  ATENÇÃO: {len(itens):,} descartados por {motivo} "
                  f"(ex.: {itens[:3]})")
        if est["sem_data_emprestimo"]:
            print(f"  {est['sem_data_emprestimo']:,} sem data de empréstimo, "
                  f"usando a previsão/devolução como created")
        if est["multas_canceladas"]:
            print(f"  {est['multas_canceladas']} multa(s) cancelada(s) no "
                  f"sistema antigo, fora")
        if not args.sem_reservas:
            print(f"  reservas: {est['reservas_encerradas']:,} já encerradas e "
                  f"{est['reservas_antigas']:,} anteriores a "
                  f"{args.reservas_desde} ficaram fora")
        print("  empréstimos por ano: " + ", ".join(
            f"{k.split(':', 1)[1]}:{v:,}"
            for k, v in sorted(est.items()) if k.startswith("ano:")))

        # Duas linhas em aberto para o mesmo exemplar deixariam o acervo
        # incoerente: `LendingBO.isLent` acha as duas e a devolução resolveria
        # só uma.
        if plano["duplo_aberto"]:
            encerrar(f"{len(plano['duplo_aberto'])} exemplar(es) com mais de um "
                     f"empréstimo em aberto (holding_id "
                     f"{plano['duplo_aberto'][:5]}). Resolva na origem antes de "
                     f"carregar.")

        if lendings:
            l = lendings[0]
            print(f"\nexemplo do primeiro empréstimo: id={l[0]} holding_id={l[1]} "
                  f"user_id={l[2]} previsão={l[3]} devolução={l[4]} created={l[5]}")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            return
        if not lendings:
            encerrar("nada a inserir.")

        info = circulacao.inserir(con, plano)
        con.commit()

        print(f"\n{info['emprestimos']:,} empréstimos, {info['multas']:,} multas "
              f"e {info['reservas']:,} reservas inseridos.")
        print("Confira em Circulação → Empréstimo: abra um leitor com pendência "
              "e veja a lista de itens em atraso; e em Administração → "
              "Relatórios, o de devoluções em atraso.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
