"""
Carrega os leitores do Biblioteca Fácil (`T04_LEIT`) no BibLivre 5.

    # 1. relatório, sem escrever nada
    python scripts/inserir_leitores.py saida

    # 2. grava de verdade (uma única transação)
    python scripts/inserir_leitores.py saida --executar --mapa-out saida/leitores_mapa.csv

POR QUE POR SQL, DE NOVO
------------------------
O BibLivre não tem importação de usuários por arquivo — a única entrada é o
formulário de Circulação, um leitor por vez. Inserir por SQL é o caminho que o
próprio BibLivre usa quando migra do Biblivre 3 (`UserDAO.saveFromBiblivre3`,
que grava `users` com id explícito e chama `global.update_user_value` para cada
campo).

O MODELO DE DADOS (verificado no fonte e no banco)
-------------------------------------------------
`users` guarda só o essencial — id, name, type, status, name_ascii. Todo o
resto é chave/valor em `users_values (user_id, key, value, ascii)`, e as chaves
válidas são as linhas de `users_fields`. Ou seja: campo que não existe em
`users_fields` não pode nem ser gravado (há FK).

  * `users.status` vem de `UserStatus`: active, pending_issues, inactive,
    blocked (`toString()` é minúsculo). `LendingBO.checkLending` recusa
    empréstimo para inactive e blocked, e `UserDAO.search` esconde inactive por
    padrão — exatamente o comportamento que queremos para os
    desativados/excluídos do Biblioteca Fácil.
  * `name_ascii` e `users_values.ascii` são as colunas de busca, usadas com
    `ilike`. O BibLivre as preenche com `TextUtils.removeDiacriticals`, que só
    decompõe em NFD e remove os acentos — não mexe em caixa.
  * O rótulo de cada campo na tela é a tradução
    `circulation.custom.user_field.<chave>` em `global.translations`. Campo novo
    sem tradução aparece sem nome, por isso este script insere as três (pt-BR,
    en-US, es) junto com o campo.
  * `users_fields.required` é validado no formulário (`user/Validator.java`),
    não no banco: dá para inserir sem email, mas depois a tela exigiria
    preencher para salvar qualquer edição. Como só 447 dos 2.743 leitores têm
    email, o script desmarca `required` do campo `email` (use
    `--email-obrigatorio` para não desmarcar).

IDS PRESERVADOS
---------------
`T04_NUMLEITOR` é 1..2743 sem buracos, então o id do Biblioteca Fácil vira o
`users.id` — o número que a biblioteca já usa continua valendo, e é o que o
BibLivre faz na migração do Biblivre 3 (`dto.setId(rs.getInt("serial"))`).
Depois da carga a sequence é ajustada com `setval`, senão o próximo leitor
cadastrado pela tela colidiria. Se a tabela já tiver gente (ex.: o usuário de
teste da conferência), use `--offset-id N`.

O QUE NÃO TEM PARA ONDE IR
--------------------------
`T04_FOTO` guarda um caminho da máquina antiga
(`C:\\MTG\\BibFacil8\\FotoLeitor\\...`) e as imagens não estão no `.bkp` — só o
caminho vai para as observações. `T04_SEXO`, `T04_TURNO` e `T04_TURMA`
(numéricos) estão zerados em todo o cadastro; valem os equivalentes texto
`SEXO2`/`TURNO2`.
"""

import argparse
import csv
import getpass
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bf_tabela as bf

TIPO_LEITOR = 1          # users_types.id 1 = "Leitor" (3 itens, 15 dias)
USUARIO_PADRAO = 1       # logins.id do admin da instalação
PREFIXO_TRAD = "circulation.custom.user_field."
IDIOMAS = ("pt-BR", "en-US", "es")

ANO_NASC_MIN = 1900

# Campos que a instalação padrão já tem, copiados sem transformação.
DIRETO = [
    ("T04_INTERNET", "email"),
    ("T04_IDENTIDADE", "id_rg"),
    ("T04_CPF", "id_cpf"),
    ("T04_CEP", "address_zip"),
    ("T04_CIDADE", "address_city"),
    ("T04_ESTADO", "address_state"),
    ("T04_TELEFONE1", "phone_home"),
    ("T04_TELEFONE2", "phone_cel"),
]

