"""
Um `.bkp` do Biblioteca Fácil em miniatura, escrito do zero.

Existe por um motivo só: a migração passou a ser um botão na tela, e um botão
que grava dezenas de milhares de linhas no PostgreSQL da biblioteca não pode
ter como única verificação "rodou em campo uma vez". Backup real não entra no
repositório — tem CPF e endereço de gente dentro (ver o aviso do README) —,
então a alternativa é gerar um que tenha a mesma forma.

O que este módulo escreve é o formato documentado em docs/FORMATO_BKP.md e
docs/TABELAS.md, do lado do escritor:

  * o `.dat`, com o catálogo de campos no cabeçalho (nome, tipo, tamanho e
    offset de cada um) que `biblio.legado.tabela` lê de volta;
  * o container `.bkp`, com os nomes das tabelas e um bloco zlib por arquivo.

Os nomes de campo não são inventados aqui: os das tabelas de leitor saem das
próprias constantes de `biblio.biblivre.leitores`, para que o dia em que um
campo novo entrar lá a amostra continue tendo o que ele procura.
"""

import struct
import zlib
from datetime import date

from biblio.biblivre import leitores as _leitores

# Tipos do `.dat`, com o tamanho em bytes de cada um (ver `biblio.legado.tabela`).
ALPHA, DATE, SHORT, ENUM, LONG, DOUBLE = 1, 2, 4, 5, 6, 7
TAMANHO_FIXO = {DATE: 4, SHORT: 2, ENUM: 2, LONG: 4, DOUBLE: 8}

DESC_BASE = 514
DESC_STRIDE = 768


def dias(iso: str) -> int:
    """Data ISO → o inteiro de dias que o Biblioteca Fácil grava (0 = vazia)."""
    if not iso:
        return 0
    return (date.fromisoformat(iso) - date(1, 1, 1)).days + 1


def _pascal(texto: str) -> bytes:
    bruto = texto.encode("cp1252", errors="replace")[:255]
    return bytes([len(bruto)]) + bruto


def _campos(declaracao):
    """[(nome, tipo, largura)] → campos com offset, como o cabeçalho os traz."""
    campos, offset = [], 1  # o byte 0 do registro é a flag do primeiro campo
    for nome, tipo, largura in declaracao:
        tamanho = (largura + 1) if tipo == ALPHA else TAMANHO_FIXO[tipo]
        campos.append({"nome": nome, "tipo": tipo, "largura": largura,
                       "tamanho": tamanho, "offset": offset})
        offset += tamanho + 1
    return campos, offset


def escrever_dat(descricao: str, declaracao, registros) -> bytes:
    """Uma tabela do Biblioteca Fácil, pronta para `tabela.Tabela` reler."""
    campos, record_size = _campos(declaracao)
    data_start = DESC_BASE - 1 + len(campos) * DESC_STRIDE
    buf = bytearray(data_start + len(registros) * record_size)

    struct.pack_into("<i", buf, 0x21, len(registros))
    struct.pack_into("<H", buf, 0x2D, record_size)
    struct.pack_into("<H", buf, 0x2F, len(campos))
    nome = _pascal(descricao)
    buf[0x47:0x47 + len(nome)] = nome

    for i, campo in enumerate(campos):
        base = DESC_BASE + i * DESC_STRIDE
        rotulo = _pascal(campo["nome"])
        buf[base:base + len(rotulo)] = rotulo
        buf[base + 162] = campo["tipo"]
        buf[base + 164] = campo["largura"]
        buf[base + 167] = campo["tamanho"]
        struct.pack_into("<H", buf, base + 170, campo["offset"])

    for i, linha in enumerate(registros):
        base = data_start + i * record_size
        for campo in campos:
            _gravar_valor(buf, base + campo["offset"], campo,
                          linha.get(campo["nome"], "" if campo["tipo"] == ALPHA else 0))
    return bytes(buf)


def _gravar_valor(buf, pos, campo, valor) -> None:
    tipo = campo["tipo"]
    if tipo == ALPHA:
        bruto = str(valor).encode("cp1252", errors="replace")[:campo["largura"]]
        buf[pos:pos + len(bruto)] = bruto
        buf[pos + len(bruto)] = 0
    elif tipo == DOUBLE:
        struct.pack_into("<d", buf, pos, float(valor))
    elif tipo in (SHORT, ENUM):
        struct.pack_into("<h", buf, pos, int(valor))
    else:
        struct.pack_into("<i", buf, pos, int(valor))


