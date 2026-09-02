"""
Leitores (`users` + `users_values` + `users_fields`) no BibLivre 5.

    from biblio.biblivre import conexao, leitores
    from biblio.legado import tabela

    linhas = list(tabela.carregar("saida/", "T04_LEIT.dat").registros())
    plano = leitores.montar(linhas)
    con = conexao.conectar()
    leitores.inserir(con, plano, campos_faltando=leitores.faltando(con))
    con.commit()

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

import re
import unicodedata
from collections import Counter
from datetime import date

from biblio.legado import tabela as bf

from .conexao import USUARIO_PADRAO

TIPO_LEITOR = 1          # users_types.id 1 = "Leitor" (3 itens, 15 dias)
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

# `created` é NOT NULL com DEFAULT now(): passar NULL explicitamente viola a
# restrição, então o coalesce cobre o único leitor sem T04_DATACADASTRO.
SQL_USER = """
INSERT INTO users (id, name, type, status, created, created_by, name_ascii)
VALUES (%s, %s, %s, %s, coalesce(%s::timestamp, now()), %s, %s)
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


def montar(leitores, modo_extras: str = "novos", offset: int = 0) -> dict:
    """
    Transforma as linhas de `T04_LEIT` no que vai para `users` e `users_values`.

    Não toca no banco: devolve um plano conferível (é o mesmo objeto que o
    dry-run imprime e que `inserir` executa, então o que se confere é
    exatamente o que se grava).
    """
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

    return {
        "usuarios": usuarios,
        "valores": valores,
        "estatisticas": est,
        "nascimentos_invalidos": nasc_invalidas,
        "emails_estranhos": emails_estranhos,
    }


def faltando(con) -> list[tuple]:
    """Quais dos campos extras ainda não existem em `users_fields`."""
    with con.cursor() as cur:
        cur.execute("SELECT key FROM users_fields")
        existentes = {k for (k,) in cur.fetchall()}
    return [c for c in CAMPOS_NOVOS if c[0] not in existentes]


def chaves_orfas(con, valores: list[tuple], campos_faltando: list[tuple]) -> list[str]:
    """
    Chaves de `users_values` que não teriam linha em `users_fields`.

    Há FK: gravar uma dessas quebraria a transação inteira no meio, então o
    chamador checa antes.
    """
    with con.cursor() as cur:
        cur.execute("SELECT key FROM users_fields")
        existentes = {k for (k,) in cur.fetchall()}
    usadas = {v[1] for v in valores}
    return sorted(usadas - existentes - {c[0] for c in campos_faltando})


def contar(con) -> int:
    with con.cursor() as cur:
        cur.execute("SELECT count(*) FROM users")
        (n,) = cur.fetchone()
    return n


def inserir(con, plano: dict, campos_faltando: list[tuple] | None = None,
            criar_campos: bool = True, email_obrigatorio: bool = False,
            usuario: int = USUARIO_PADRAO) -> dict:
    """
    Grava leitores, valores e (opcionalmente) os campos novos com as traduções.

    Não commita. Ajusta `users_id_seq` no fim: sem isso o próximo leitor
    cadastrado pela tela reusaria um id (`UserDAO.save` chama
    `getNextSerial('users_id_seq')`).
    """
    from psycopg2.extras import execute_batch

    usuarios, valores = plano["usuarios"], plano["valores"]
    campos_faltando = campos_faltando or []
    criados = []

    with con.cursor() as cur:
        if criar_campos:
            for chave, tipo, tam, ordem, _, trad in campos_faltando:
                cur.execute(SQL_CAMPO, (chave, tipo, tam, ordem, usuario))
                criados.append(chave)
                for idioma, texto in zip(IDIOMAS, trad):
                    cur.execute(
                        "SELECT 1 FROM global.translations "
                        "WHERE language = %s AND key = %s",
                        (idioma, PREFIXO_TRAD + chave))
                    if not cur.fetchone():
                        cur.execute(SQL_TRAD, (idioma, PREFIXO_TRAD + chave,
                                               texto, usuario, usuario))

        # 447 dos 2.743 leitores têm email. `required` é validado no formulário
        # (`user/Validator.java`), não no banco: deixar marcado obrigaria a
        # preencher email para salvar qualquer edição depois.
        if not email_obrigatorio:
            cur.execute("UPDATE users_fields SET required = false, "
                        "modified = now() WHERE key = 'email'")

        execute_batch(cur, SQL_USER, usuarios, page_size=500)
        execute_batch(cur, SQL_VALOR, valores, page_size=1000)

        cur.execute("SELECT setval('users_id_seq', %s, true)",
                    (max(u[0] for u in usuarios),))

    return {
        "leitores": len(usuarios),
        "valores": len(valores),
        "campos_criados": criados,
    }