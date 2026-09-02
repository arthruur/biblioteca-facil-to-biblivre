# Spec de UI/UX — Catalogação por ISBN

Documento de referência para prototipar as telas servidas por
`scripts/servidor.py`. Descreve o que cada tela precisa mostrar, em que estado
ela pode estar e por quê — não o CSS que a implementação atual usa.

Quem for redesenhar pode ignorar a aparência de hoje inteira; o que não pode
mudar sem quebrar o produto são os **estados**, os **destinos** e as
**garantias** listadas aqui.

---

## 1. O que o produto faz

Catalogar livro novo lendo o código de barras. O trabalho acontece em dois
lugares, com duas pessoas em duas posturas físicas diferentes:

| | Celular (`/`) | PC (`/fila`) |
|---|---|---|
| Postura | de pé na estante, livro na mão | sentado, teclado e mouse |
| Ritmo | segundos por livro, repetitivo | minutos por lote, cuidadoso |
| Objetivo | **não perder o ritmo** | **não deixar erro passar** |
| Erro caro | perder um bipe | gravar ficha duplicada no acervo |

Essa divisão é a decisão de design mais importante: **a tela do celular nunca
pede decisão**, e a tela do PC **nunca é apressada**.

### Fluxo completo

```
     CELULAR                          PC                        BIBLIVRE 5
  ┌───────────┐   enviar    ┌──────────────────┐   exportar   ┌────────────┐
  │   LOTE    │────lote────►│       FILA       │─────────────►│  banco     │
  │ (memória) │             │ (data/fila/*.json)│              │ PostgreSQL │
  └───────────┘             └──────────────────┘              └────────────┘
   bipa e some               revisa, edita, decide             obras+exemplares
```

O **lote** é volátil de propósito (bandeja do scanner). A **fila** persiste em
disco e sobrevive a reinício do servidor — é trabalho pendente de gente, não
cache.

---

## 2. O conceito central: destino no BibLivre

Toda a tela do PC gira em torno de uma pergunta por item:

> **Este ISBN já está catalogado?**

A resposta define o destino, e os dois destinos são visualmente diferentes em
toda parte:

| Destino | Quando | O que acontece na gravação |
|---|---|---|
| **Obra nova** | ISBN não achado no acervo | 1 registro em `biblio_records` + N exemplares em `biblio_holdings`. Exige reindexar. |
| **+N exemplares** | ISBN já existe | **Nenhum** registro novo. Só N exemplares no `record_id` que já existe. Não exige reindexar. |
| **Não verificado** | banco desconectado | Cai em "obra nova" na gravação — **estado de alerta**, nunca silencioso. |

A comparação é por ISBN normalizado, com equivalência ISBN-10 ↔ ISBN-13: um
livro cadastrado em 1998 com ISBN-10 casa com o EAN-13 do código de barras de
hoje.

> **Limite conhecido, e é de propósito:** o casamento é só por ISBN, nunca por
> título/autor. A migração já mostrou que ISBN digitado à mão no acervo antigo
> não é identidade confiável (três livros diferentes com o mesmo ISBN — ver
> `ROADMAP.md`). Aqui o ISBN vem do código de barras, então é confiável; mas
> um livro sem ISBN ou com ISBN errado entra como obra nova, e a tela precisa
> deixar isso visível em vez de esconder. Preferir separar demais a juntar
> demais.

---

## 3. Tela do celular — `/`

### Objetivo
Bipar muitos livros em sequência sem tocar na tela entre um e outro.

### Regiões

1. **Visor da câmera** (topo, ~46% da altura) — scanner contínuo, não fecha
   entre leituras. Faixa de status sobreposta na base.
2. **Galeria do lote** (faixa horizontal) — um card por título, o mais recente
   à direita, rolagem automática. Só aparece com o lote não-vazio.
3. **Controles** — Escanear / Fechar câmera / Foto; entrada manual de ISBN
   (escondida no celular, visível no desktop).
4. **Barra de envio** (fixa na base) — "Enviar lote para fila (N tit, M ex)".

### Card do lote

```
┌──────────────────┐
│ 9786559870530 ×3 │ ← ISBN + multiplicador (só se >1)
│ 2041             │ ← título (vem do lookup, pode chegar depois)
│ Kai-Fu Lee       │
│ ✓ já no acervo·5 │ ← só quando o ISBN já existe (borda verde)
│ BrasilAPI/CBL    │ ← fonte do metadado
└──────────────────┘
```

### Feedback por bipe — nunca modal, nunca bloqueante

