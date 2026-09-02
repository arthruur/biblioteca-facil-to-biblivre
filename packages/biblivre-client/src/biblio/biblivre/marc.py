"""
Construção dos registros MARC21 / ISO 2709 que o BibLivre 5 entende.

    from biblio.biblivre import marc

    grupos = marc.agrupar_por_obra(linhas)      # exemplares -> obras
    registro = marc.montar_registro(grupos[0])  # pymarc.Record
    marc.escrever_mrc(registros, "obras.mrc")

Este módulo não fala com o banco: ele só sabe transformar linhas de acervo em
registros MARC (e de volta). Quem grava é `biblio.biblivre.obras`.

POR QUE 1 REGISTRO POR OBRA, E NÃO 1 POR EXEMPLAR
--------------------------------------------------
O Biblioteca Fácil grava cada exemplar físico como um registro separado do
acervo. A tentação é importar 1:1, mas isso não funciona no BibLivre — e a
razão está no código dele (github.com/Biblivre/Biblivre-5):

1. A importação de arquivo **só cria registros bibliográficos**.
   `cataloging/Handler.java:saveImport()` aceita BIBLIO, AUTHORITIES e
   VOCABULARY — nunca HOLDING. Não existe caminho de arquivo que crie
   exemplares.

2. Exemplar no BibLivre é um **registro MARC separado** (Leader de holdings,
   090 $a$b$c$d + 541), ligado ao bibliográfico por uma **FK no banco**
   (`HoldingDTO.setRecordId`). Essa FK não existe dentro do MARC, então
   nenhum arquivo consegue expressá-la.

3. **Empréstimo é feito contra exemplar, não contra registro bibliográfico**
   (`LendingBO.doLend(HoldingDTO, UserDTO, int)`). Sem exemplares, a
   biblioteca não empresta nada.

Ou seja: importar 1 registro por exemplar **não cria exemplar nenhum** — só
duplica fichas no catálogo (62 fichas idênticas do mesmo livro, no pior caso)
e ainda deixa o acervo inemprestável. As duas opções exigem um segundo passo
para os exemplares, então vale ficar com o catálogo correto.

O próprio BibLivre faz assim na migração dele do Biblivre 3, inserindo
holdings direto no banco com o `record_serial` (`DataMigrationDAO.java`).

AGRUPAMENTO: POR CONTEÚDO, NUNCA POR ISBN
------------------------------------------
Testamos agrupar por ISBN e o resultado foi perigoso: o maior grupo juntou
"Paixão - Doce Traição" (Maya Blake), "Felizes... Para Sempre?" (Raye Morgan)
e "Corações Blindados" (Diana Palmer) — três livros diferentes da Editora HR
cadastrados com o mesmo ISBN. ISBN neste acervo é digitado à mão e não é
confiável como identidade.

A chave usada é o conteúdo bibliográfico normalizado: título, subtítulo,
autor, editora, ano, volume e edição. O `volume` é essencial — sem ele, o
vol. 1 e o vol. 2 da mesma coleção viram um registro só.

O critério é deliberadamente conservador: **preferir separar demais a juntar
demais**. Separar a mais gera duas fichas para o mesmo livro, que o
bibliotecário funde em minutos no BibLivre. Juntar a mais faz uma obra
distinta desaparecer do catálogo — e ninguém percebe.

MAPEAMENTO MARC21
-----------------
    Leader/06-08 'a','m',' '  -> MaterialType.BOOK no BibLivre
    Leader/09    'a'          -> Unicode (o BibLivre lê/grava UTF-8)
    035 $a  (BF)<numacervo>   identificador de origem, para casar os
                              exemplares depois da importação
    020 $a  ISBN
    041 $a  idioma (por/eng/spa/fre/ger)
    080 $a  CDU
    082 $a  CDD
    090 $a  CDD  $b Cutter    número de chamada — o BibLivre COPIA o 090
                              $a/$b do bibliográfico para cada exemplar
                              criado (HoldingBO.createAutomaticHolding)
    100 $a  autor principal
    245 $a  título  $b subtítulo
    250 $a  edição
    260 $a  local  $b editora  $c ano
    300 $a  páginas
    500 $a  notas (OBS1 + OBS2)
    650 $a  assuntos (PALAVRAS1..5)
    700 $a  autores secundários

O BibLivre sobrescreve 001/005/008 com valores próprios ao salvar
(`BiblioRecordBO.save`), por isso o identificador de origem vai no 035.
"""