def escrever_bkp(tabelas: dict[str, bytes]) -> bytes:
    """
    Empacota `{"T09_ACER.dat": bytes}` no container `.bkp`.

    O leitor localiza os streams zlib pela assinatura, varrendo até 200 bytes
    depois do nome do arquivo — daí os 8 bytes de metadado zerado no lugar do
    bloco que o Biblioteca Fácil escreve ali.
    """
    codigos = sorted({nome.rsplit(".", 1)[0] for nome in tabelas})

    saida = bytearray()
    saida += b"BF-AMOSTRA-BKP01"          # 16 bytes de assinatura
    saida += struct.pack("<q", 0)          # int64 de uso não confirmado
    saida += struct.pack("<d", 0.0)        # TDateTime do backup
    saida += _pascal("Backup do dia 01/01/2026 00:00:00")
    saida += struct.pack("<i", len(codigos))
    for codigo in codigos:
        saida += _pascal(codigo)

    for nome, conteudo in tabelas.items():
        saida += _pascal(nome)
        saida += bytes(8)                  # metadado que o leitor pula
        saida += zlib.compress(conteudo)
    return bytes(saida)


# ------------------------------------------------------- a amostra em si

ACERVO = [
    ("T09_NUMACERVO", LONG, 0), ("T09_TITULO", ALPHA, 60),
    ("T09_SUBTITULO", ALPHA, 60), ("T09_NUMEDITORA", LONG, 0),
    ("T09_NUMIDIOMA", LONG, 0), ("T09_NUMTIPOITEM", LONG, 0),
    ("T09_NUMCLASSIFIC", LONG, 0), ("T09_ANOEDICAO2", ALPHA, 10),
    ("T09_EDICAO", ALPHA, 10), ("T09_VOLUME", ALPHA, 10),
    ("T09_EXEMPLAR", ALPHA, 10), ("T09_TOMBO", LONG, 0),
    ("T09_ISBN", ALPHA, 20), ("T09_PAGINAS", LONG, 0),
    ("T09_CDD", ALPHA, 20), ("T09_CDU", ALPHA, 20), ("T09_CUTTER", ALPHA, 20),
    ("T09_PALAVRAS1", ALPHA, 30), ("T09_PALAVRAS2", ALPHA, 30),
    ("T09_PALAVRAS3", ALPHA, 30), ("T09_PALAVRAS4", ALPHA, 30),
    ("T09_PALAVRAS5", ALPHA, 30), ("T09_LOCAL", ALPHA, 30),
    ("T09_OBS1", ALPHA, 60), ("T09_OBS2", ALPHA, 60),
    ("T09_AQUISICAO", DATE, 0), ("T09_EXCLUSAO", DATE, 0),
]

# T04_LEIT: o que a montagem dos leitores procura, tirado dela mesma.
LEITOR = (
    [("T04_NUMLEITOR", LONG, 0), ("T04_LEITOR", ALPHA, 60),
     ("T04_EXCLUSAO", DATE, 0), ("T04_DESATIVADO", ENUM, 0),
     ("T04_DATACADASTRO", DATE, 0), ("T04_ENDERECO", ALPHA, 60),
     ("T04_SEXO2", ALPHA, 2), ("T04_DATANASC", DATE, 0),
     ("T04_OBS1", ALPHA, 60), ("T04_OBS2", ALPHA, 60),
     ("T04_TURMA", ALPHA, 20), ("T04_TURNO2", ALPHA, 20),
     ("T04_FOTO", ALPHA, 60)]
    + [(origem, ALPHA, 40) for origem, _ in _leitores.DIRETO]
    + [(c[4], ALPHA, c[2]) for c in _leitores.CAMPOS_NOVOS]
)

MOVM = [("T13_NUMEMPRESTIMO", LONG, 0), ("T13_NUMLEITOR", LONG, 0),
        ("T13_DATA", DATE, 0)]

MOVI = [("T11_NUMMOVIMENTO", LONG, 0), ("T11_NUMEMPRESTIMO", LONG, 0),
        ("T11_NUMACERVO", LONG, 0), ("T11_PREVISAO", DATE, 0),
        ("T11_DEVOLUCAO", DATE, 0), ("T11_EXCLUSAO", DATE, 0),
        ("T11_MULTA", DOUBLE, 0), ("T11_PGTOMULTA", DATE, 0),
        ("T11_MultaCancelada", ENUM, 0)]

