"""
Catalogação de livro novo por código de barras (ISBN).

É o caminho oposto ao da migração: em vez de trazer um acervo inteiro de um
sistema legado, entra um livro de cada vez, lido na estante com a câmera do
celular.

    lookup     ISBN -> metadados (Google Books, BrasilAPI/CBL, Open Library)
    fila       o lote (volátil) e a fila de revisão (persistida em disco)
    export     dedup por ISBN, geração de MRC/CSV e gravação no BibLivre
    ficha      OCR de ficha CIP (deteccao + isbn), para livro sem código de barras
    config     caminhos, estado do lote/fila, localização do Tesseract
    cert       certificado autoassinado (a câmera do navegador exige HTTPS)

O invariante do módulo é a **dedup por ISBN**: antes de gerar qualquer MARC, o
ISBN é confrontado com o acervo já catalogado (`biblio.biblivre.acervo`). Livro
que já existe não vira ficha nova — entra como exemplar a mais no `record_id`
que já está lá. Sem isso, reescanear a estante duplicaria o catálogo.

O outro invariante é a divisão de posturas: o lote é a bandeja do scanner
(volátil, nunca bloqueia quem está de pé na estante) e a fila é trabalho de
revisão (persistida, sobrevive a reinício). Ver docs/SPEC_UI.md.
"""

from . import cert, config, export, fila, lookup, rede

__all__ = ["cert", "config", "export", "fila", "lookup", "rede"]