| Situação | Retorno |
|---|---|
| ISBN novo no lote | vibra 60ms, card entra com animação, status "Adicionado" |
| ISBN repetido | vibra, multiplicador do card sobe, status "+1 exemplar (×N)" |
| Mesmo frame lido 2× | **ignorado** (janela de 2s) — não conta exemplar a mais |
| Lookup não achou | card fica sem título, status neutro; **não interrompe** |
| Já no acervo | card ganha borda verde e a linha "✓ já no acervo · N ex" |

### Modal de detalhe (toque no card)
Ficha completa: capa, título/subtítulo, autor, editora, ano, páginas, idioma,
descrição, ISBN, fonte. Editáveis: **quantidade** (stepper), **CDD**,
**Cutter**. Ação: Remover do lote.

Quando o ISBN já está no acervo, o modal abre com um aviso verde no topo:

> **✓ Já está no acervo**
> Obra #14904 · 5 exemplar(es) hoje.
> Não vai virar ficha nova — os 3 exemplares entram nessa obra.

### Estados de erro que o protótipo precisa cobrir
- câmera negada pelo navegador
- código riscado/amassado que não decodifica (há fallback OCR após 5 falhas)
- servidor fora do ar no meio de um lote (o lote em memória do navegador
  sobrevive; o envio é que falha)

---

## 4. Tela do PC — `/fila`

### Objetivo
Ver de relance **o que vai acontecer no acervo** e corrigir antes que aconteça.

### Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ Fila de revisão   [← Escanear]        [● Acervo: 10.488 ISBNs] [↻]     │  cabeçalho fixo
├────────────────────────────────────────────────────────────────────────┤
│ ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐               │
│ │  26  ││  26  ││   0  ││   7  ││  19  ││   5  ││   0  │               │  indicadores
│ │ A EXP││PENDEN││REVISA││ NOVAS││ACERVO││ATENÇÃ││EXPORT│               │
│ └──────┘└──────┘└──────┘└──────┘└──────┘└──────┘└──────┘               │
├────────────────────────────────────────────────────────────────────────┤
│ [⌕ buscar…]  [Todos|Pendentes|Revisados|Exportados|Ignorados]          │  filtros
│              □ só já no acervo                    [ordenação ▾]        │
├────────────────────────────────────────────────────────────────────────┤
│ □ │📕│ Obra              │ ISBN      │ Destino        │ Ex │ Situação │ │
│ □ │📕│ 2041              │978655987… │ +3 exemplares  │ 3  │ pendente │ │
│   │  │ Kai-Fu Lee·Globo  │BrasilAPI  │ obra #14904·5  │    │          │ │
│ ☑ │📕│ On the Road       │978014028… │ obra nova      │ 4  │ revisado │ │
├────────────────────────────────────────────────────────────────────────┤
│         [2 selecionados ✓Revisado ↺Pendente ⊘Ignorar 🗑Remover]        │  flutuante
├────────────────────────────────────────────────────────────────────────┤
│ □ Gravar no BibLivre  [senha]   26 itens → 7 novas · 19 acervo · 60 ex │  rodapé fixo
│                                                        [Exportar →]    │
└────────────────────────────────────────────────────────────────────────┘
```

### Os sete indicadores

| Indicador | Fonte | Por que existe |
|---|---|---|
| **A exportar** | `pendente + revisado` | o tamanho real do trabalho |
| **Pendentes** | `por_status.pendente` | fila de revisão |
| **Revisados** | `por_status.revisado` | prontos para gravar |
| **Obras novas** | `a_exportar − ja_no_acervo` | quantas fichas nascem |
| **Já no acervo** | itens com `acervo.existe` | quantas duplicatas foram evitadas |
| **Precisam de atenção** | sem título + ISBN repetido | o que vai dar problema |
| **Exportados** | `por_status.exportado` | histórico |

O par **Obras novas / Já no acervo** é o coração da tela: é a resposta à
pergunta "quanto do que escaneei é livro que a biblioteca já tem?".

### Coluna "Destino no BibLivre"

| Aparência | Significado |
|---|---|
| `[obra nova]` roxo + "vira ficha + N exemplares" | registro novo |
| `[+N exemplares]` verde + "obra #14904 · tem 5" | só holdings |
| `[não verificado]` cinza + "banco desconectado" | **alerta** |

### Ciclo de vida do item

```
              ┌──────────► ignorado ──┐
              │                       │ (fica na fila, fora do export)
   pendente ──┼──► revisado ──────────┼──► exportado
              │        ▲              │
              └────────┘              └──► removido (arquivo apagado)