RESE = [("T15_NUMRESERVA", LONG, 0), ("T15_NUMLEITOR", LONG, 0),
        ("T15_NUMACERVO", LONG, 0), ("T15_DATA", DATE, 0),
        ("T15_VALIDADE1", DATE, 0), ("T15_VALIDADE2", DATE, 0),
        ("T15_EXCLUSAO", DATE, 0), ("T15_UTILIZOU", ENUM, 0)]

APOIO = {
    "T05_AUTO.dat": ("Cadastro de Autores",
                     [("T05_NUMAUTOR", LONG, 0), ("T05_AUTOR", ALPHA, 60),
                      ("T05_EXCLUSAO", DATE, 0)],
                     [{"T05_NUMAUTOR": 1, "T05_AUTOR": "ASSIS, MACHADO DE"},
                      {"T05_NUMAUTOR": 2, "T05_AUTOR": "CUNHA, EUCLIDES DA"}]),
    "T06_EDIT.dat": ("Cadastro de Editoras",
                     [("T06_NUMEDITORA", LONG, 0), ("T06_EDITORA", ALPHA, 40),
                      ("T06_LOCALIZACAO", ALPHA, 40), ("T06_EXCLUSAO", DATE, 0)],
                     [{"T06_NUMEDITORA": 1, "T06_EDITORA": "Globo",
                       "T06_LOCALIZACAO": "Rio de Janeiro"}]),
    "T07_CLAS.dat": ("Cadastro de Classificacao",
                     [("T07_NUMCLASSIFIC", LONG, 0),
                      ("T07_CLASSIFICACAO", ALPHA, 40),
                      ("T07_EXCLUSAO", DATE, 0)],
                     [{"T07_NUMCLASSIFIC": 1, "T07_CLASSIFICACAO": "Literatura"}]),
    "T08_TIPO.dat": ("Cadastro de Tipos de Item",
                     [("T08_NUMTIPOITEM", LONG, 0), ("T08_TIPOITEM", ALPHA, 40),
                      ("T08_EXCLUSAO", DATE, 0)],
                     [{"T08_NUMTIPOITEM": 1, "T08_TIPOITEM": "Livro"}]),
    "T14_IDIO.dat": ("Cadastro de Idiomas",
                     [("T14_NUMIDIOMA", LONG, 0), ("T14_IDIOMA", ALPHA, 40),
                      ("T14_EXCLUSAO", DATE, 0)],
                     [{"T14_NUMIDIOMA": 1, "T14_IDIOMA": "PORTUGUES"}]),
}


def _acervo(num, titulo, **extra) -> dict:
    linha = {
        "T09_NUMACERVO": num, "T09_TITULO": titulo, "T09_SUBTITULO": "",
        "T09_NUMEDITORA": 1, "T09_NUMIDIOMA": 1, "T09_NUMTIPOITEM": 1,
        "T09_NUMCLASSIFIC": 1, "T09_ANOEDICAO2": "2022", "T09_EDICAO": "1",
        "T09_VOLUME": "", "T09_EXEMPLAR": "1", "T09_TOMBO": num,
        "T09_ISBN": "9786559870530", "T09_PAGINAS": 480, "T09_CDD": "869.3",
        "T09_CDU": "", "T09_CUTTER": "A848d", "T09_PALAVRAS1": "ROMANCE",
        "T09_LOCAL": "Estante A", "T09_OBS1": "", "T09_OBS2": "",
        "T09_AQUISICAO": dias("2026-01-15"), "T09_EXCLUSAO": 0,
    }
    linha.update(extra)
    return linha


def _leitor(num, nome, **extra) -> dict:
    linha = {
        "T04_NUMLEITOR": num, "T04_LEITOR": nome, "T04_EXCLUSAO": 0,
        "T04_DESATIVADO": 0, "T04_DATACADASTRO": dias("2019-03-10"),
        "T04_ENDERECO": "RUA DAS ACACIAS nº 120", "T04_SEXO2": "F",
        "T04_DATANASC": dias("1990-05-02"), "T04_CIDADE": "Feira de Santana",
        "T04_ESTADO": "BA", "T04_TELEFONE1": "75999990000",
        "T04_BAIRRO": "Centro", "T04_NOMEMAE": "MARIA DA SILVA",
    }
    linha.update(extra)
    return linha


