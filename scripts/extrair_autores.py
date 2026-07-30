"""
Extrai os registros da tabela T05_AUTO (Autores) para um CSV.

Registro de tamanho fixo: 80 bytes.
O nome do autor começa no offset 47 dentro de cada registro (medido a
partir de um registro confirmado: "Joel Rufino dos Santos").

O campo NUMAUTOR (ID numérico) provavelmente fica nos primeiros bytes do
registro (antes do offset 47), armazenado em binário (não como texto) -
ainda não identificamos o tipo exato (inteiro de 2 ou 4 bytes + possível
byte de flag). Se precisar do ID para relacionar com o Acervo, vale a pena
investigar esses bytes iniciais com mais calma.
"""

import pickle
import csv
import sys
from pathlib import Path

REC_SIZE = 80
NAME_OFFSET = 47
NAME_LEN = 33  # ate o proximo campo (EXCLUSAO), ajustar se cortar nomes longos

ANCHOR_NAME_START = 2847  # "Joel Rufino dos Santos" - registro confirmado


def decode_field(raw: bytes) -> str:
    return raw.split(b"\x00")[0].decode("cp1252", errors="replace").strip()


def main():
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("saida")
    pkl_path = pasta / "_tabelas.pkl"
    with open(pkl_path, "rb") as f:
        tabelas = pickle.load(f)

    autores = tabelas["T05_AUTO.dat"]
    record_start_anchor = ANCHOR_NAME_START - NAME_OFFSET

    n_registros = (len(autores) - record_start_anchor) // REC_SIZE
    print(f"Total estimado de registros em Autores: {n_registros}")

    out_path = Path("autores.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["nome"])

        for i in range(n_registros):
            off = record_start_anchor + i * REC_SIZE
            rec = autores[off: off + REC_SIZE]
            if len(rec) < REC_SIZE:
                break
            nome = decode_field(rec[NAME_OFFSET:NAME_OFFSET + NAME_LEN])
            if nome:
                writer.writerow([nome])

    print(f"CSV gerado em: {out_path.resolve()}")


if __name__ == "__main__":
    main()
