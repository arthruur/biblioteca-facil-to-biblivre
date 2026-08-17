"""
Extrai o conteúdo de um arquivo .bkp do Biblioteca Fácil.

O QUE DESCOBRIMOS SOBRE O FORMATO .bkp
----------------------------------------
O .bkp é um container proprietário criado pelo Biblioteca Fácil que empacota
16 tabelas (cada uma com um arquivo .dat = dados e .idx = índice),
compactadas em blocos zlib de até 64KB cada (tabelas grandes viram vários
blocos em sequência).

Estrutura do arquivo:
  - 16 bytes: assinatura/magic fixo do aplicativo (não muda entre backups)
  - 8 bytes:  inteiro (uso não confirmado)
  - 8 bytes:  double (timestamp Delphi TDateTime do backup)
  - string Pascal (1 byte tamanho + texto): "Backup do dia DD/MM/AAAA HH:MM:SS"
  - int32: quantidade de tabelas (16)
  - lista de strings Pascal: nomes das tabelas (T01_USUA, T02_ACES, ...)
  - depois, uma sequência de entradas, uma por arquivo de tabela:
      string Pascal: nome do arquivo (ex: "T09_ACER.dat")
      bloco de metadados de tamanho variável (inclui tamanho total
        descomprimido, timestamp, etc. - não precisamos decodificar
        campo a campo, ver abaixo)
      um ou mais blocos: [int32 tamanho comprimido][dados zlib]
        (tabelas grandes são divididas em blocos de 64KB descomprimidos)

Em vez de decodificar os metadados campo a campo (o que exigiria
engenharia reversa exata de cada campo), este script localiza os streams
zlib diretamente pela assinatura (0x78 seguido de 0x01/0x5e/0x9c/0xda) e
usa zlib.decompressobj() para descobrir automaticamente onde cada stream
termina. Isso é robusto e não depende de acertar o tamanho exato dos
campos de metadados.

Resultado: recupera os 32 arquivos de tabela originais, byte a byte,
prontos para serem lidos por scripts/bf_tabela.py (o formato do .dat NÃO é
Paradox, apesar da aparência - ver docs/TABELAS.md).
"""

import struct
import zlib
import re
import pickle
import sys
from pathlib import Path


def parse_bkp(path: str) -> dict[str, bytes]:
    with open(path, "rb") as f:
        data = f.read()
    n = len(data)

    pos = 16 + 8 + 8  # pula magic + int64 + double
    strlen = data[pos]
    pos += 1 + strlen  # pula a string "Backup do dia ..."

    count = struct.unpack_from("<i", data, pos)[0]
    pos += 4

    table_codes = []
    for _ in range(count):
        l = data[pos]
        table_codes.append(data[pos + 1: pos + 1 + l].decode("latin1"))
        pos += 1 + l

    name_pattern = re.compile(
        r"^(" + "|".join(re.escape(t) for t in table_codes) + r")\.(dat|idx)$"
    )

    def find_zlib_and_decompress(start, limit=200):
        for cand in range(start, min(start + limit, n - 1)):
            if data[cand] == 0x78 and data[cand + 1] in (0x01, 0x5E, 0x9C, 0xDA):
                d = zlib.decompressobj()
                try:
                    out = d.decompress(data[cand:])
                    out += d.flush()
                except Exception:
                    continue
                consumed = n - cand - len(d.unused_data)
                return cand, out, consumed
        return None

    extracted: dict[str, bytes] = {}
    current = None

    while pos < n - 5:
        l = data[pos]
        matched_name = None
        if 0 < l <= 40 and pos + 1 + l < n:
            candidate = data[pos + 1: pos + 1 + l].decode("latin1", errors="ignore")
            if name_pattern.match(candidate):
                matched_name = candidate

        if matched_name:
            current = matched_name
            extracted[current] = b""
            pos = pos + 1 + l

        r = find_zlib_and_decompress(pos)
        if r is None:
            break
        zpos, out, consumed = r
        if current is None:
            break
        extracted[current] += out
        pos = zpos + consumed

    return extracted


def main():
    if len(sys.argv) < 2:
        print("Uso: python extrair_bkp.py caminho/do/arquivo.bkp [pasta_saida]")
        sys.exit(1)

    bkp_path = sys.argv[1]
    outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("tabelas_extraidas")
    outdir.mkdir(exist_ok=True)

    tabelas = parse_bkp(bkp_path)

    print(f"{len(tabelas)} arquivos de tabela extraídos:\n")
    for nome, conteudo in sorted(tabelas.items()):
        (outdir / nome).write_bytes(conteudo)
        print(f"  {nome:20s} {len(conteudo):>10,d} bytes")

    # também salva tudo num único pickle, útil para os próximos scripts
    with open(outdir / "_tabelas.pkl", "wb") as f:
        pickle.dump(tabelas, f)

    print(f"\nArquivos salvos em: {outdir.resolve()}")


if __name__ == "__main__":
    main()
