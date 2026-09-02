"""
Leitor genérico das tabelas do Biblioteca Fácil (`biblio.legado.tabela`).

POR QUE ISSO SUBSTITUI A CAÇA MANUAL DE OFFSETS
------------------------------------------------
As primeiras versões dos scripts de extração descobriam os offsets de campo
"na mão": procuravam um texto conhecido (ex.: o título "Palavra Aberta") e
mediam a distância até os outros campos. Isso funciona, mas é lento, erra
fácil e não alcança campos numéricos (que não aparecem como texto legível).

Descobrimos que cada arquivo `.dat` traz, ANTES dos dados, um catálogo
completo do próprio layout: nome, tipo, tamanho e offset de cada campo.
Ou seja, não é preciso adivinhar nada — o arquivo se descreve.

LAYOUT DO CABEÇALHO
-------------------
Atenção: NÃO é o formato Paradox padrão (apesar do software ser da era
Delphi). É um formato próprio do Biblioteca Fácil. Offsets do cabeçalho:

    0x00  2 bytes   'yy' (assinatura fixa)
    0x09  8 bytes   double  - TDateTime do Delphi
    0x11  8 bytes   FILETIME do Windows
    0x1d  4x int32  - contadores de registro (o 2º é o total: numRecords)
    0x2d  uint16    - recordSize (tamanho do registro em bytes)
    0x2f  uint16    - numFields (quantidade de campos)
    0x47  string    - Pascal string com a descrição da tabela
                      (ex.: "Cadastro do Acervo")

Depois vem a TABELA DE DESCRITORES: `numFields` blocos de 768 bytes cada,
começando no offset 514. Dentro de cada bloco de 768 bytes:

    +0    Pascal string  - nome do campo (ex.: "T09_TITULO")
    +162  1 byte         - tipo (ver TIPOS abaixo)
    +164  1 byte         - largura de exibição na tela
    +167  1 byte         - tamanho do campo em bytes
    +170  uint16         - OFFSET DO CAMPO dentro do registro
    +766  1 byte         - índice do campo + 2

Os dados começam imediatamente depois dos descritores:
    data_start = 513 + numFields * 768

VALIDAÇÃO DO LAYOUT (vale a pena repetir ao portar para outra tabela)
---------------------------------------------------------------------
Cada campo ocupa `tamanho + 1` bytes: há 1 byte de flag ANTES do dado
(provavelmente indicador de nulo). Isso fecha a conta exatamente:

    offset_do_primeiro_campo + soma(tamanho + 1 de cada campo) == recordSize

No Acervo: 25 + 807 == 832 ✅. Se essa igualdade fechar, o layout está
certo — é o melhor teste de sanidade disponível.
"""

import csv
import struct
from pathlib import Path

HDR_RECSIZE = 0x2D
HDR_NUMFIELDS = 0x2F
HDR_NUMRECORDS = 0x21
HDR_DESC_NAME = 0x47

DESC_BASE = 514
DESC_STRIDE = 768
DESC_TYPE = 162
DESC_WIDTH = 164
DESC_SIZE = 167
DESC_OFFSET = 170

# Tipos observados nas tabelas deste backup.
TIPO_ALPHA = 1  # texto CP1252, terminado em \x00
TIPO_DATE = 2  # int32, dias desde 01/01/0001 (0 = vazio)
TIPO_SHORT = 4  # int16
TIPO_ENUM = 5  # int16 usado como enum/booleano (ex.: T04_SEXO, T01_NIVEL)
TIPO_LONG = 6  # int32
TIPO_DOUBLE = 7  # float64 (ex.: T11_MULTA, T03_MultaDia)

TIPOS = {
    TIPO_ALPHA: "alpha",
    TIPO_DATE: "date",
    TIPO_SHORT: "short",
    TIPO_ENUM: "enum",
    TIPO_LONG: "long",
    TIPO_DOUBLE: "double",
}


class Campo:
    __slots__ = ("nome", "tipo", "largura", "tamanho", "offset")

    def __init__(self, nome, tipo, largura, tamanho, offset):
        self.nome = nome
        self.tipo = tipo
        self.largura = largura
        self.tamanho = tamanho
        self.offset = offset

    @property
    def tipo_nome(self):
        return TIPOS.get(self.tipo, f"desconhecido({self.tipo})")

    def __repr__(self):
        return (
            f"Campo({self.nome!r}, {self.tipo_nome}, "
            f"offset={self.offset}, tamanho={self.tamanho})"
        )


def _pascal(buf, pos=0):
    n = buf[pos]
    return buf[pos + 1: pos + 1 + n].decode("cp1252", errors="replace")


