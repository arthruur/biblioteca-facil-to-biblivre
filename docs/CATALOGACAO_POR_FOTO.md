# Catalogação por foto da ficha CIP

Notas de projeto para uma ferramenta que **cataloga livro novo a partir de
uma foto**, reaproveitando a infraestrutura de MARC e de carga que a
migração já produziu.

> Status: 📐 **projeto, não implementação.** Nada aqui foi construído nem
> medido ainda. As afirmações sobre o BibLivre vêm do código-fonte e estão
> em [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md); as afirmações sobre
> OCR e acurácia são **hipóteses a testar** (ver "O que ainda é hipótese").

## O problema

A migração cobre o acervo que já existia. Livro que entra depois continua
sendo catalogado à mão, campo a campo. A ideia é fotografar o livro e
chegar num registro pronto para revisão.

## O alvo é a ficha CIP, não a capa

A decisão de alvo mudou durante a discussão e é a mais importante do
documento. Fotografar capa ou folha de rosto obrigaria a extrair título,
autor e editora de um layout livre — e ainda deixaria **CDD e Cutter em
aberto**, que são decisão catalográfica, não leitura.

A **ficha catalográfica CIP impressa na página de crédito** (presente em
praticamente todo livro brasileiro) resolve os dois problemas de uma vez:
é texto impresso de alto contraste, com estrutura ABNT, e **já traz CDD e
Cutter atribuídos por um bibliotecário**.

Isso importa além da conveniência: pelo que está documentado em
[IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md), o `090 $a$b$c` do
registro bibliográfico é **propagado para todo exemplar** que o BibLivre
cria. CDD ou Cutter errados não sujam só a ficha — sujam os holdings
junto.

## Decisões de arquitetura

### 1. Detectar a caixa da ficha, não a página

A ficha ABNT é um retângulo desenhado de ~12,5 × 7,5 cm (imita a ficha de
fichário). Detectar esse retângulo — e não a página inteira — dá duas
coisas:

- **Recorte automático.** A página de crédito é cheia de ruído (dados da
  editora, gráfica, tiragem, copyright). Descartar isso antes do OCR é
  melhor que pedir ao parser que adivinhe onde a ficha começa e termina.
- **Filtro de sanidade.** Proporção ~1,67. Contorno que não bate na razão
  não é a ficha.

Pipeline (o mesmo do scanner de documentos do iOS, ~40 linhas de OpenCV):
cinza → blur → Canny → `findContours` → maior quadrilátero com a proporção
esperada → `getPerspectiveTransform` + `warpPerspective` → threshold
adaptativo.

### 2. A retificação é etapa de acurácia, não de polimento

O Tesseract degrada bastante com perspectiva e rotação. Foto de celular
torta perde muito; a mesma ficha retificada e binarizada tende a ler bem
melhor. **A qualidade do pré-processamento é o que decide se o parsing
precisa ou não de um modelo.**

Complementos baratos, na mesma etapa:

- **Gate de nitidez** (variância do Laplaciano) antes de processar. Devolve
  "segura firme / chega mais perto" em vez de OCR silenciosamente errado.
- **Auto-captura** quando o quadrilátero fica estável e nítido. É o que faz
  a experiência parecer a de um scanner em vez de "tira foto → espera →
  revisa".

No iOS, o scanner do sistema (VisionKit) costuma estar acessível pelo
seletor de arquivos do Safari e já devolve a imagem retificada — **vale
testar**, mas o OpenCV entra de qualquer forma, porque é o caminho que
funciona em Android, em webcam de desktop e em foto já salva.

### 3. A ficha é fonte de ISBN e CDD/Cutter — não dos metadados gerais

Inversão deliberada: **registro autoritativo é melhor dado que OCR de
título.** O fluxo preferencial é

```
OCR → extrai ISBN → valida dígito verificador → consulta catálogo externo
      → título, autor, editora, ano, edição, páginas vêm de lá
      → CDD e Cutter vêm da ficha (o catálogo externo raramente tem)
```

O dígito verificador do ISBN-13/10 é um **detector de erro de OCR
determinístico e grátis**: pega a maioria dos erros de um dígito (`8`/`B`,
`1`/`l`, `0`/`O`). Passou, há quase-certeza; falhou, sabe-se que falhou, e
cai para o código de barras da contracapa.

Só quando o lookup falha (ISBN ilegível, livro fora das bases, edição
antiga sem ISBN) é que se parseia a ficha inteira. Isso confina o parsing
— a etapa mais frágil — ao ramo minoritário, em vez de depender dele em
100% dos livros.

### 4. OCR local; modelo só no ramo de fallback

Tesseract (`-l por`, `--psm 4` ou `6`, ficha reescalada para ~300 DPI
equivalente) roda local, offline e de graça — o que importa numa
biblioteca com conectividade ruim.

Para o parsing do ramo de fallback, a preferência é **extração por modelo,
não regex**. Motivo: o parser por regras depende da pontuação ISBD
(` / `, ` : `, ` ; `, `. — `) para achar as fronteiras dos campos, e
pontuação é justamente o que o OCR mais erra. Pior, erro de parsing não
levanta exceção — gera campo errado em silêncio. Com a ficha bem
retificada o regex fica mais viável; a decisão final sai da medição da
Fase 1, não de opinião.

