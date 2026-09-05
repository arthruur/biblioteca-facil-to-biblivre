# Spec de UI/UX — Catalogação por ISBN

Contrato das telas. Descreve o que cada uma precisa mostrar, em que estado ela
pode estar e por quê — não o CSS que a implementação usa. As seções 1 a 8 são
da catalogação por ISBN, o trabalho de todo dia; a 9 é da migração de acervo
legado, o trabalho do primeiro dia.

As telas vivem em `apps/web` (React); as rotas que elas consomem, em
`apps/api`. Quem for redesenhar pode trocar a aparência inteira; o que não pode
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
- código riscado/amassado que não decodifica (após 8 leituras falhas seguidas
  entra o OCR da faixa de números, validado pelo dígito verificador)
- servidor fora do ar no meio de um lote (o lote em memória do navegador
  sobrevive; o envio é que falha)

### A bandeja começa recolhida

A tela abre com o visor grande e o lote reduzido a uma linha de resumo
("3 títulos · 5 ex") com um `+` para abrir a galeria de cards. Motivo: o gesto
que a tela serve é apontar a câmera, e a galeria só interessa na conferência,
não entre um bipe e o outro. Recolhida, a barra do lote ganha um **Enviar**
compacto — recolher nunca pode esconder o envio de um lote que existe. O rodapé
com a entrada manual de ISBN e as mensagens de erro continua visível nos dois
estados.

### Lanterna

O visor tem um botão de lanterna sempre presente enquanto a câmera está aberta
— inclusive quando `getCapabilities()` não anuncia `torch`, porque muitos
aparelhos anunciam o recurso como lista (`[false, true]`), só o expõem em
`getSettings()`, ou simplesmente mentem. A tentativa é barata e o resultado é
conferido lendo `torch` de volta: se a lanterna não acendeu de verdade, a barra
de status diz "A lanterna não respondeu neste aparelho" em vez de deixar um
botão aceso mentindo.

---

## 3.1 Bancada do scanner — `/scanner-debug`

Tela de conferência, fora do fluxo e fora da barra de navegação: a mesma câmera
da tela de bipar, sem lote e sem envio. Existe porque "o scanner não lê" não é
sintoma acionável — o laço tem quatro etapas em sequência e cada uma falha por
motivo próprio:

| # | Etapa | Falha típica |
|---|---|---|
| 1 | **Quadro** — o `<video>` entrega pixels (`videoWidth`, `readyState`) | permissão, contexto inseguro, aba em segundo plano |
| 2 | **Candidatos** — ROI acha o quadrado das barras num canvas de 400px | código pequeno, torto, ou contraste baixo |
| 3 | **Decodificação** — `BarcodeDetector` lê o recorte (ou o quadro cheio, na salvaguarda) | foco, resolução, formato fora do EAN-13 |
| 4 | **Classificação** — o texto lido é ISBN, EAN de preço ou lixo | código de preço na contracapa |

A tela mostra, ao vivo: contador por etapa, passos por segundo, resolução do
quadro, densidade do melhor candidato, os últimos códigos **brutos** com o
veredito da classificação e uma frase apontando a primeira etapa que travou.

Garantias que ela precisa manter:

- **etapas 2 e 3 desligáveis em separado** — é o teste que responde se a ROI
  está atrapalhando ou salvando;
- **congelar e andar de passo em passo**, sem fechar a câmera;
- **espelhar o recorte** que foi para o decodificador — quadradinho no lugar
  certo com recorte borrado é foco, não detecção;
- **não gravar nada**: o que é lido só aparece na lista da própria tela.

Os quadradinhos das detecções são projetados no recorte real do vídeo (o visor
desenha a câmera com `object-fit: cover`, então coordenada do quadro não é
porcentagem do elemento). Sem essa projeção eles pousam ao lado do código, e
quem está depurando culpa o scanner por um erro de desenho.

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
| **Execução** | uma migração de acervo legado, do `.bkp` ao commit | "importação", "job" |
| **Conferência** | o dry-run da migração, que não toca no banco | "prévia", "simulação" |
| **Fila** | trabalho pendente de revisão, em disco | "lista", "pendências" |
| **Obra** | registro bibliográfico (`biblio_records`) | "livro", "título" |
| **Exemplar** | cópia física (`biblio_holdings`) | "cópia", "volume" |
| **Tombo** | `accession_number`, `Bib.2026.687` | "código", "registro" |
| **Destino** | obra nova ou +N exemplares | — |
| **Acervo** | o que já está no BibLivre | "base", "catálogo" |

