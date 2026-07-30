# Layout de registro por tabela

As tabelas Paradox usadas pelo Biblioteca Fácil têm **registros de
tamanho fixo**. A técnica geral para mapear os campos de uma tabela:

1. Procurar trechos de texto legível repetidos com `re.finditer` sobre os
   bytes crus da tabela (regex `[ -~\xa0-\xff]{4,}` funciona bem para
   texto em CP1252/Latin-1).
2. Medir a distância constante entre valores equivalentes em registros
   consecutivos → isso dá o **tamanho do registro**.
3. Escolher um registro cujo conteúdo real você já conhece (ex.: um
   título de livro específico) e medir o **offset de cada campo** dentro
   do registro, comparando a mesma medição em 2-3 registros vizinhos para
   confirmar que não foi coincidência.

A codificação de texto usada é **CP1252** (Windows Latin-1 — não é
CP850/CP860 apesar do software ser da era DOS/Delphi). Bytes como `0xea`,
`0xe9`, `0xe1` só fazem sentido como `ê`, `é`, `á` em CP1252.

## T05_AUTO — Autores

- Tamanho do registro: **80 bytes**
- Nome do autor: offset **47**, até ~33 bytes

| Campo | Offset | Status |
|---|---|---|
| NUMAUTOR (ID) | ? | não mapeado — provavelmente binário nos primeiros bytes do registro |
| AUTOR (nome) | 47 | ✅ mapeado |
| EXCLUSAO (flag) | ? | não mapeado |

## T09_ACER — Acervo (livros)

- Tamanho do registro: **832 bytes**
- Registro-âncora usado para medir offsets: título "Palavra Aberta" /
  CDD "371.32" / cutter "C117p" / ano "1995"

| Campo | Offset | Tamanho | Status |
|---|---|---|---|
| (não identificado — possível Coleção/Série) | 0 | ~40 | ⚠️ suspeito, não confirmado como Idioma |
| CDD | 369 | ~31 | ✅ mapeado |
| Cutter | 505 | 12 | ✅ mapeado |
| **Título** | 517 | 238 | ✅ mapeado |
| Ano de edição | 755 | 14 | ✅ mapeado |
| ISBN | ? | ? | ❌ falta mapear |
| Tombo (nº patrimônio) | ? | ? | ❌ falta mapear |
| Páginas | ? | ? | ❌ falta mapear |
| CDU | ? | ? | ❌ falta mapear |
| Autor (FK → T05_AUTO) | ? | ? | ❌ falta mapear — provavelmente binário |
| Editora (FK → T06_EDIT) | ? | ? | ❌ falta mapear — provavelmente binário |

Nomes de campo confirmados no cabeçalho da tabela (mas ainda sem offset
mapeado): `T09_NAOEMPRESTAR`, `T09_ISBN`, `T09_TOMBO`, `T09_FOTO`,
`T09_SUBTITULO`, `T09_PALAVRAS3/4/5`, `T09_ANOEDICAO2`, `T09_PAGINAS`,
`T09_CDU`, `T09_RESERVADO`, `T09_NUMIDIOMA`.

## T06_EDIT — Editoras

Ainda não iniciado. Deve seguir o mesmo padrão de T05_AUTO (registro
pequeno, nome em texto simples).

## Outras tabelas

Não iniciado: T01_USUA, T02_ACES, T03_CONF, T04_LEIT, T07_CLAS, T08_TIPO,
T10_AUAC, T11_MOVI, T12_INDC, T13_MOVM, T14_IDIO, T15_RESE, T16_TURM.

`T10_AUAC` merece atenção prioritária — pelo nome, é provavelmente a
tabela de relacionamento Autor↔Acervo, o que resolveria o vínculo
autor-livro sem precisar decifrar um campo binário dentro do próprio
registro do Acervo.