import csv
import io
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

LEADER = "00000nam a2200000 a 4500"

IDIOMAS_MARC = {
    "PORTUGUES": "por",
    "INGLES": "eng",
    "ESPANHOL": "spa",
    "FRANCES": "fre",
    "ALEMAO": "ger",
}

# Partículas de nome que não ajudam a identificar o autor: sem elas,
# "ALBERGARIA, LINO" e "Lino de Albergaria" caem no mesmo grupo.
PARTICULAS = {"de", "da", "do", "dos", "das", "e", "del", "von", "van", "la"}


def sem_acento(txt: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", txt)
        if not unicodedata.combining(c)
    )


def norm(txt: str) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados."""
    txt = sem_acento((txt or "").casefold())
    return re.sub(r"[^0-9a-z]+", " ", txt).strip()


def norm_autor(nome: str) -> str:
    """Conjunto ordenado de tokens, para casar 'SILVA, JOÃO' com 'João Silva'."""
    tokens = [t for t in norm(nome).split() if t not in PARTICULAS and len(t) > 1]
    return " ".join(sorted(tokens))


def norm_num(txt: str) -> str:
    """Normaliza volume/edição: '01', '1', '1ª' e '1a' viram a mesma coisa."""
    t = norm(txt).replace(" ", "")
    m = re.match(r"0*(\d+)", t)
    return m.group(1) if m else t


def chave_obra(linha: dict) -> str:
    return "|".join((
        norm(linha["titulo"]),
        norm(linha["subtitulo"]),
        norm_autor(linha["autor_principal"]),
        norm(linha["editora"]),
        linha["ano_edicao"].strip(),
        norm_num(linha["volume"]),
        norm_num(linha["edicao"]),
    ))


def representante(grupo, campo, validar=None):
    """
    Valor de consenso de um campo dentro do grupo de exemplares.

    Exemplares da mesma obra costumam ter preenchimento desigual (um tem
    ISBN, outro não; um tem CDD, outro não). Pegamos o valor mais frequente
    entre os não-vazios; em caso de empate, o mais longo — que costuma ser o
    mais completo.
    """
    valores = [g[campo].strip() for g in grupo if g[campo].strip()]
    if validar:
        preferidos = [v for v in valores if validar(v)]
        valores = preferidos or valores
    if not valores:
        return ""
    contagem = Counter(valores)
    return max(valores, key=lambda v: (contagem[v], len(v)))


def isbn_valido(v: str) -> bool:
    return len(re.sub(r"[^0-9Xx]", "", v)) in (10, 13)


def _sf(codigo, valor):
    return Subfield(code=codigo, value=valor)


def montar_registro(grupo) -> Record:
    r0 = grupo[0]
    rec = Record(force_utf8=True, leader=LEADER)

    titulo = representante(grupo, "titulo")
    subtitulo = representante(grupo, "subtitulo")
    autor = representante(grupo, "autor_principal")
    editora = representante(grupo, "editora")
    local = representante(grupo, "local_publicacao")
    ano = representante(grupo, "ano_edicao")
    edicao = representante(grupo, "edicao")
    isbn = representante(grupo, "isbn", validar=isbn_valido)
    cdd = representante(grupo, "cdd")
    cdu = representante(grupo, "cdu")
    cutter = representante(grupo, "cutter")
    paginas = representante(grupo, "paginas")
    notas = representante(grupo, "notas")

    # Identificador de origem: o menor NUMACERVO do grupo. É o que permite
    # casar cada exemplar com o registro certo depois da importação.
    origem = min(int(g["numacervo"]) for g in grupo)
    rec.add_field(Field(tag="035", indicators=[" ", " "],
                        subfields=[_sf("a", f"(BF){origem}")]))

    if isbn:
        rec.add_field(Field(tag="020", indicators=[" ", " "],
                            subfields=[_sf("a", re.sub(r"[^0-9Xx]", "", isbn))]))

    idioma = IDIOMAS_MARC.get(sem_acento(r0["idioma"].upper()))
    if idioma:
        rec.add_field(Field(tag="041", indicators=["0", " "],
                            subfields=[_sf("a", idioma)]))

    if cdu:
        rec.add_field(Field(tag="080", indicators=[" ", " "],
                            subfields=[_sf("a", cdu)]))
    if cdd:
        rec.add_field(Field(tag="082", indicators=["0", "4"],
                            subfields=[_sf("a", cdd)]))

    # 090 = número de chamada. O BibLivre copia $a, $b e $c daqui para cada
    # exemplar que cria, então é aqui que CDD + Cutter + volume precisam
    # estar (HoldingBO.createAutomaticHolding).
    volume = representante(grupo, "volume")
    if cdd or cutter or volume:
        sub = []
        if cdd:
            sub.append(_sf("a", cdd))
        if cutter:
            sub.append(_sf("b", cutter))
        if volume:
            sub.append(_sf("c", f"v. {volume}"))
        rec.add_field(Field(tag="090", indicators=[" ", " "], subfields=sub))

    if autor:
        # ind1=1: nome iniciado por sobrenome ("SILVA, JOÃO").
        ind1 = "1" if "," in autor else "0"
        rec.add_field(Field(tag="100", indicators=[ind1, " "],
                            subfields=[_sf("a", autor)]))

    # ind2 = nº de caracteres a ignorar na ordenação (artigo inicial).
    ind2 = "0"
    for artigo in ("A ", "O ", "As ", "Os ", "Um ", "Uma ", "The "):
        if titulo.upper().startswith(artigo.upper()):
            ind2 = str(len(artigo))
            break
    # Ordem dos subcampos no 245 é $a $n $b (o MARC21 define $n antes de $b).
    # Sem o $n, os 4 volumes de um didático viram 4 fichas de título idêntico
    # e indistinguível no catálogo.
    sub245 = []
    if volume:
        sub245.append(_sf("a", f"{titulo}."))
        sub245.append(_sf("n", f"v. {volume}" + (" :" if subtitulo else "")))
    else:
        sub245.append(_sf("a", f"{titulo} :" if subtitulo else titulo))
    if subtitulo:
        sub245.append(_sf("b", subtitulo))
    rec.add_field(Field(tag="245", indicators=["1" if autor else "0", ind2],
                        subfields=sub245))

    if edicao:
        rec.add_field(Field(tag="250", indicators=[" ", " "],
                            subfields=[_sf("a", edicao)]))

    sub260 = []
    if local:
        sub260.append(_sf("a", local))
    if editora:
        sub260.append(_sf("b", editora))
    if ano:
        sub260.append(_sf("c", ano))
    if sub260:
        rec.add_field(Field(tag="260", indicators=[" ", " "], subfields=sub260))

    if paginas and paginas not in ("0", ""):
        rec.add_field(Field(tag="300", indicators=[" ", " "],
                            subfields=[_sf("a", f"{paginas} p.")]))

    if notas:
        rec.add_field(Field(tag="500", indicators=[" ", " "],
                            subfields=[_sf("a", notas)]))

    assuntos = []
    for g in grupo:
        for a in g["assuntos"].split(";"):
            a = a.strip()
            if a and a not in assuntos:
                assuntos.append(a)
    for a in assuntos:
        rec.add_field(Field(tag="650", indicators=[" ", "4"],
                            subfields=[_sf("a", a)]))

    secundarios = []
    for g in grupo:
        for a in g["autores_secundarios"].split(";"):
            a = a.strip()
            if a and a not in secundarios:
                secundarios.append(a)
    for a in secundarios:
        ind1 = "1" if "," in a else "0"
        rec.add_field(Field(tag="700", indicators=[ind1, " "],
                            subfields=[_sf("a", a)]))

    return rec

def agrupar_por_obra(linhas: list[dict]) -> list[list[dict]]:
    """
    Agrupa linhas de exemplar em obras pela `chave_obra`, em ordem estável
    (pelo menor numacervo de cada grupo) — a mesma ordem em que os registros
    entram no MRC e no banco.
    """
    grupos: dict[str, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(chave_obra(linha), []).append(linha)
    return sorted(grupos.values(),
                  key=lambda g: min(int(x["numacervo"]) for x in g))


def ler_csv_consolidado(caminho) -> list[dict]:
    """Lê o CSV do `consolidar.py`, com todo campo ausente virando string vazia."""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(f)]


def escrever_mrc(registros, caminho) -> int:
    """Serializa os registros em ISO 2709 (UTF-8). Devolve quantos foram."""
    n = 0
    with open(caminho, "wb") as f:
        writer = MARCWriter(f)
        for rec in registros:
            writer.write(rec)
            n += 1
        writer.close()
    return n


def ler_mrc(caminho) -> list:
    with open(caminho, "rb") as f:
        return list(MARCReader(f, to_unicode=True, force_utf8=True))


def do_iso2709(iso: str):
    """Um registro a partir da coluna `iso2709` do banco, ou None se ilegível."""
    if not iso:
        return None
    try:
        return next(MARCReader(io.BytesIO(iso.encode("utf-8")),
                               to_unicode=True, force_utf8=True), None)
    except Exception:
        return None


def escrever_csv_exemplares(grupos: list[list[dict]], caminho) -> int:
    """
    O `exemplares.csv` que casa com o MRC: uma linha por exemplar físico,
    ligada à obra pelo `id_origem` (035 $a).
    """
    n = 0
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CABECALHO_EXEMPLARES)
        for grupo in grupos:
            origem = min(int(g["numacervo"]) for g in grupo)
            for i, g in enumerate(sorted(grupo, key=lambda x: int(x["numacervo"])),
                                  start=1):
                w.writerow([
                    f"(BF){origem}", g["numacervo"], i,
                    g["tombo"] if g["tombo"] not in ("0", "") else "",
                    g["exemplar"], g["volume"], g["localizacao"],
                    g["data_aquisicao"], g["titulo"],
                ])
                n += 1
    return n


CABECALHO_EXEMPLARES = [
    "id_origem", "numacervo", "ordem_exemplar", "tombo",
    "exemplar_origem", "volume", "localizacao", "data_aquisicao", "titulo",
]


# --- Campos de controle que o BibLivre reescreve ao salvar ---
# Reproduzem `BiblioRecordBO.save` / `MarcUtils`; conferidos byte a byte contra
# 25 registros que o próprio BibLivre importou pela tela.

# Template do 008 idêntico ao de MarcUtils.setCF008 (posições 07-40).
CF008_TAIL = "s||||     bl|||||||||||||||||por|u"


def set_cf001(rec, rec_id: int) -> None:
    """001 = id em 7 dígitos (DecimalFormat '0000000')."""
    rec.remove_fields("001")
    rec.add_ordered_field(Field(tag="001", data=f"{rec_id:07d}"))


def set_cf005(rec, agora: datetime) -> None:
    """005 = yyyyMMddHHmmss.SSS (SimpleDateFormat COMPACT_ISO)."""
    rec.remove_fields("005")
    stamp = agora.strftime("%Y%m%d%H%M%S.") + f"{agora.microsecond // 1000:03d}"
    rec.add_ordered_field(Field(tag="005", data=stamp))


def set_cf008(rec, agora: datetime) -> None:
    """008 só é criado se ainda não existir (mesma regra do MarcUtils)."""
    if rec.get("008") is not None:
        return
    rec.add_ordered_field(
        Field(tag="008", data=agora.strftime("%y%m%d") + CF008_TAIL))


def carimbar(rec, rec_id: int, agora: datetime | None = None) -> str:
    """
    Aplica 001/005/008 e devolve o ISO 2709 pronto para a coluna `iso2709`.
    É o último passo antes de qualquer INSERT em `biblio_records`.
    """
    agora = agora or datetime.now()
    set_cf001(rec, rec_id)
    set_cf005(rec, agora)
    set_cf008(rec, agora)
    return rec.as_marc().decode("utf-8")