def amostra() -> bytes:
    """
    Um backup pequeno com um caso de cada coisa que a migração decide.

    Quatro registros de acervo para três obras (dois exemplares de *Dom
    Casmurro* e dois volumes da mesma coleção, que **não** podem ser fundidos),
    um registro excluído na origem, dois leitores (um deles desativado), dois
    empréstimos — um em aberto, um devolvido com multa — e uma reserva.
    """
    acervo = [
        _acervo(100, "Dom Casmurro"),
        _acervo(101, "Dom Casmurro", T09_EXEMPLAR="2", T09_TOMBO=101),
        _acervo(102, "Palavra Aberta", T09_VOLUME="1", T09_ISBN="",
                T09_NUMEDITORA=1),
        _acervo(103, "Palavra Aberta", T09_VOLUME="2", T09_ISBN=""),
        _acervo(104, "Livro Apagado", T09_EXCLUSAO=dias("2020-06-01")),
    ]
    vinculos = [
        {"T10_SEQUENCIA": 1, "T10_NUMAUTOR": 1, "T10_NUMACERVO": 100},
        {"T10_SEQUENCIA": 2, "T10_NUMAUTOR": 1, "T10_NUMACERVO": 101},
        {"T10_SEQUENCIA": 3, "T10_NUMAUTOR": 2, "T10_NUMACERVO": 102},
        {"T10_SEQUENCIA": 4, "T10_NUMAUTOR": 2, "T10_NUMACERVO": 103},
    ]
    leitores_amostra = [
        _leitor(1, "ANA SOUZA"),
        _leitor(2, "JOAO PEREIRA", T04_DESATIVADO=1, T04_SEXO2="M",
                T04_DATANASC=dias("1850-01-01")),  # nascimento impossível
    ]
    movm = [
        {"T13_NUMEMPRESTIMO": 1, "T13_NUMLEITOR": 1,
         "T13_DATA": dias("2026-02-01")},
        {"T13_NUMEMPRESTIMO": 2, "T13_NUMLEITOR": 2,
         "T13_DATA": dias("2026-03-05")},
    ]
    movi = [
        {"T11_NUMMOVIMENTO": 1, "T11_NUMEMPRESTIMO": 1, "T11_NUMACERVO": 100,
         "T11_PREVISAO": dias("2026-02-16"), "T11_DEVOLUCAO": 0,
         "T11_EXCLUSAO": 0, "T11_MULTA": 0.0, "T11_PGTOMULTA": 0,
         "T11_MultaCancelada": 0},
        {"T11_NUMMOVIMENTO": 2, "T11_NUMEMPRESTIMO": 2, "T11_NUMACERVO": 102,
         "T11_PREVISAO": dias("2026-03-20"),
         "T11_DEVOLUCAO": dias("2026-03-25"), "T11_EXCLUSAO": 0,
         "T11_MULTA": 2.5, "T11_PGTOMULTA": dias("2026-03-25"),
         "T11_MultaCancelada": 0},
    ]
    rese = [
        {"T15_NUMRESERVA": 1, "T15_NUMLEITOR": 1, "T15_NUMACERVO": 103,
         "T15_DATA": dias("2026-04-01"), "T15_VALIDADE1": dias("2026-04-30"),
         "T15_VALIDADE2": 0, "T15_EXCLUSAO": 0, "T15_UTILIZOU": 0},
    ]

    tabelas = {
        "T09_ACER.dat": escrever_dat("Cadastro do Acervo", ACERVO, acervo),
        "T10_AUAC.dat": escrever_dat(
            "Cadastro de Autores nas Obras",
            [("T10_SEQUENCIA", LONG, 0), ("T10_NUMAUTOR", LONG, 0),
             ("T10_NUMACERVO", LONG, 0)], vinculos),
        "T04_LEIT.dat": escrever_dat("Cadastro de Leitores", LEITOR,
                                     leitores_amostra),
        "T13_MOVM.dat": escrever_dat("Cadastro de Emprestimos", MOVM, movm),
        "T11_MOVI.dat": escrever_dat("Movimentacao de Emprestimos", MOVI, movi),
        "T15_RESE.dat": escrever_dat("Cadastro de Reservas", RESE, rese),
    }
    for nome, (descricao, declaracao, linhas) in APOIO.items():
        tabelas[nome] = escrever_dat(descricao, declaracao, linhas)

    return escrever_bkp(tabelas)