# Campos do Biblioteca Fácil sem equivalente no BibLivre. max_length é o
# tamanho do campo no .dat menos o \x00 terminador.
CAMPOS_NOVOS = [
    # (chave, tipo, max_length, sort_order, campo BF, (pt-BR, en-US, es))
    ("address_district", "string", 20, 16, "T04_BAIRRO",
     ("Bairro", "District", "Barrio")),
    ("address_reference", "string", 40, 17, "T04_PONTOREFER",
     ("Ponto de Referência", "Landmark", "Punto de Referencia")),
    ("name_mother", "string", 40, 18, "T04_NOMEMAE",
     ("Nome da Mãe", "Mothers Name", "Nombre de la Madre")),
    ("name_father", "string", 40, 19, "T04_NOMEPAI",
     ("Nome do Pai", "Fathers Name", "Nombre del Padre")),
    ("birthplace", "string", 30, 20, "T04_NATURALIDADE",
     ("Naturalidade", "Place of Birth", "Naturalidad")),
    ("education", "string", 30, 21, "T04_ESCOLARIDADE",
     ("Escolaridade", "Education", "Escolaridad")),
    ("contact_name", "string", 20, 22, "T04_NOMECONTATO",
     ("Nome do Contato", "Contact Name", "Nombre del Contacto")),
    ("contact_phone", "string", 20, 23, "T04_FONECONTATO",
     ("Telefone do Contato", "Contact Phone", "Teléfono del Contacto")),
    ("registration", "string", 10, 24, "T04_MATRICULA",
     ("Matrícula", "Registration No.", "Matrícula")),
]

# Rótulos usados quando os campos extras vão para as observações.
ROTULO_OBS = {chave: trad[0] for chave, _, _, _, _, trad in CAMPOS_NOVOS}

# Rua e número vêm juntos em T04_ENDERECO ("RUA LEOVIGILDO RIBEIRO nº 476").
# O padrão só separa quando o número está no fim — endereço com número no meio
# ("AVENIDA PONTEVEDRA, 501 - FAZENDA ALTO") fica inteiro em `address`, porque
# chutar ali erraria mais do que acertaria.
RE_NUMERO = re.compile(r"^(.*?)[,\s]*(?:n[º°o\.]*\s*)?(\d{1,6}[A-Za-z]?)$", re.I)

SQL_USER = """
INSERT INTO users (id, name, type, status, created, created_by, name_ascii)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
SQL_VALOR = """
INSERT INTO users_values (user_id, key, value, ascii) VALUES (%s, %s, %s, %s)
"""
SQL_CAMPO = """
INSERT INTO users_fields (key, type, required, max_length, sort_order, created_by)
VALUES (%s, %s, false, %s, %s, %s)
"""
SQL_TRAD = """
INSERT INTO global.translations (language, key, text, created_by, modified_by,
                                 user_created)
