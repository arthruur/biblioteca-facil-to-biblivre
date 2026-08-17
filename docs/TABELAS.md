# Layout das tabelas

> **Esta página foi reescrita.** A primeira versão descrevia offsets
> descobertos à mão, comparando textos conhecidos dentro dos bytes crus.
> Descobrimos depois que **cada arquivo `.dat` descreve o próprio layout**
> num catálogo de campos no cabeçalho — nome, tipo, tamanho e offset de
> todos os campos. Não é preciso adivinhar nada.
>
> A caça manual também tinha produzido **um erro**: o campo lido como
> "título" era na verdade `T09_SUBTITULO`. O registro-âncora usado nas
> medições era o livro didático *Português – Palavra Aberta*, cujo título
> é "Português" e subtítulo "Palavra Aberta" — parecia que "Palavra
> Aberta" era o título e "Português" era um campo de idioma.

## O formato não é Paradox

Apesar do Biblioteca Fácil ser um aplicativo Delphi da era do Paradox, os
`.dat` **não seguem o formato de cabeçalho Paradox**. Tentar lê-los como
Paradox (recordSize em `0x00`, numFields em `0x21`) devolve lixo. É um
formato próprio do aplicativo.

## Cabeçalho do arquivo `.dat`

| Offset | Tipo | Conteúdo |
|---|---|---|
| `0x00` | 2 bytes | assinatura fixa `79 79` (`'yy'`) |
| `0x09` | double | TDateTime do Delphi |
| `0x11` | 8 bytes | FILETIME do Windows |
| `0x1d` | 4 × int32 | contadores de registro (o 2º é o total) |
| `0x2d` | uint16 | **recordSize** — tamanho do registro |
| `0x2f` | uint16 | **numFields** — quantidade de campos |
| `0x47` | Pascal string | descrição da tabela (ex.: `"Cadastro do Acervo"`) |

Os 16 bytes em `0x09`–`0x18` são exatamente os mesmos que aparecem no
início do container `.bkp` — o que FORMATO_BKP.md chamava de "assinatura
fixa da instalação" é, na verdade, esse par timestamp + FILETIME copiado
de um cabeçalho de tabela.

## Catálogo de campos

Depois do cabeçalho vêm `numFields` descritores de **768 bytes cada**,
começando no offset **514**. Dentro de cada descritor:

| Offset | Tipo | Conteúdo |
|---|---|---|
| `+0` | Pascal string | nome do campo (ex.: `T09_TITULO`) |
| `+162` | byte | tipo (tabela abaixo) |
| `+164` | byte | largura de exibição na tela |
| `+167` | byte | tamanho do campo em bytes |
| `+170` | uint16 | **offset do campo dentro do registro** |
| `+766` | byte | índice do campo + 2 |

Os dados começam logo depois: `data_start = 513 + numFields * 768`.

### Tipos

| Código | Significado |
|---|---|
| 1 | alpha — texto CP1252, terminado em `\x00` |
| 2 | date — int32, dias desde 01/01/0001 (`0` = vazio) |
| 4 | short — int16 |
| 5 | enum/booleano — int16 |
| 6 | long — int32 |
| 7 | double — float64 |

A codificação de texto é **CP1252** (Windows Latin-1), não CP850/CP860.

### Teste de sanidade do layout

Cada campo ocupa `tamanho + 1` bytes: há **1 byte de flag antes do dado**
(provavelmente indicador de nulo). Isso fecha a conta exatamente:

```
offset_do_primeiro_campo + Σ(tamanho + 1) ≈ recordSize
```

No Acervo: `25 + 807 = 832` = `recordSize` ✅. Algumas tabelas têm alguns
bytes de sobra no fim do registro (alinhamento), por isso a comparação é
`≤`. `bf_tabela.Tabela.validar()` faz esse teste — **as 16 tabelas
passam**.

## Ver o layout de qualquer tabela

```bash
python scripts/extrair_tabela.py pasta_das_tabelas --listar
```

## Tabelas relevantes para a migração

Contagens de um backup real de 2026-07-30.

### T09_ACER — Acervo (16.258 registros, 33 campos, 832 bytes)

