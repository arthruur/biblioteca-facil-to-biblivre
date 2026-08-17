# Formato do container `.bkp`

Este documento registra o processo de engenharia reversa do arquivo de
backup do Biblioteca Fácil, para referência futura (e para quem precisar
validar/corrigir o que foi descoberto).

## Primeira impressão

`file` no arquivo retorna apenas `data` — sem assinatura conhecida. O nome
`.bkp` é genérico (usado por dezenas de programas diferentes, sem relação
entre si), então não havia como assumir nada a partir da extensão.

## Cabeçalho do arquivo

Abrindo em hexdump, o início do arquivo é:

```
8a be 8e 59 23 64 cb 40 3d 71 d2 e3 bc 64 d0 01   <- 16 bytes, fixos entre backups
0c ad 00 00 00 00 00 00                            <- 8 bytes (uso não confirmado)
50 c8 1d 88 2d 93 e6 40                            <- 8 bytes, double (timestamp)
21 "Backup do dia 30/07/2026 10:08:55"              <- string Pascal (1 byte tamanho + texto)
10 00 00 00                                         <- int32: quantidade de tabelas (16)
08 "T01_USUA"  08 "T02_ACES"  08 "T03_CONF"  ...    <- strings Pascal, uma por tabela
```

Os primeiros 16 bytes se repetem **idênticos** em todos os backups desse
mesmo Biblioteca Fácil que analisamos. Deciframos depois, ao atacar o
cabeçalho dos `.dat`: são um **double TDateTime do Delphi seguido de um
FILETIME do Windows**, copiados do cabeçalho de uma tabela (os mesmos 16
bytes aparecem no offset `0x09` de cada `.dat`). Ver
[TABELAS.md](TABELAS.md).

**Armadilha:** o campo de quantidade de tabelas parece à primeira vista
ser 1 byte (valor `0x10` = 16), mas na verdade é um **int32** (4 bytes:
`10 00 00 00`). Tentar ler como 1 byte faz o parser desalinhar e "engolir"
os 3 bytes seguintes como se fossem entradas vazias.

## Entradas de arquivo (uma por tabela `.dat`/`.idx`)

Depois da lista de nomes de tabela, o arquivo é uma sequência de
entradas, cada uma representando um arquivo de tabela:

```
0c "T01_USUA.dat"                          <- string Pascal: nome do arquivo
<metadados de tamanho variável>            <- ver abaixo
<int32 tamanho comprimido><dados zlib>      <- primeiro bloco de dados
[<int32 tamanho comprimido><dados zlib>]*   <- blocos adicionais, se o arquivo for grande
```

Os metadados entre o nome do arquivo e o primeiro bloco zlib incluem
(nem todos os campos foram fixados com certeza, mas não precisamos deles
para extrair os dados):

- tamanho total descomprimido do arquivo (int64)
- timestamp (double, TDateTime do Delphi)
- 8 bytes não identificados
- 1 byte (método de compressão? sempre `0x06` nas amostras)
- tamanho do próximo bloco comprimido (int32)

Esse bloco de metadados **tem tamanho diferente** para entradas `.dat`
(33 bytes) e `.idx` (29 bytes) — por isso o parser final não tenta
decodificar os metadados campo a campo. Em vez disso:

## Estratégia de parsing robusta (a que funcionou)

1. Depois do nome do arquivo, procurar os dois bytes de assinatura zlib
   (`0x78` seguido de `0x01`, `0x5e`, `0x9c` ou `0xda` — os 4 valores
   válidos de FLG do zlib) numa janela de até ~80 bytes à frente.
2. Usar `zlib.decompressobj()` para descomprimir a partir dali. O objeto
   informa em `unused_data` quantos bytes sobraram depois do fim real do
   stream — isso dá o tamanho exato consumido, **sem precisar confiar em
   nenhum campo de tamanho do cabeçalho**.
3. Tabelas grandes (>64KB descomprimidos) são divididas em múltiplos
   blocos zlib sequenciais. Cada bloco de continuação não tem nome nem
   metadados — é só `<int32 tamanho comprimido><dados zlib>` direto.
   O parser detecta isso simplesmente checando se a próxima posição
   "parece" um nome de tabela válido (regex contra a lista de tabelas
   conhecidas); se não parecer, assume que é continuação do arquivo
   atual.

Essa abordagem foi validada em produção: rodando sobre um `.bkp` real de
~5,4 MB, a posição final do parser bate **exatamente** com o tamanho do
arquivo (nenhum byte sobrando, nenhum erro de descompressão).

## Resultado

32 arquivos recuperados (16 tabelas × `.dat` + `.idx`), idênticos aos
originais. A partir daqui, o trabalho passa a ser
sobre o **formato de registro de cada tabela** — ver
[TABELAS.md](TABELAS.md).