VALUES (%s, %s, %s, %s, %s, true)
"""


def sem_acento(texto):
    """TextUtils.removeDiacriticals: NFD e fora os acentos, sem mexer na caixa."""
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if not unicodedata.combining(c))


def _ident(nome):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
        sys.exit(f"nome de schema inválido: {nome!r}")
    return f'"{nome}"'


def separar_endereco(endereco):
    m = RE_NUMERO.match(endereco)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2)
    return endereco, ""


def data_br(dias):
    """
    Data no formato que o formulário do BibLivre lê e escreve. O valor é texto
    livre em `users_values` (na migração do Biblivre 3 o BibLivre copia a string
    da origem sem converter), e o campo `birthday` é forçado para o tipo DATE em
    `UserFieldsDAO`, renderizado pelo date picker no padrão do idioma —
    dd/mm/aaaa em pt-BR.
    """
    iso = bf.data_para_iso(dias)
    if not iso:
        return ""
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def montar(leitores, modo_extras, offset):
    """Monta as linhas de `users` e `users_values`, e junta as estatísticas."""
    usuarios, valores = [], []
    est = Counter()
    nasc_invalidas, emails_estranhos = [], []
    hoje = date.today()

    for l in leitores:
        num = l["T04_NUMLEITOR"]
        user_id = num + offset
        nome = l["T04_LEITOR"].strip()

        inativo = bool(l["T04_EXCLUSAO"]) or bool(l["T04_DESATIVADO"])
        est["inativos" if inativo else "ativos"] += 1
        criado = bf.data_para_iso(l["T04_DATACADASTRO"]) or None
        if not criado:
            est["sem_data_cadastro"] += 1

        usuarios.append((user_id, nome, TIPO_LEITOR,
                         "inactive" if inativo else "active",
                         criado, USUARIO_PADRAO, sem_acento(nome)))

        campos = {}
        for origem, chave in DIRETO:
            texto = l[origem].strip()
            if texto:
                campos[chave] = texto
        if campos.get("email") and "@" not in campos["email"]:
            emails_estranhos.append((num, campos["email"]))

        endereco = l["T04_ENDERECO"].strip()
        if endereco:
            rua, numero = separar_endereco(endereco)
            campos["address"] = rua
            if numero:
                campos["address_number"] = numero
                est["endereco_separado"] += 1
            else:
                est["endereco_inteiro"] += 1

        # gender é do tipo `list`, com as opções traduzidas em
        # circulation.custom.user_field.gender.1 (Masculino) e .2 (Feminino).
        sexo = l["T04_SEXO2"].strip().upper()
        if sexo in ("M", "F"):
            campos["gender"] = "1" if sexo == "M" else "2"
        elif sexo:
            est["sexo_desconhecido"] += 1

        nasc = bf.data_para_iso(l["T04_DATANASC"])
        if nasc:
            ano = int(nasc[:4])
            if ANO_NASC_MIN <= ano <= hoje.year:
                campos["birthday"] = data_br(l["T04_DATANASC"])
            else:
                nasc_invalidas.append((num, nasc))

        # Observações: as duas linhas de OBS, mais o que não tem campo próprio.
        obs = [t for t in (l["T04_OBS1"].strip(), l["T04_OBS2"].strip()) if t]
        extras = [(chave, l[origem].strip())
                  for chave, _, _, _, origem, _ in CAMPOS_NOVOS
                  if l[origem].strip()]

        if modo_extras == "novos":
            for chave, texto in extras:
                campos[chave] = texto
        elif modo_extras == "obs":
            obs += [f"{ROTULO_OBS[chave]}: {texto}" for chave, texto in extras]
        else:
            est["extras_descartados"] += len(extras)

        # Turma/turno (4 leitores) e o caminho da foto (14) não ganham campo:
        # volume pequeno demais para justificar coluna nova, e a foto em si não
        # está no backup.
        turma = " / ".join(t for t in (l["T04_TURMA"].strip(),
                                       l["T04_TURNO2"].strip()) if t)
        if turma:
            obs.append(f"Turma: {turma}")
        if l["T04_FOTO"].strip():
            obs.append(f"Foto no sistema antigo: {l['T04_FOTO'].strip()}")
            est["fotos_nao_migradas"] += 1

        if obs:
            campos["obs"] = "\n".join(obs)

        for chave, texto in campos.items():
            valores.append((user_id, chave, texto, sem_acento(texto)))
            est[f"campo:{chave}"] += 1

    return usuarios, valores, est, nasc_invalidas, emails_estranhos


def conectar(args):
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 não instalado. Rode: pip install -r requirements.txt")

    senha = args.senha or os.environ.get("PGPASSWORD")
    if not senha:
        senha = getpass.getpass(f"Senha de {args.user}@{args.host}: ")
    con = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname,
                           user=args.user, password=senha)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(f"SET search_path TO {_ident(args.schema)}, public")
    return con


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

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

    p.add_argument("--host", default="localhost")
    p.add_argument("--port", default="5432")
    p.add_argument("--dbname", default="biblivre4")
    p.add_argument("--user", default="biblivre")
    p.add_argument("--senha", help="senha do PostgreSQL (ou use PGPASSWORD)")
    p.add_argument("--schema", default="single")
    args = p.parse_args()

    tabela = bf.carregar(args.pasta, "T04_LEIT.dat")
    leitores = list(tabela.registros())
    print(f"{len(leitores):,} leitores em T04_LEIT ({tabela.descricao})")

    usuarios, valores, est, nasc_invalidas, emails = montar(
        leitores, args.campos_extras, args.offset_id)

    print(f"  {est['ativos']:,} ativos, {est['inativos']:,} inativos "
          f"(excluídos ou desativados no Biblioteca Fácil)")
    print(f"  ids: {usuarios[0][0]} a {usuarios[-1][0]}"
          + (f" (NUMLEITOR + {args.offset_id})" if args.offset_id else
             " (o próprio NUMLEITOR)"))
    print(f"  {len(valores):,} valores de campo em users_values")
    print(f"  endereço: {est['endereco_separado']:,} com número separado, "
          f"{est['endereco_inteiro']:,} inteiros em address")
    if nasc_invalidas:
        print(f"  {len(nasc_invalidas)} data(s) de nascimento fora de "
              f"{ANO_NASC_MIN}-{date.today().year}, descartada(s): "
              f"{nasc_invalidas[:4]}")
    if emails:
        print(f"  {len(emails)} email(s) sem '@', migrados como estão: {emails}")
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
        with con.cursor() as cur:
            cur.execute("SELECT count(*) FROM users")
            (ja,) = cur.fetchone()
            if ja and not args.permitir_existentes:
                cur.execute("SELECT id, name FROM users ORDER BY id LIMIT 5")
                # Em relatório isto é só um aviso: o dry-run precisa mostrar o
                # resto da conferência mesmo com a base ocupada.
                recado = (
                    f"já existem {ja:,} usuários em {args.schema}.users "
                    f"({cur.fetchall()}). Gravar duplicaria o cadastro e os ids "
                    f"colidiriam. Apague o usuário de teste (e o empréstimo de "
                    f"teste, que aponta para ele) ou use --offset-id / "
                    f"--permitir-existentes.")
                if args.executar:
                    sys.exit(f"ERRO: {recado}")
                print(f"  ATENÇÃO: {recado}")

            cur.execute("SELECT key FROM users_fields")
            existentes = {k for (k,) in cur.fetchall()}
            faltando = [c for c in CAMPOS_NOVOS if c[0] not in existentes]
            if args.campos_extras == "novos":
                print("\ncampos a criar em users_fields: "
                      + (", ".join(c[0] for c in faltando) or "nenhum"))
            usadas = {v[1] for v in valores}
            orfas = usadas - existentes - {c[0] for c in faltando}
            if orfas:
                sys.exit(f"ERRO: chaves sem linha em users_fields: {sorted(orfas)}")

        if args.mapa_out:
            with open(args.mapa_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["numleitor", "user_id", "nome", "status"])
                for usuario, l in zip(usuarios, leitores):
                    w.writerow([l["T04_NUMLEITOR"], usuario[0], usuario[1],
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

        from psycopg2.extras import execute_batch
        with con.cursor() as cur:
            if args.campos_extras == "novos":
                for chave, tipo, tam, ordem, _, trad in faltando:
                    cur.execute(SQL_CAMPO, (chave, tipo, tam, ordem,
                                            USUARIO_PADRAO))
                    for idioma, texto in zip(IDIOMAS, trad):
                        cur.execute(
                            "SELECT 1 FROM global.translations "
                            "WHERE language = %s AND key = %s",
                            (idioma, PREFIXO_TRAD + chave))
                        if not cur.fetchone():
                            cur.execute(SQL_TRAD, (idioma, PREFIXO_TRAD + chave,
                                                   texto, USUARIO_PADRAO,
                                                   USUARIO_PADRAO))
            if not args.email_obrigatorio:
                cur.execute("UPDATE users_fields SET required = false, "
                            "modified = now() WHERE key = 'email'")

            execute_batch(cur, SQL_USER, usuarios, page_size=500)
            execute_batch(cur, SQL_VALOR, valores, page_size=1000)

            # Sem isto o próximo leitor cadastrado pela tela reusaria um id:
            # UserDAO.save chama getNextSerial('users_id_seq').
            cur.execute("SELECT setval('users_id_seq', %s, true)",
                        (max(u[0] for u in usuarios),))
        con.commit()

        print(f"\n{len(usuarios):,} leitores inseridos em {args.schema}.users "
              f"e {len(valores):,} valores em users_values.")
        if args.campos_extras == "novos" and faltando:
            print(f"{len(faltando)} campos criados em users_fields, com as "
                  f"traduções em global.translations.")
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