```

`exportado` é terminal: linha esmaecida, quantidade travada, fora de qualquer
export futuro.

### Ações

**Por item** — editar (✎ abre editor embutido), alternar revisado (✓/↺),
remover (🗑, com confirmação), stepper de quantidade (grava com debounce 400ms).

**Editor embutido** — 12 campos: título, subtítulo, autor, editora, ano,
edição, páginas, idioma, ISBN, CDD, Cutter, localização. Editar o ISBN
**reconsulta o acervo** e o destino pode mudar na hora — o protótipo precisa
mostrar essa transição.

**Em lote** — barra flutuante que só aparece com seleção: marcar revisado,
voltar a pendente, ignorar, remover. Com seleção ativa, o export passa a valer
**só para os selecionados** (o rodapé precisa dizer isso).

**Atalhos** — `/` foca a busca, `Esc` fecha modal/editor, `Ctrl+A` seleciona o
que está visível.

### Modal de conexão com o banco

Aberto pela pílula de status do cabeçalho. Campos: host, banco, usuário,
schema, senha. Ao conectar com sucesso, a tela **reavalia a fila inteira** e
informa quantos itens passaram a ser "já no acervo".

> A senha vive só na memória do processo do servidor, nunca em disco.
> Alternativas de configuração: `--db-senha` na linha de comando ou
> `PGPASSWORD`/`BIBLIVRE_DB_SENHA` no ambiente.

### Modal de confirmação do export

Obrigatório antes de gravar. Mostra, antes de qualquer escrita:

- quantas obras novas
- quantas já no acervo (com a lista: título → `#record_id +N`)
- total de exemplares
- **aviso em âmbar se o banco estiver desconectado**: nenhum ISBN foi
  verificado, então tudo entra como obra nova

Dois modos, com rótulos diferentes:
- `Gerar arquivos` — só escreve `data/export/obras_*.mrc` e `exemplares_*.csv`
- `Gravar agora` — escreve no banco, numa transação só

### Depois de gravar

Mensagem no rodapé com o que aconteceu, e — **só quando houve obra nova** — o
lembrete de reindexar (Administração → Manutenção → Reindexar). Se só entraram
exemplares, a tela diz explicitamente que reindexar não é necessário. Um JSON
de conferência é baixado automaticamente.

---

## 5. Estados que o protótipo precisa desenhar

Nenhum destes é hipotético; todos acontecem em uso normal.

| # | Estado | Onde aparece |
|---|---|---|
| 1 | Fila vazia | ilustração + "escaneie no celular e envie o lote" |
| 2 | Filtro sem resultado | "nenhum item com esse filtro" (≠ do vazio) |
| 3 | Banco desconectado | pílula âmbar, destino "não verificado", aviso no export |
| 4 | Banco com erro de auth | pílula âmbar + mensagem do Postgres no modal |
| 5 | Item sem metadados | título em itálico âmbar "— sem metadados —", conta em Atenção |
| 6 | ISBN repetido na fila | conta em Atenção (o servidor soma exemplares, mas itens antigos de antes desta versão podem estar duplicados) |
| 7 | Item já exportado | linha esmaecida, controles travados |
| 8 | Gravação falhou | mensagem vermelha; arquivos MRC/CSV **já estão em disco**, nada foi gravado pela metade (transação única) |
| 9 | Senha faltando | pedido explícito, sem tentar gravar |
| 10 | Seleção ativa | rodapé muda de "26 itens" para "3 itens (seleção)" |

---

## 6. Contrato de API

Tudo em JSON. Os campos abaixo são o que a tela consome — o protótipo pode ser
alimentado com mocks nesse formato.

### Captura
| Método | Rota | Uso |
|---|---|---|
| `POST` | `/api/lote` `{isbn}` | adiciona ao lote; repetido incrementa |
| `GET` | `/api/lote` | lista o lote |
| `PUT` | `/api/lote/{isbn}` `{quantidade}` | ajusta exemplares |
| `DELETE` | `/api/lote/{isbn}` · `/api/lote` | remove um · limpa |
| `POST` | `/api/lote/enviar` | move o lote para a fila |
| `POST` | `/api/capturar` (multipart) | OCR de ficha CIP |
| `GET` | `/api/lookup/{isbn}` | metadados sem adicionar |

> `/api/carrinho*` continua respondendo como alias de `/api/lote*`.