---

## 9. Tela de migração — `/migracao`

### Objetivo

Trazer o acervo inteiro de uma biblioteca que vem do *Biblioteca Fácil*: obras,
exemplares, leitores, empréstimos, multas e reservas. Roda **uma vez por
biblioteca**, no primeiro dia, e sai do caminho depois.

É o oposto da catalogação em ritmo e em risco. Lá são segundos por livro e o
erro caro é perder um bipe; aqui são minutos de leitura antes de um clique que
escreve dezenas de milhares de linhas e não tem desfazer pela tela. Por isso
ela é uma tela separada — e por isso fica no PC, como a fila.

### Os três passos

| Passo | O que faz | Toca no banco? |
|---|---|---|
| **1. Enviar o `.bkp`** | extrai as 16 tabelas e lista o que veio dentro: nome, descrição do próprio cabeçalho, nº de registros, layout válido | não |
| **2. Conferir** | gera `obras.mrc` e `exemplares.csv` e conta o que a gravação faria, com os descartes e seus motivos | só leitura |
| **3. Gravar** | uma transação, do primeiro registro bibliográfico à última reserva | sim |

O passo 2 existe porque o 3 não tem desfazer. É o mesmo dry-run que os CLIs de
`scripts/` imprimem no terminal, em números na tela.

### Estados

| Estado | A tela mostra |
|---|---|
| `vazio` | a área de arrastar o `.bkp`, com o aviso de que o arquivo tem dado pessoal |
| `pronto` | o inventário das tabelas e as opções do que migrar |
| `conferindo` / `gravando` | os passos, um deles marcado como em curso |
| `conferido` | indicadores, cartões por bloco, avisos, impedimentos e os arquivos para baixar |
| `concluido` | o que entrou, o que ficou de fora e os próximos passos fora do app |
| `erro` | o que falhou e, na gravação, a frase que responde "entrou metade?" |

### Garantias (além das da seção 7, que continuam valendo)

1. **A gravação é uma transação só, e a tela promete isso por escrito.** Acervo
   e circulação fecham juntos: não existe empréstimo sem exemplar nem exemplar
   sem obra.
2. **Base ocupada é impedimento, não aviso.** Migração é carga de base nova.
   Prosseguir mesmo assim existe (o `--permitir-existentes` dos CLIs), é uma
   caixa marcada à mão e é a única em âmbar na tela.
3. **Nada é gravado sem conferência.** O MRC que entra no banco é o que a
   conferência gerou — gravar sem conferir seria gravar o que ninguém viu.
4. **A conferência roda sem banco.** O que ela não pôde verificar aparece
   listado, nunca omitido (a mesma regra da pílula do acervo).
5. **A execução sobrevive a reinício**, como a fila. Uma que morreu no meio da
   gravação volta dizendo que não é possível afirmar daqui se a transação
   commitou — a tela não adivinha, manda conferir no BibLivre.
6. **Descartar apaga os arquivos**, não só a referência: o `.bkp` e os CSVs têm
   nome, CPF e endereço de leitores dentro.
7. **O que a tela não pode fazer, ela diz.** Reindexar é ação do BibLivre e
   reiniciar o Tomcat é da máquina; os dois aparecem como próximos passos
   depois da carga.

### Contrato de API

```
GET    /api/migracao                   estado (fase, passos, relatório, artefatos)
GET    /api/migracao/versao            só o contador, para o laço
POST   /api/migracao/backup            multipart: o .bkp
POST   /api/migracao/conferir          dispara o dry-run em segundo plano
POST   /api/migracao/executar          grava — exige confirmado=true
DELETE /api/migracao                   descarta a execução e apaga a pasta
GET    /api/migracao/arquivos/{nome}   baixa um arquivo de conferência
```

Uma execução por vez: um segundo disparo responde 409, em vez de gravar ids
sobrepostos na mesma base.
