"""
Leitura do backup do Biblioteca Fácil (`.bkp`) — o sistema legado de onde o
acervo veio.

O `.bkp` é um container proprietário com 16 tabelas em blocos zlib; cada `.dat`
traz, antes dos dados, um catálogo do próprio layout (nome, tipo, tamanho e
offset de cada campo), o que dispensa caçar offset a mão. Ver
docs/FORMATO_BKP.md e docs/TABELAS.md.

    from biblio.legado import bkp, consolidar, tabela

    bkp.extrair_para_pasta("backup.bkp", "saida/")
    acervo = tabela.carregar("saida/", "T09_ACER.dat")
    df = consolidar.consolidar("saida/")

`consolidar` é carregado sob demanda porque é o único módulo daqui que precisa
de pandas — e quem importa este pacote com mais frequência é o servidor web
(por tabelas de arquivo `.dat`, via `biblio.biblivre.leitores`), que nunca
consolida backup nenhum. Sem isto, subir a API custaria o import do pandas.
"""

from .bkp import extrair_para_pasta, parse_bkp
from .tabela import (
    Campo,
    Tabela,
    carregar,
    carregar_todas,
    data_para_iso,
    exportar_csv,
)

__all__ = [
    "Campo", "Tabela", "carregar", "carregar_todas", "data_para_iso",
    "exportar_csv", "parse_bkp", "extrair_para_pasta", "consolidar",
]


def __getattr__(nome):
    if nome == "consolidar":
        from . import consolidar as modulo

        return modulo
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