class Tabela:
    """Uma tabela do Biblioteca Fácil, lida a partir dos bytes de um `.dat`."""

    def __init__(self, dados: bytes, nome: str = "?"):
        self.nome = nome
        self._dados = dados
        self.record_size = struct.unpack_from("<H", dados, HDR_RECSIZE)[0]
        self.num_fields = struct.unpack_from("<H", dados, HDR_NUMFIELDS)[0]
        self.num_records_header = struct.unpack_from("<i", dados, HDR_NUMRECORDS)[0]
        self.descricao = _pascal(dados, HDR_DESC_NAME)

        self.campos = []
        for i in range(self.num_fields):
            blk = dados[DESC_BASE + i * DESC_STRIDE:
                        DESC_BASE + (i + 1) * DESC_STRIDE]
            self.campos.append(Campo(
                nome=_pascal(blk),
                tipo=blk[DESC_TYPE],
                largura=blk[DESC_WIDTH],
                tamanho=blk[DESC_SIZE],
                offset=struct.unpack_from("<H", blk, DESC_OFFSET)[0],
            ))

        self.data_start = DESC_BASE - 1 + self.num_fields * DESC_STRIDE
        self.num_records = max(
            0, (len(dados) - self.data_start) // self.record_size
        )

    def validar(self) -> bool:
        """
        Sanidade do layout: os campos vêm em ordem crescente de offset, cada um
        ocupa `tamanho + 1` bytes (1 byte de flag antes do dado) e o último
        termina dentro do registro.

        Algumas tabelas têm alguns bytes de sobra no fim do registro
        (alinhamento), por isso a comparação é `<=` e não `==`.
        """
        if not self.campos:
            return False
        pos = self.campos[0].offset
        for c in self.campos:
            if c.offset < pos:
                return False
            pos = c.offset + c.tamanho + 1
        return pos - 1 <= self.record_size

    def por_nome(self, sufixo: str) -> Campo:
        """Busca um campo pelo sufixo do nome, ignorando o prefixo TNN_."""
        alvo = sufixo.upper()
        for c in self.campos:
            if c.nome.upper().endswith(alvo):
                return c
        raise KeyError(f"campo {sufixo!r} não existe em {self.nome}")

    def _valor(self, rec: bytes, campo: Campo):
        raw = rec[campo.offset: campo.offset + campo.tamanho]
        if campo.tipo == TIPO_ALPHA:
            return raw.split(b"\x00")[0].decode("cp1252", errors="replace").strip()
        if campo.tipo in (TIPO_SHORT, TIPO_ENUM):
            return struct.unpack("<h", raw[:2])[0]
        if campo.tipo == TIPO_DOUBLE:
            return struct.unpack("<d", raw[:8])[0]
        # date e long são ambos int32; a data fica como número de dias cru,
        # convertida sob demanda por data_para_iso().
        return struct.unpack("<i", raw[:4])[0]

    def registros(self, pular_vazios=True):
        """Itera os registros como dicts {nome_do_campo: valor}."""
        for i in range(self.num_records):
            off = self.data_start + i * self.record_size
            rec = self._dados[off: off + self.record_size]
            if len(rec) < self.record_size:
                break
            linha = {c.nome: self._valor(rec, c) for c in self.campos}
            if pular_vazios and not any(
                v not in ("", 0) for v in linha.values()
            ):
                continue
            yield linha

    def resumo(self) -> str:
        linhas = [
            f"{self.nome}  ({self.descricao})",
            f"  record_size={self.record_size}  campos={self.num_fields}  "
            f"registros={self.num_records}  layout_valido={self.validar()}",
        ]
        for c in self.campos:
            linhas.append(
                f"    {c.nome:20s} {c.tipo_nome:6s} offset={c.offset:>4} "
                f"tamanho={c.tamanho:>3}"
            )
        return "\n".join(linhas)


def data_para_iso(dias: int) -> str:
    """Converte o inteiro de data do Biblioteca Fácil para 'AAAA-MM-DD'."""
    if not dias:
        return ""
    from datetime import date, timedelta
    try:
        return (date(1, 1, 1) + timedelta(days=dias - 1)).isoformat()
    except (OverflowError, ValueError):
        return ""


def carregar(pasta, nome_arquivo: str) -> Tabela:
    """Carrega uma tabela a partir de um `.dat` extraído do `.bkp`."""
    caminho = Path(pasta) / nome_arquivo
    return Tabela(caminho.read_bytes(), nome=nome_arquivo)


def carregar_todas(pasta) -> dict:
    pasta = Path(pasta)
    return {
        p.name: Tabela(p.read_bytes(), nome=p.name)
        for p in sorted(pasta.glob("*.dat"))
    }


def exportar_csv(tab: "Tabela", saida, datas_iso: bool = False) -> int:
    """
    Despeja uma tabela num CSV, uma coluna por campo declarado no cabeçalho.

    `datas_iso` converte os campos do tipo date (int32 de dias) para
    AAAA-MM-DD; sem isso o número cru é preservado.
    """
    saida = Path(saida)
    campos_data = {c.nome for c in tab.campos if c.tipo == TIPO_DATE}
    colunas = [c.nome for c in tab.campos]

    n = 0
    with open(saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        w.writeheader()
        for linha in tab.registros():
            if datas_iso:
                for nome in campos_data:
                    linha[nome] = data_para_iso(linha[nome])
            w.writerow(linha)
            n += 1
    return n
