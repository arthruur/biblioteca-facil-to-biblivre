"""
Carrega os leitores do Biblioteca Fácil (`T04_LEIT`) no BibLivre 5.

    # 1. relatório, sem escrever nada
    python scripts/inserir_leitores.py saida

    # 2. grava de verdade (uma única transação)
    python scripts/inserir_leitores.py saida --executar --mapa-out saida/leitores_mapa.csv

O modelo de dados (users + users_values + users_fields), a preservação dos ids
e o que não tem para onde ir estão documentados em `biblio.biblivre.leitores`.

DEPOIS DESTE PASSO: reinicie o Tomcat. `UserFields` e `Translations` são caches
estáticos — sem reiniciar, os campos novos não aparecem no formulário.
"""

import argparse
import csv

from biblio.biblivre import leitores
from biblio.legado import tabela

from _comum import args_db, conectar, console_utf8, encerrar


def main():
    console_utf8()
    p = argparse.ArgumentParser(
        description="Carrega os leitores do Biblioteca Fácil no BibLivre 5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sem --executar o script só relata o que faria; nada é escrito.")
    p.add_argument("pasta", nargs="?", default="saida",
                   help="pasta com os .dat extraídos do .bkp (padrão: saida)")
    p.add_argument("--executar", action="store_true",
                   help="grava de verdade (uma transação; sem isto é só relatório)")
    p.add_argument("--mapa-out", metavar="ARQUIVO",
                   help="CSV de conferência: numleitor, user_id, nome, status")
    p.add_argument("--campos-extras", choices=("novos", "obs", "descartar"),
                   default="novos",
                   help="destino dos campos que o BibLivre não tem "
                        "(padrão: novos, cria em users_fields)")
    p.add_argument("--offset-id", type=int, default=0,
                   help="soma este valor ao NUMLEITOR para formar o users.id")
    p.add_argument("--email-obrigatorio", action="store_true",
                   help="mantém users_fields.required do email (padrão: desmarca)")
    p.add_argument("--permitir-existentes", action="store_true",
                   help="prossegue mesmo com leitores já cadastrados")
    args_db(p)
    args = p.parse_args()

    tab = tabela.carregar(args.pasta, "T04_LEIT.dat")
    linhas = list(tab.registros())
    print(f"{len(linhas):,} leitores em T04_LEIT ({tab.descricao})")

    plano = leitores.montar(linhas, args.campos_extras, args.offset_id)
    usuarios, valores = plano["usuarios"], plano["valores"]
    est = plano["estatisticas"]

    print(f"  {est['ativos']:,} ativos, {est['inativos']:,} inativos "
          f"(excluídos ou desativados no Biblioteca Fácil)")
    print(f"  ids: {usuarios[0][0]} a {usuarios[-1][0]}"
          + (f" (NUMLEITOR + {args.offset_id})" if args.offset_id
             else " (o próprio NUMLEITOR)"))
    print(f"  {len(valores):,} valores de campo em users_values")
    print(f"  endereço: {est['endereco_separado']:,} com número separado, "
          f"{est['endereco_inteiro']:,} inteiros em address")
    if plano["nascimentos_invalidos"]:
        print(f"  {len(plano['nascimentos_invalidos'])} data(s) de nascimento "
              f"fora do intervalo válido, descartada(s): "
              f"{plano['nascimentos_invalidos'][:4]}")
    if plano["emails_estranhos"]:
        print(f"  {len(plano['emails_estranhos'])} email(s) sem '@', migrados "
              f"como estão: {plano['emails_estranhos']}")
    if est["fotos_nao_migradas"]:
        print(f"  {est['fotos_nao_migradas']} foto(s) não migrada(s) — só o "
              f"caminho antigo vai nas observações")
    if est["extras_descartados"]:
        print(f"  {est['extras_descartados']:,} valores de campos extras "
              f"descartados (--campos-extras descartar)")
    print("  preenchimento por campo: " + ", ".join(
        f"{k.split(':', 1)[1]}={v:,}"
        for k, v in sorted(est.items()) if k.startswith("campo:")))

    con = conectar(args)
    try:
        ja = leitores.contar(con)
        if ja and not args.permitir_existentes:
            recado = (f"já existem {ja:,} usuários em {args.schema}.users. "
                      f"Gravar duplicaria o cadastro e os ids colidiriam. "
                      f"Apague o usuário de teste (e o empréstimo de teste, que "
                      f"aponta para ele) ou use --offset-id / "
                      f"--permitir-existentes.")
            # Em relatório isto é só um aviso: o dry-run precisa mostrar o resto
            # da conferência mesmo com a base ocupada.
            if args.executar:
                encerrar(recado)
            print(f"  ATENÇÃO: {recado}")

        faltando = leitores.faltando(con)
        if args.campos_extras == "novos":
            print("\ncampos a criar em users_fields: "
                  + (", ".join(c[0] for c in faltando) or "nenhum"))

        orfas = leitores.chaves_orfas(con, valores, faltando)
        if orfas:
            encerrar(f"chaves sem linha em users_fields: {orfas}")

        if args.mapa_out:
            with open(args.mapa_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["numleitor", "user_id", "nome", "status"])
                for usuario, linha in zip(usuarios, linhas):
                    w.writerow([linha["T04_NUMLEITOR"], usuario[0], usuario[1],
                                usuario[3]])
            print(f"mapa de conferência -> {args.mapa_out}")

        print("\nexemplo do primeiro leitor:")
        print(f"  users: id={usuarios[0][0]} name={usuarios[0][1]!r} "
              f"status={usuarios[0][3]} created={usuarios[0][4]}")
        for v in valores:
            if v[0] != usuarios[0][0]:
                break
            print(f"  {v[1]:18s} = {v[2]!r}")

        if not args.executar:
            print("\nNada foi escrito (rode com --executar para gravar).")
            return

        info = leitores.inserir(
            con, plano, campos_faltando=faltando,
            criar_campos=(args.campos_extras == "novos"),
            email_obrigatorio=args.email_obrigatorio)
        con.commit()

        print(f"\n{info['leitores']:,} leitores inseridos em {args.schema}.users "
              f"e {info['valores']:,} valores em users_values.")
        if info["campos_criados"]:
            print(f"{len(info['campos_criados'])} campos criados em "
                  f"users_fields, com as traduções em global.translations.")
        print("REINICIE O TOMCAT antes de conferir: UserFields e Translations "
              "são caches estáticos (StaticBO), carregados uma vez por schema — "
              "sem reiniciar, os campos novos não aparecem no formulário.")
        print("Depois confira em Circulação → Usuários: busque um leitor, abra "
              "a ficha e veja se os campos e a data de nascimento aparecem "
              "certos.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