### 5. Nunca gravar sem confirmação

A saída é um **rascunho pré-preenchido numa fila de revisão** — foto
original ao lado dos campos extraídos, editáveis, com CDD e Cutter em
destaque. Grava só quando a pessoa aprova. Mesma postura conservadora da
decisão de agrupamento por obra no [ROADMAP](ROADMAP.md).

### 6. Deduplicar contra o acervo migrado

Sem isso, a ferramenta começa a criar duplicatas das 14.866 obras
recém-carregadas. A chave já existe: a normalização de título, subtítulo,
autor, editora, ano, volume e edição do `scripts/consolidar.py`.

Atenção a uma assimetria já apurada: **ISBN não serve de chave contra o
acervo existente** (no Biblioteca Fácil foi digitado à mão — há três livros
distintos com o mesmo ISBN, ver [ROADMAP.md](ROADMAP.md)). Mas o ISBN lido
do código de barras ou da ficha CIP do livro novo *é* confiável. A
diferença é a origem do dado, não o campo.

## A etapa de entrega: por que não é o import nativo

O caminho intuitivo — gerar `.mrc` e importar por Catalogação → Importar —
**não** é o caminho principal, pelo que já está apurado no fonte em
[IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md):

- `Handler.saveImport()` trata `BIBLIO`, `AUTHORITIES` e `VOCABULARY`, e
  **ignora `HOLDING`**. Nenhum formato de arquivo cria exemplar no
  BibLivre, e não é contornável: a ligação é uma FK no banco
  (`biblio_holdings.record_id`), sem representação dentro de um arquivo
  MARC. Sem exemplar, o livro não é emprestável.
- Registro importado cai na **base de trabalho**, e não há "mover todos"
  para a principal.
- Os relatos de fórum de que o `949` não vem preenchido são consistentes
  com isso: o `949 $a` é escrito por `MarcUtils.setAccessionNumber` **no
  registro de exemplar**, dentro de `HoldingBO.createAutomaticHolding`.
  Sem exemplar, não há 949.

### E a inserção por SQL também não serve para o fluxo unitário

`biblio.biblivre.obras` resolve o lote, mas **não passa pelo
indexador** — o conserto é `Administração → Manutenção → Reindexar`, que
relê `biblio_records` inteiro em lotes de 30. Aceitável uma vez, para
14.866 registros. Inviável a cada livro novo.

### Caminho pretendido

**POST no caminho de save do próprio BibLivre** (o controller JSON que o
formulário de catalogação usa). Assim `BiblioRecordBO.save` faz o registro,
a indexação acontece, e `HoldingBO.createAutomaticHolding` cria o exemplar
— os três de uma vez, sem reindexar nada.

**Fallback**, se a autenticação/sessão desse endpoint não cooperar na
versão instalada: acumular aprovados em lote e usar `inserir_obras.py` +
reindex + `inserir_exemplares.py`, o caminho já validado numa carga real.

## O que ainda é hipótese

Distinção importante, porque o resto dos `docs/` deste repo é fato
verificado no fonte. Estes pontos **não são**:

1. Que o Tesseract atinge acurácia utilizável nas fichas reais deste
   acervo. Não medido.
2. Que a detecção de contorno acha a caixa da ficha de forma confiável em
   foto de celular. Não medido.
3. Que o scanner do VisionKit é alcançável pelo `<input type="file">` na
   versão de iOS em uso. Não testado.
4. Que o controller JSON de catalogação aceita POST externo com sessão.
   **Não verificado no fonte** — é a checagem que decide entre o caminho
   pretendido e o fallback.

## Fase 1 — o que medir antes de construir

O formato do `.mrc` **não** é risco: a migração já gerou 14.866 registros
ISO 2709 válidos, validados byte a byte contra a tela. Não vale gastar a
fase 1 reprovando isso.

Amostra: ~20 fotos de ficha CIP, tiradas como serão tiradas na prática,
**incluindo as ruins** (torta, fora de foco, com sombra) — são elas que
definem o projeto.

Três números decidem a arquitetura:

| Métrica | O que decide |
|---|---|
| Taxa de detecção da caixa da ficha | se o recorte automático é viável |
| Taxa de ISBN válido no checksum | quanto entra pelo lookup externo e quanto cai no parsing |
| Acurácia de CDD e Cutter | os dois campos que só a ficha tem, e que se propagam para os exemplares |

Em paralelo, a checagem de fonte do item 4 das hipóteses.

## Stack pretendida

Python + FastAPI, OpenCV (retificação e gate de nitidez), Tesseract
(`-l por`), `pymarc` para o MARC, front simples para a fila de revisão.

**O seam de reuso:** o parser deve cuspir **a mesma linha do CSV
consolidado** que o `biblio.biblivre.marc` já consome. Com isso, geração
de MARC e carga são reuso puro — e é essa fronteira que mantém o pipeline
portável para outro sistema, trocando só a etapa final de entrega.