### Fila
| Método | Rota | Uso |
|---|---|---|
| `GET` | `/api/fila?status=&busca=` | lista (status aceita `pendente,revisado`) |
| `GET` | `/api/fila/stats` | os sete indicadores |
| `GET` `PUT` `DELETE` | `/api/fila/{id}` | item: ler, editar, remover |
| `POST` | `/api/fila/acoes` `{ids,acao}` | ação em lote |
| `POST` | `/api/fila/reconsultar` | reavalia tudo contra o acervo |
| `POST` | `/api/fila/exportar-biblivre` `{executar,ids,db}` | gera / grava |

### Acervo
| Método | Rota | Uso |
|---|---|---|
| `GET` | `/api/acervo/status` | diagnóstico do índice |
| `GET` | `/api/acervo/isbn/{isbn}` | `{existe, record_id, exemplares, titulo}` |
| `GET` `POST` | `/api/db` | ler estado · conectar e reavaliar |
| `POST` | `/api/acervo/reindexar-cache` | força nova varredura |

### Item da fila

```json
{
  "id": "20260901_022049_842182",
  "timestamp": "2026-09-01T02:20:49",
  "status": "pendente",
  "isbn": "9786559870530",
  "titulo": "2041", "subtitulo": "", "autor": "Kai-Fu Lee, Chen Qiufan",
  "editora": "Globo Livros", "ano": "2022", "edicao": "", "paginas": "480",
  "idioma": "pt", "capa": "https://…", "fonte": "BrasilAPI/CBL",
  "cdd": "", "cutter": "", "localizacao": "", "notas": "",
  "quantidade": 3, "exemplares": 3,
  "acervo": {
    "existe": true, "record_id": 14904, "exemplares": 5,
    "titulo": "2041", "autor": "Kai-Fu Lee…", "id_origem": "(BF)900128"
  }
}
```

`acervo` é `null` quando o ISBN não está no acervo **ou** quando não havia
banco no momento da consulta — a tela distingue os dois casos pelo estado da
conexão, não pelo item.

### Resposta do export

```json
{
  "status": "ok",
  "obras_novas": 3, "obras_existentes": 19,
  "exemplares_novos": 8, "exemplares_existentes": 52, "exemplares": 60,
  "detalhe_existentes": [
    {"isbn":"9786559870530","titulo":"2041","record_id":14904,
     "exemplares_atuais":5,"acrescentar":3}
  ],
  "mrc": "data/export/obras_20260901_231102.mrc",
  "csv": "data/export/exemplares_20260901_231102.csv",
  "inseridos": 3, "exemplares_inseridos": 60,
  "reindex_necessario": true,
  "mensagem": "Gravado: 3 obra(s) nova(s)…",
  "ids": ["20260901_022049_842182", "…"]
}
```

`status` possíveis: `ok`, `vazio`, `senha_requerida`, `gerado_sem_inserir`.

---

## 7. Regras que a interface não pode quebrar

1. **A tela do celular nunca bloqueia.** Nada de modal obrigatório, confirmação
   ou espera de rede entre dois bipes.
2. **Nenhuma escrita no banco sem confirmação explícita** que mostre antes
   quantas fichas nascem e quantas são reaproveitadas.
3. **Banco desconectado é sempre visível**, nunca degrada em silêncio — porque
   sem ele todo livro vira obra nova e o dano é duplicata no acervo.
4. **Reindexar só é pedido quando houve obra nova.** Pedir sempre treina o
   usuário a ignorar o aviso.
5. **Gravação é uma transação só.** Não existe "gravou metade".
6. **A fila sobrevive a reinício.** Nada de trabalho de revisão só em memória.
7. **`exportado` é terminal.** Nunca reexportar sem ação deliberada — é assim
   que se cria exemplar fantasma.

---

## 8. Vocabulário

Um termo por conceito, em toda a interface e no código:

| Termo | É | Não é |
|---|---|---|
| **Lote** | a bandeja do scanner, volátil | "carrinho" (nome antigo, só nos aliases de API) |
| **Fila** | trabalho pendente de revisão, em disco | "lista", "pendências" |
| **Obra** | registro bibliográfico (`biblio_records`) | "livro", "título" |
| **Exemplar** | cópia física (`biblio_holdings`) | "cópia", "volume" |
| **Tombo** | `accession_number`, `Bib.2026.687` | "código", "registro" |
| **Destino** | obra nova ou +N exemplares | — |
| **Acervo** | o que já está no BibLivre | "base", "catálogo" |