| Campo | Tipo | Offset | Tam. |
|---|---|---|---|
| T09_NUMACERVO | long | 25 | 4 |
| T09_TITULO | alpha | 30 | 51 |
| T09_NUMEDITORA | long | 82 | 4 |
| T09_NUMTIPOITEM | long | 87 | 4 |
| T09_NUMCLASSIFIC | long | 92 | 4 |
| T09_EXCLUSAO | date | 97 | 4 |
| T09_EXEMPLAR | alpha | 102 | 6 |
| T09_VOLUME | alpha | 109 | 6 |
| T09_EDICAO | alpha | 116 | 6 |
| T09_ANOEDICAO | long | 123 | 4 |
| T09_LOCAL | alpha | 128 | 6 |
| T09_AQUISICAO | date | 135 | 4 |
| T09_BAIXA | date | 140 | 4 |
| T09_PALAVRAS1 | alpha | 145 | 61 |
| T09_PALAVRAS2 | alpha | 207 | 61 |
| T09_OBS1 | alpha | 269 | 61 |
| T09_OBS2 | alpha | 331 | 61 |
| T09_EMPRESTADO | short | 393 | 2 |
| T09_NAOEMPRESTAR | short | 396 | 2 |
| T09_CDD | alpha | 399 | 21 |
| T09_ISBN | alpha | 421 | 16 |
| T09_TOMBO | long | 438 | 4 |
| T09_FOTO | alpha | 443 | 91 |
| T09_CUTTER | alpha | 535 | 11 |
| T09_SUBTITULO | alpha | 547 | 51 |
| T09_PALAVRAS3 | alpha | 599 | 61 |
| T09_PALAVRAS4 | alpha | 661 | 61 |
| T09_PALAVRAS5 | alpha | 723 | 61 |
| T09_ANOEDICAO2 | alpha | 785 | 11 |
| T09_PAGINAS | long | 797 | 4 |
| T09_CDU | alpha | 802 | 21 |
| T09_RESERVADO | short | 824 | 2 |
| T09_NUMIDIOMA | long | 827 | 4 |

**Armadilha:** o ano de edição está em `T09_ANOEDICAO2` (alpha, 12.688
preenchidos). `T09_ANOEDICAO` é um long e está zerado em todo o acervo.

### T05_AUTO — Autores (7.258 registros)

`T05_NUMAUTOR` (long, 25) · `T05_AUTOR` (alpha, 30, 41) ·
`T05_EXCLUSAO` (date, 72)

### T06_EDIT — Editoras (2.027 registros)

`T06_NUMEDITORA` (long, 25) · `T06_EDITORA` (alpha, 30, 41) ·
`T06_EXCLUSAO` (date, 72) · `T06_LOCALIZACAO` (alpha, 77, 21 — cidade,
serve como local de publicação no MARC 260$a)

### T10_AUAC — "Cadastro de Autores nas Obras" (17.883 registros)

A tabela N:N entre acervo e autores, como suspeitávamos pelo nome:

`T10_SEQUENCIA` (long, 25) · `T10_NUMACERVO` (long, 30) ·
`T10_NUMAUTOR` (long, 35)

`T10_SEQUENCIA` é um sequencial **global** da tabela, não a ordem do autor
dentro da obra — não existe campo de ordem de autoria. Distribuição:
13.962 obras com 1 autor, 1.229 com 2, 262 com 3, até um caso com 10.
659 itens de acervo não têm nenhum autor vinculado.

### Tabelas de apoio

| Tabela | Registros | Chave → valor |
|---|---|---|
| T07_CLAS | 356 | `T07_NUMCLASSIFIC` → `T07_CLASSIFICACAO` |
| T08_TIPO | 27 | `T08_NUMTIPOITEM` → `T08_TIPOITEM` |
| T14_IDIO | 5 | `T14_NUMIDIOMA` → `T14_IDIOMA` (PORTUGUES, INGLÊS, ESPANHOL, FRANCÊS, ALEMÃO) |

## Integridade referencial (verificada no backup real)

- 16.258 `NUMACERVO` únicos, nenhum título vazio
- 0 vínculos em T10_AUAC apontando para acervo inexistente
- 1 vínculo apontando para autor inexistente
- 1 item de acervo apontando para editora inexistente

Ou seja: os joins são confiáveis, com um punhado de órfãos irrelevantes.

## Exclusão lógica

`EXCLUSAO` **não é booleano** — é uma data. `0` significa ativo; qualquer
outro valor é a data em que o registro foi excluído. No acervo há 7
registros excluídos; entre os autores, 46.

## Demais tabelas

Não são necessárias para a migração bibliográfica, mas o leitor genérico
já as decodifica: T01_USUA (usuários), T02_ACES (permissões), T03_CONF
(configuração), T04_LEIT (2.743 leitores — **dados pessoais**), T11_MOVI
(19.711 movimentações), T12_INDC (índice), T13_MOVM (17.492 empréstimos),
T15_RESE (803 reservas), T16_TURM (turmas).
