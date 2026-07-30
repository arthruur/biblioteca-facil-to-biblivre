"""
Extrai os registros da tabela T09_ACER (Acervo / livros) para um CSV.

COMO OS OFFSETS ABAIXO FORAM DESCOBERTOS
------------------------------------------
As tabelas Paradox têm registros de TAMANHO FIXO. Descobrimos o tamanho do
registro (832 bytes para o Acervo) procurando por trechos de texto legível
repetidos (ex.: "Português", "371.32", "Palavra Aberta") e medindo a
distância constante entre ocorrências equivalentes em registros
consecutivos.

Depois, usando um registro cujo conteúdo já conhecíamos (por ex. o título
"Palavra Aberta"), medimos o deslocamento (offset) de cada campo dentro do
registro de 832 bytes.

Confirmados até agora:
  offset   0 : campo que aparenta ser Coleção/Série (NÃO é o idioma -
               precisa confirmar contra a lista de valores possíveis)
  offset 369 : CDD  (classificação decimal Dewey)
  offset 505 : Cutter
  offset 517 : Título  (até ~238 bytes)
  offset 755 : Ano de edição

AINDA NÃO MAPEADOS (mas com nome de campo já identificado no cabeçalho):
  ISBN, TOMBO (nº de patrimônio/exemplar), PAGINAS, CDU, NUMIDIOMA,
  SUBTITULO, PALAVRAS3/4/5, NAOEMPRESTAR, FOTO, RESERVADO
  -> provavelmente há também campos numéricos (não-texto) apontando
     para o autor e a editora (chave estrangeira para T05_AUTO e
     T06_EDIT), que não aparecem como texto legível na varredura.

Para mapear os campos que faltam, repita a técnica: abra o pickle,
procure por `re.finditer` de texto legível certo (ex.: um ISBN que você
sabe que existe) e meça a distância dele até o título do mesmo registro.
"""

import pickle
import csv
import sys
from pathlib import Path

REC_SIZE = 832
ANCHOR_OFFSET = 26719  # posição de início de UM registro real e confirmado

FIELDS = {
    "coluna_inicial_offset0": (0, 40),
    "cdd": (369, 400),
    "cutter": (505, 517),
    "titulo": (517, 755),
    "ano_edicao": (755, 769),
}


def decode_field(raw: bytes) -> str:
    return raw.split(b"\x00")[0].decode("cp1252", errors="replace").strip()


def main():
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("saida")
    pkl_path = pasta / "_tabelas.pkl"
    with open(pkl_path, "rb") as f:
        tabelas = pickle.load(f)

    acervo = tabelas["T09_ACER.dat"]

    n_registros = (len(acervo) - ANCHOR_OFFSET) // REC_SIZE
    print(f"Total estimado de registros no Acervo: {n_registros}")

    out_path = Path("acervo.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(list(FIELDS.keys()))

        for i in range(n_registros):
            off = ANCHOR_OFFSET + i * REC_SIZE
            rec = acervo[off: off + REC_SIZE]
            if len(rec) < REC_SIZE:
                break
            row = [decode_field(rec[start:end]) for start, end in FIELDS.values()]
            # pula registros totalmente vazios (provavelmente deletados/não usados)
            if any(row):
                writer.writerow(row)

    print(f"CSV gerado em: {out_path.resolve()}")


if __name__ == "__main__":
    main()
