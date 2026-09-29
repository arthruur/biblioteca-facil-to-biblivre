# Spec de UI/UX

Contrato das telas. Descreve o que cada uma precisa mostrar, em que estado ela
pode estar e por quê — não o CSS que a implementação usa. São quatro frentes,
em quatro ritmos diferentes: as seções 1 a 8 são da **catalogação por ISBN**, o
trabalho de todo dia; a 9 é da **migração de acervo legado**, o trabalho do
primeiro dia; a 10 é da **circulação** — o balcão, que é o trabalho de toda
hora; e a 11 é da **manutenção**, que é o que sobrava fora do app.

A ordem das seções é histórica, não de importância: a circulação chegou por
último e é a frente que mais gente usa por dia. As regras da seção 7 valem
para todas — com uma exceção declarada, que é a circulação no celular e está
explicada no fim daquela seção.

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

### Sessão do operador

Circulação e manutenção exigem operador identificado. O token volta no corpo
do login e o cliente o reenvia em **`X-Sessao`**, na mesma mecânica do
`X-Dispositivo` da captura. Ele vive só na memória do servidor: reiniciar o
processo desloga todo mundo, e isso é o preço de não guardar credencial.

| Método | Rota | Uso |
|---|---|---|
| `POST` | `/api/sessao` `{usuario, senha}` | entra; `{token, operador, expira_em, senha_padrao}` · **401** quando não confere |
| `GET` | `/api/sessao` | `{operador, criada_em, visto_em, expira_em}` · **401** |
| `DELETE` | `/api/sessao` | sai; `{ok:true}` **sempre** — sair de uma sessão morta não é erro |

`operador` é `{id, login, nome, employee, admin, permissoes, pode_emprestar}`.
O `id` é o `logins.id` de verdade, e é ele que vai para `lendings.created_by`.
Usuário inexistente e senha errada dão a **mesma** resposta, de propósito.
Banco fora do ar não vira 401 — vira **503 `sem_banco`**, porque mandar o
balcão redigitar a senha dez vezes por causa do Postgres é o pior conselho
possível.

### Circulação — todas exigem `X-Sessao`

| Método | Rota | Uso |
|---|---|---|
| `GET` | `/api/circulacao/resolver?codigo=` | `{tipo: tombo\|isbn\|leitor\|desconhecido, …}` — **200 sempre** |
| `GET` | `/api/circulacao/leitores?busca=&limite=` | `{leitores, total, busca}` |
| `GET` | `/api/circulacao/leitor/{user_id}` | `{leitor, situacao, emprestimos}` · **404** |
| `GET` | `/api/circulacao/exemplar/{holding_id}` | `{exemplar, obra, emprestimo\|null}` · **404** |
| `GET` | `/api/circulacao/pendencias?tipo=&limite=` | `{itens, total}`; `tipo` = `atrasados` \| `hoje` \| `abertos` |
| `POST` | `/api/circulacao/emprestimos` `{holding_id, user_id, forcar_avisos?, previsto_para?}` | **201** `{emprestimo, avisos}` · **409** · **400** |
| `POST` | `/api/circulacao/devolucoes` `{holding_id?, lending_id?}` | `{devolucao, multa\|null, reserva\|null, atraso_dias}` · **409** |
| `POST` | `/api/circulacao/renovacoes` `{lending_id}` | `{emprestimo, avisos, atraso_dias}` · **409** |

Três coisas que o contrato garante e a tela pode assumir:

- **o operador nunca vem no corpo.** Ele sai do `X-Sessao`; corpo que mandar
  `operador_id` é ignorado. É o que faz `created_by` valer alguma coisa;
- **consulta também pede sessão.** Inclusive os `GET`: a ficha do leitor é
  dado pessoal (nome, multas, o histórico do que a pessoa leu) e a rede é o
  wi-fi da biblioteca. O efeito colateral é bem-vindo — é o 401 num `GET`
  barato que faz a tela descobrir que a sessão expirou **antes** de alguém
  estar com o livro na mão;
- **código não reconhecido não é erro HTTP.** `resolver` devolve 200 com
  `tipo: "desconhecido"`, porque errar a leitura do código de barras é rotina
  de balcão, não falha de sistema.

### As chaves que o balcão devolve

O §4.2 do plano fixou as rotas e o primeiro nível das respostas, mas não os
nomes dos campos dentro de cada dicionário — e por isso as duas telas leem
defensivamente (`tombo` ou `accession_number`, `titulo` ou `title`, `nome` ou
`name`). Ficam registrados aqui os nomes que o servidor **de fato** devolve
hoje, para que essa leitura defensiva possa encolher:

| Objeto | Chaves |
|---|---|
| `exemplar` | `holding_id`, `record_id`, `tombo`, `disponibilidade`, `database`, `volume`, `emprestado` |
| `obra` | `record_id`, `titulo`, `autor` |
| `emprestimo` (em aberto) | `lending_id`, `user_id`, `leitor`, `previsto_para`, `emprestado_em`, `renovacao`, `atraso_dias`, `atrasado` |
| `emprestimo` (recém-gravado) | o acima mais `id`, `holding_id`, `tombo`, `titulo`, `autor`, `operador_id` |
| `leitor` | `id` (= `user_id`), `nome`, `matricula`, `status`, `tipo_id`, `tipo`, `limite`, `dias_prazo`, `multa_por_dia` |
| `situacao` | `abertos`, `atrasados`, `multas`, `multas_qtd`, `limite`, `dias_prazo`, `status`, `pode_levar` |
| item de `pendencias` | `lending_id`, `holding_id`, `record_id`, `tombo`, `titulo`, `autor`, `user_id`, `leitor`, `matricula`, `previsto_para`, `emprestado_em`, `renovacao`, `atraso_dias`, `atrasado`, `multa_estimada` |

Datas vão sempre como `AAAA-MM-DD` (ou carimbo ISO, nos campos `_em`), nunca
formatadas: formatar é da tela, e `Date` no navegador muda o dia por fuso.
`matricula` é o `users.id` com zeros à esquerda, como o BibLivre imprime na
carteirinha. A `multa_estimada` das pendências é **estimativa**:
`lending_fines` só ganha linha na devolução.

### Manutenção — todas exigem `X-Sessao`

| Método | Rota | Uso |
|---|---|---|
| `GET` | `/api/manutencao` | `{biblivre:{configurado,url,conectado,erro}, reindex:{…}, backup:{…}}` |
| `POST` | `/api/manutencao/biblivre` `{url, usuario, senha}` | `{configurado, url, conectado, erro}` — **nunca** devolve a senha |
| `POST` | `/api/manutencao/reindexar` | `{iniciado:true}` · **409** |
| `GET` | `/api/manutencao/reindexar` | `{rodando, atual, total, pct, erro}` — **200 sempre** |
| `POST` | `/api/manutencao/caches` | `{ok, detalhe, aviso}` · **409** |
| `POST` | `/api/manutencao/conferencia` | `{checagens, resumo}` · **503** |
| `POST` | `/api/manutencao/backup` `{tipo:"full"}` | `{iniciado:true, id}` · **409** |
| `GET` | `/api/manutencao/backup` | `{rodando, id, atual, total, pct, erro, url_download, iniciado_em, terminado_em}` |

Os dois `GET` de progresso **nunca** respondem 409: falha de consulta volta
como `erro` dentro do corpo, com o último valor conhecido. Perder um polling
não pode apagar a barra de progresso nem fazer parecer que o trabalho morreu.

### O envelope de erro

Um só, para as três frentes acima, e plano de propósito — a tela lê
`dados.codigo` e `dados.mensagem` direto, sem desembrulhar o `{"detail": …}`
que o FastAPI produziria:

```json
{
  "status": "erro",
  "codigo": "exemplar_emprestado",
  "mensagem": "Exemplar já está emprestado.",
  "impedimentos": ["exemplar_emprestado"],
  "avisos": [],
  "impedimentos_detalhe": [
    {"codigo": "exemplar_emprestado",
     "mensagem": "Exemplar já está emprestado.",
     "detalhe": "com outro leitor desde 12/08/2026"}
  ],
  "avisos_detalhe": []
}
```

`impedimentos` e `avisos` são **códigos**; a frase pronta e o detalhe vão em
`*_detalhe`. `confirmavel: true` aparece **só** quando não há impedimento e
existe aviso — é o único sinal que autoriza a tela a oferecer "emprestar
assim mesmo".

| Código | Status | Quando |
|---|---|---|
| os 13 do vocabulário de circulação (§10) | 409 | recusa de balcão |
| `sem_operador` | 401 | sem `X-Sessao`, token expirado ou senha errada |
| `sem_banco` | 503 | não deu para abrir a conexão, ou o Postgres recusou a operação |
| `pedido_incompleto` | 400 | corpo malformado (`holding_id` e `lending_id` nulos, por exemplo) |
| `biblivre_nao_configurado` | 409 | manutenção sem URL/credencial de admin |
| `biblivre_indisponivel` | 409 | manutenção configurada, mas o Tomcat não respondeu |
| `falha_inesperada` | 500 | o resto — frase em português, **sem** stack no corpo |

Os três últimos e o `pedido_incompleto` ficam **fora** do vocabulário de
impedimento de propósito: "a URL do Tomcat está errada" não é motivo para o
leitor não levar o livro, e misturar os dois faria a tela do balcão dizer
"não pode levar" para um defeito de configuração.

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

### A exceção declarada: na circulação, o celular espera

A regra 1 vale para a **captura**, e só para ela. Na circulação o celular
**espera a resposta do servidor** entre um bipe e o próximo. É exceção
consciente, não descuido, e o desenho dela está na §10.

O motivo é a diferença entre os dois erros. Na captura, bipe é rascunho: o
lote é volátil, a fila é revisada por gente sentada e um bipe perdido se
resolve bipando de novo — bloquear ali custaria o ritmo, que é o produto. Na
circulação não existe rascunho: a operação grava em `lendings` na hora, e
dizer "levou" antes do commit é mentir para quem está na frente do balcão. O
livro sai da biblioteca com a tela dizendo uma coisa e o banco dizendo outra,
e a diferença só aparece semanas depois — quando alguém cobra a devolução de
quem nunca levou, ou não cobra de quem levou.

Na prática, na circulação: cada bipe passa por "Gravando…", leitura nova é
ignorada enquanto há operação em curso ou decisão aberta, e o fim é sempre uma
das quatro respostas da §10 — inclusive a quarta, "não deu para confirmar",
para quando a rede cai depois do envio.

O que **não** muda: a captura continua sem bloquear nada, e nenhuma tela pode
usar esta exceção como licença para pendurar o celular esperando rede fora do
balcão.

---

## 8. Vocabulário

Um termo por conceito, em toda a interface e no código:

| Termo | É | Não é |
|---|---|---|
| **Lote** | a bandeja do scanner, volátil | "carrinho" (nome antigo, só nos aliases de API) |
| **Execução** | uma migração de acervo legado, do `.bkp` ao commit | "importação", "job" |
| **Conferência** (da migração) | o dry-run que não toca no banco, antes de gravar | "prévia", "simulação" |
| **Conferência** (da base) | as 26 checagens de leitura depois de uma carga (§11) | "validação", "diagnóstico" |
| **Fila** | trabalho pendente de revisão, em disco | "lista", "pendências" |
| **Obra** | registro bibliográfico (`biblio_records`) | "livro", "título" |
| **Exemplar** | cópia física (`biblio_holdings`) | "cópia", "volume" |
| **Tombo** | `accession_number`, `Bib.2026.687` | "código", "registro" — e **não** é o número que a etiqueta imprime na barra (esse é o `biblio_holdings.id` com zeros) |
| **Destino** | obra nova ou +N exemplares | — |
| **Acervo** | o que já está no BibLivre | "base", "catálogo" |
| **Leitor** | a pessoa que empresta (`users`) | "usuário", "cliente", "aluno" |
| **Operador** | quem está no balcão, autenticado contra `logins`; vira `lendings.created_by` | "usuário", "admin" |
| **Sessão** | o token do operador, em memória do servidor, enviado em `X-Sessao` | "login" (login é a linha em `logins`) |
| **Empréstimo em aberto** | linha em `lendings` com `return_date IS NULL` | um estado do exemplar — `availability` responde outra pergunta |
| **Impedimento** | motivo que **barra** a operação (409) | "erro" |
| **Aviso** | motivo que **passa** com confirmação explícita e `forcar_avisos` | "alerta", "warning" |
| **Atraso** | empréstimo em aberto com `expected_return_date` vencida | "pendência" (pendência inclui multa não paga) |

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

---

## 10. Circulação — `/circulacao`

### Objetivo

Emprestar, devolver e renovar sem abrir o BibLivre. É a frente que mais gente
usa por dia: a catalogação acontece quando chega livro novo, a migração
acontece uma vez, e o balcão acontece toda hora em que a biblioteca está
aberta.

O que grava é o **PostgreSQL do próprio BibLivre**, reproduzindo o
`LendingBO` — sem tabela nova, sem schema paralelo. Um empréstimo feito aqui
tem de ser indistinguível de um feito pela tela do BibLivre, porque o BibLivre
continua instalado, pode estar aberto na mesma base no PC ao lado, e o `.b5bz`
continua sendo a verdade da biblioteca. As regras reproduzidas e o que foi
lido no fonte estão em [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).

Como a captura, a circulação tem duas telas para duas posturas — e a mesma
rota (`/circulacao`) resolve para uma ou para a outra conforme o aparelho:

| | Celular (`/circulacao`) | PC (`/circulacao`) |
|---|---|---|
| Postura | de pé no balcão, livro e leitor na frente | sentado, teclado e leitor USB |
| Gesto | bipar | bipar e **clicar** |
| Ritmo | um leitor por vez, com fila atrás | um atendimento por vez, com tempo de olhar |
| Erro caro | dizer "levou" sem ter gravado | emprestar para o leitor errado |
| Escopo | emprestar e devolver | + renovar, ficha completa, histórico e painel de atrasados |

### Quem decide o quê

Uma linha, e ela sustenta as duas telas: **a tela traduz, o servidor decide.**

| Pergunta | Quem responde |
|---|---|
| O que foi bipado? | `GET /api/circulacao/resolver` — só o banco sabe se `2019000123` é tombo, matrícula ou nada |
| Este leitor pode levar este exemplar? | o servidor, em `situacao.pode_levar` e no corpo do 409 |
| Como isso se diz em português? | a tela |

O classificador local do scanner (`features/scanner/codigos.js`) existe **só**
para o visor não ficar mudo entre o bipe e a resposta: ele arrisca "isso
parece um tombo" e nada mais. Nenhuma decisão de circulação sai dele — duas
fontes de verdade, uma no celular e outra no banco, seriam bug garantido, e do
tipo que só aparece no balcão.

### O empréstimo tem duas etapas; a devolução, uma

Empréstimo precisa de **duas** identidades, e por isso é o único fluxo com
etapa: primeiro o leitor (carteirinha, número ou busca por nome), depois o
exemplar. A ordem é essa porque o leitor é quem está de pé esperando:
identificado uma vez, ele fica fixo no topo da tela e os livros entram em
sequência, quantos ele levar.

```
EMPRESTAR                                    DEVOLVER
 1. leitor  ──bipa a carteirinha──┐            1. bipa o livro
    ou busca por nome             │               └── fecha o empréstimo e diz
 2. livro   ──bipa a etiqueta─────▼                   o que apareceu: multa,
    ou o ISBN da capa      grava e confirma           atraso, reserva pendente
```

Devolução é uma etapa porque o exemplar já sabe de quem é: o empréstimo em
aberto tem `user_id`. Pedir o leitor ali seria digitar o que o banco já tem.

### O caminho do ISBN é de primeira classe

Boa parte do acervo migrado **não tem etiqueta impressa** — os 16.251 tombos
existem no banco, nem todos no papel. Então bipar o código de barras da
**capa** devolve a obra e a lista de exemplares dela, com o estado de cada um,
e o operador escolhe qual está na mão dele.

Isso não é plano B: é o caminho normal de boa parte da estante, e por isso o
exemplar que não serve **continua na lista**, desabilitado e com o motivo ao
lado. Sumir com ele faria alguém procurar na estante um livro que a tela
escondeu.

### As quatro respostas do celular — e por que ele espera

Esta tela é a **exceção declarada à regra 1 da §7** (ver o fim da §7). Cada
bipe passa por "Gravando…" e termina numa destas quatro, com cor, frase e som
próprios:

| Resposta | Significa | Como aparece |
|---|---|---|
| **Confirmado** (verde) | gravou; o livro pode sair | tombo, título e "devolver até"; duas notas subindo |
| **Recusado** (vermelho) | não gravou, e o motivo é de balcão | a frase do impedimento e o que fazer agora; duas notas graves |
| **Aviso** (âmbar) | passou, mas com informação que o atendente precisa ver | multa apurada, reserva pendente, livro que já estava na estante |
| **Não deu para confirmar** (neutro) | a rede caiu **depois** do envio | "Não diga que levou; confira no PC antes de repetir" |

A quarta existe porque as três primeiras seriam mentira nesse caso: o pedido
pode ter commitado do outro lado. Nem verde nem vermelho — é o único estado
em que a tela admite não saber.

Os sons são **diferentes** do bipe de 880 Hz do scanner, de propósito: aquele
diz "li a etiqueta", estes dizem "o servidor gravou" ou "o servidor recusou".
Iguais, fariam o operador guardar o livro ao ouvir "ok" sem que nada tivesse
sido gravado.

Duas cores de modo, que não se misturam com as de resposta: **EMPRESTAR é
roxo, DEVOLVER é azul**, os dois no topo, sempre visíveis. Se DEVOLVER fosse
verde, a tela pareceria uma confirmação permanente e o verde deixaria de
significar "gravou".

### As três regiões do PC

O PC não bipa para gravar — ele bipa para **mostrar**, e a ação é sempre um
clique explícito. Quem está sentado vê a ficha inteira (o atraso, a multa, o
histórico) e a decisão é dele.

1. **Barra de comando, sempre com foco** — um campo só, que aceita tombo, ISBN
   ou número de leitor. O leitor de código de barras USB é, para o navegador,
   um teclado que digita rápido e aperta Enter; então qualquer tecla
   imprimível pressionada fora de um campo devolve o foco à barra **e entra
   nela** — sem isso o primeiro dígito do tombo se perderia depois de um
   clique em botão. `Esc` limpa o atendimento.
2. **Atendimento** — o leitor corrente em ficha compacta, com os selos de
   situação; o exemplar recém-bipado "em mãos", com o estado real e a ação
   explícita (emprestado oferece Devolver, Renovar ou ver quem está com ele;
   livre com leitor na tela oferece "Emprestar para tal pessoa"; livre sem
   leitor diz que falta identificar e segura o exemplar até o leitor
   aparecer); e o recibo do turno ("Neste atendimento": saiu, voltou,
   renovou, com hora).
3. **Ficha do leitor / Atrasos** — as duas dividem a coluna larga e a aba
   troca sozinha para a ficha quando um leitor é identificado. A ficha tem os
   empréstimos em aberto com a data prevista (linha em vermelho quando
   vencida), ações por item e o bloco de multas quando existe. O painel de
   atrasos lista os vencidos com busca e ordenação, e cada linha abre a ficha
   ou registra a devolução.

   A tela tem também o lugar do **histórico** (o que o leitor já devolveu),
   paginado, e ele está vazio: `GET /api/circulacao/leitor/{id}` hoje devolve
   **só os empréstimos em aberto** (`return_date IS NULL`). Ou a rota passa a
   devolver os devolvidos — com paginação no servidor, porque leitor antigo
   tem centenas —, ou a tela deixa de prometer a seção. Está na lista de
   pendências do [ROADMAP.md](ROADMAP.md).

O painel de atrasos se atualiza a cada 15s, pelo mesmo padrão de contador de
versão que a fila usa: frequente o bastante para refletir uma devolução feita
no PC ao lado, leve o bastante para não pesar sobre a mesma conexão que
atende os celulares bipando.

### Impedimento barra; aviso passa com confirmação

O vocabulário é fechado — 13 códigos — e a divisão entre os dois grupos não
foi escolha de gosto: **impedimento é exatamente o que o `LendingBO` do
BibLivre recusa**, mais os erros de identidade e a corrida.

| Código | O que a tela diz | O que fazer agora |
|---|---|---|
| `leitor_nao_encontrado` | Não achei esse leitor no cadastro. | Confira o número da carteirinha ou procure pelo nome. |
| `leitor_inativo` | O cadastro deste leitor está inativo. | Ele precisa ser reativado no BibLivre antes de levar livro. |
| `leitor_bloqueado` | Este leitor está bloqueado. | Só a biblioteca libera, pelo BibLivre. |
| `limite_atingido` | Já está com o número máximo de livros permitido. | Devolva um para poder levar outro. |
| `exemplar_nao_encontrado` | Este tombo não existe no acervo. | Confira a etiqueta, ou bipe o código de barras da capa. |
| `exemplar_emprestado` | Este exemplar já está emprestado para outra pessoa. | Se ele está na sua mão, troque para DEVOLVER e bipe de novo. |
| `exemplar_indisponivel` | Este exemplar não pode sair da biblioteca. | Está marcado como consulta local, em encadernação ou baixado. |
| `conflito` | Este exemplar mudou de estado agora há pouco. | Alguém pode ter mexido nele pelo BibLivre. Confira antes de repetir. |
| `leitor_com_atraso` **(aviso)** | Este leitor tem livro atrasado. | Precisa devolver o que está atrasado antes de levar outro. |
| `multa_em_aberto` **(aviso)** | Há multa em aberto no nome deste leitor. | Acerte a multa na biblioteca antes de emprestar de novo. |
| `reserva_de_outro_leitor` **(aviso)** | Este livro está reservado para outro leitor. | Separe o exemplar para quem reservou. |
| `sem_operador` | Sua sessão expirou. | Entre de novo para continuar emprestando. |
| `sem_banco` | Sem conexão com o acervo — nada foi gravado. | Avise quem cuida do servidor antes de continuar no papel. |

As três marcadas como **aviso** passam com `forcar_avisos: true`, e é a única
coisa que `forcar_avisos` faz. Elas avisam em vez de barrar porque o BibLivre
**não checa nenhuma das três**: barrar deixaria o app mais rígido que a tela
do PC ao lado — o balcão veria "não pode" e o BibLivre emprestaria o mesmo
livro no clique seguinte, o que é pior do que passar com confirmação.
`reserva_de_outro_leitor` é acréscimo nosso (o BibLivre nem consulta reserva
ao emprestar) e por isso jamais barra.

A confirmação precisa dizer **o que** está sendo ignorado, nominalmente, e o
registro do atendimento repete isso depois. "Emprestar assim mesmo?" sem a
lista treina o operador a clicar sim.

Nenhuma frase da tela menciona status HTTP, nome de tabela ou código interno.
Código que a tela não conhece cai numa frase honesta ("Não deu para concluir
esta operação — confira no PC antes de repetir"), nunca no identificador cru.
As frases do PC são as mesmas em conteúdo e mais longas em forma: ali cabe
explicação, no celular não.

### Estados que as telas cobrem

| # | Estado | O que a tela mostra |
|---|---|---|
| 1 | verificando a sessão | o "carregando", sem piscar o login |
| 2 | sem operador | o login sozinho na tela; nada mais é acionável |
| 3 | sem conexão com o acervo | faixa própria, barra e ações **desabilitadas**, com o motivo |
| 4 | esperando o leitor (etapa 1) | busca por nome disponível; livro bipado aqui vira aviso, não erro |
| 5 | leitor barrado | painel com o motivo, e **não** deixa bipar livro |
| 6 | leitor fixo | nome, número, tipo e situação (em aberto · atrasados · multa · limite) |
| 7 | gravando | "Gravando…", leitura nova ignorada |
| 8 | confirmado / recusado / aviso / não deu para confirmar | as quatro respostas acima |
| 9 | decisão aberta | escolher exemplar (ISBN), confirmar avisos, confirmar troca de leitor |
| 10 | devolvido com multa | o valor apurado e os dias de atraso |
| 11 | devolvido com reserva pendente | "separe este livro", e para quem |
| 12 | livro que não estava emprestado | aviso âmbar ("já estava na estante"), **não** erro vermelho |
| 13 | carteirinha bipada no modo devolver | aviso |
| 14 | código não reconhecido | "não reconheci isto", com o texto lido |
| 15 | câmera negada | a saída explícita: digitar o tombo ou o ISBN |
| 16 | sessão expirada no meio | fecha a câmera e volta ao login |
| 17 | exemplar mudou de estado (`conflito`) | tom próprio, âmbar e não vermelho — não é erro de quem está no balcão |

### Garantias (além das da §7, que continuam valendo)

1. **Ninguém grava sem operador identificado.** O `operador_id` sai da sessão,
   nunca do corpo do pedido, e é ele que vai para `lendings.created_by`. Sem
   sessão, o pedido é recusado antes de tocar o banco.
2. **No celular o bipe espera a confirmação** (exceção declarada à regra 1 da
   §7). No PC **bipar nunca grava**: a ação é sempre um clique.
3. **Uma operação, uma transação, um commit.** A trava é `SELECT … FOR UPDATE`
   no exemplar e a revalidação acontece **dentro** da transação, porque o
   BibLivre pode estar aberto na mesma base. Recusa faz `ROLLBACK`, não
   commit: meia operação gravada é pior que nenhuma.
4. **Aviso só passa com confirmação que diz o que está sendo ignorado.**
5. **Sem banco, a tela desabilita e explica** — nunca degrada em silêncio. É a
   regra 3 da §7 aplicada ao balcão.
6. **`conflito` tem tom próprio.** Não é erro do operador: é o outro sistema
   na mesma base. A tela manda conferir, não repetir.
7. **A tela diz o que ela não faz.** Cadastrar ou reativar leitor, receber
   multa, administrar a fila de reservas e catalogar continuam no BibLivre, e
   a tela nomeia isso na hora em que o caso aparece, em vez de oferecer um
   botão morto.

### O que a circulação **não** faz, e por quê

Recorte deliberado: o balcão é 90% do uso diário e é onde a tela do BibLivre
pesa; o resto é uso ocasional, de gente sentada, e reescrever aquilo seria
refazer um sistema inteiro para ganhar pouco.

| Fica no BibLivre | Por quê |
|---|---|
| Cadastro, edição, reativação e desbloqueio de leitor | é formulário de gente sentada, com dado pessoal e validação própria; é o primeiro candidato à fase 2 |
| Receber/quitar multa | a tela **mostra** o valor apurado; receber dinheiro é outra operação, com `payment_date` e responsabilidade de caixa |
| Fila de reservas | a devolução avisa "separe para tal leitor", mas administrar a fila não tem rota aqui |
| Catalogação avançada e edição de MARC | é a razão de o BibLivre existir |
| Etiquetas, cartões, relatórios, permissões, tipos de usuário, Z39.50 | uso ocasional, de gente sentada |

---

## 11. Manutenção

### Objetivo

Fazer, de dentro do app, os passos que até aqui terminavam em instrução de
papel: **reindexar** a base bibliográfica, **derrubar os caches** estáticos,
**conferir** a base depois de uma carga e **gerar o `.b5bz`**. São as quatro
coisas que o roteiro de importação mandava fazer "no BibLivre, depois",
e que por isso eram as mais fáceis de esquecer — um catálogo de 14.866 obras
que existe e não aparece na busca é um acervo perdido, e ninguém descobre isso
sem procurar um título de cor.

> **Estado: as rotas existem, a tela ainda não.** Os quatro botões estão
> implementados e testados do lado do servidor (`biblio.biblivre.web`,
> `biblio.biblivre.verificacao` e o router `/api/manutencao`), e nenhuma tela
> os consome ainda — hoje o caminho é a própria API ou o `scripts/conferir.py`.
> A tela é o próximo passo, e esta seção é o contrato que ela vai cumprir.

### Duas decisões que a tela precisa respeitar

**1. Reindex e backup disparam e voltam; o progresso é outra rota.** São
minutos de trabalho do lado do Tomcat — o `IndexingBO.reindex` varre a
`biblio_records` em lotes de 30, e o backup roda um `pg_dump`. A tela precisa
de barra de progresso, não de requisição pendurada; quem segura a espera é uma
thread dentro do pacote `web`.

Detalhe que a barra tem de tratar sem parecer defeito: **durante o reindex o
`atual` começa em zero**, porque o `clearIndexes` roda antes de reconstruir. Ou
seja, por alguns segundos o índice está *vazio* e a busca do BibLivre não acha
nada. Isso é normal e a tela deve dizer, em vez de deixar o bibliotecário
descobrir sozinho no pior momento.

**2. A senha do admin do BibLivre segue a regra da senha do Postgres:** entra
em memória, nunca vai para disco e **nunca volta na resposta**. Ela viaja no
corpo do POST, nunca na query string, para não cair no access log do Tomcat.

### As quatro ações

| Ação | Como é feita | O que a tela precisa mostrar |
|---|---|---|
| **Reindexar** | HTTP contra o próprio BibLivre (`administration.indexing`, ações `reindex` e `progress`), logado como admin | progresso, o aviso de que o índice fica vazio no meio, e uma por vez (a segunda chamada é 409 — o BibLivre tem lock por tipo de registro e faria a segunda voltar calada, o que pareceria sucesso) |
| **Limpar caches** | HTTP (`administration.translations`, ação `list`, que chama `Translations.reset`) | o que foi limpo (traduções) **e o que não foi**: campo de leitor continua exigindo restart do Tomcat |
| **Conferir a base** | SQL puro, só leitura, contra o Postgres | as 26 checagens com valor × esperado, e o resumo (`ok` / falhas / não verificadas) |
| **Gerar backup** | HTTP (`administration.backup`: `prepare` → `backup` → `progress`) | progresso e a URL de download do `.b5bz`, **com o aviso do que tem dentro** |

Por que HTTP e não SQL, se todo o resto do projeto é SQL: inserir em
`biblio_records` por SQL não preenche `biblio_idx_*`, e reproduzir o indexador
significaria copiar a tokenização Java do `IndexingBO` — índice errado falha
**em silêncio**, que é a pior superfície possível para uma reimplementação.
Mais barato e mais correto é mandar o BibLivre indexar. O mesmo raciocínio
vale para o backup: o `.b5bz` é um `pg_dump` empacotado pelo `BackupBO`, e um
formato reimplementado por fora seria um restore que ninguém testou.

### O restart do Tomcat não morreu

Procuramos no fonte inteiro: nenhuma ação alcançável por HTTP derruba o cache
de **campos de leitor** sem destruir a instalação (os três chamadores de
`StaticBO.resetCache()` são restore, importação do Biblivre 3 e remoção de
schema). Campo criado em `users_fields` por SQL continua exigindo **reiniciar o
Tomcat** para aparecer na tela do BibLivre.

O botão faz o que dá — as traduções — e **diz na resposta** que os campos de
leitor ficaram de fora. Um botão que promete mais do que cumpre é pior que
nenhum botão: quem confia nele reinicia o Tomcat mais tarde, no meio do
expediente, sem saber por quê.

### A conferência

26 checagens em três famílias. Ela é **só leitura**: nenhum `INSERT`, nenhum
`UPDATE`, nenhum commit.

| Família | Quantas | O que responde |
|---|---|---|
| Índice | 1 | obras que não têm linha em `biblio_idx_fields` — a única resposta objetiva para "o reindex funcionou?" |
| Sequences | 4 | `biblio_records`, `biblio_holdings`, `lendings` e `users`: a sequence está à frente do `max(id)`? |
| Integridade | 12 | exemplar órfão, obra sem exemplar, tombo duplicado ou em branco, MARC vazio, base divergente, chave fora de `users_fields`, empréstimo sem exemplar ou sem leitor, multa sem empréstimo, reserva sem vínculo, exemplar com dois empréstimos em aberto |
| Informativas | 9 | contagens de referência, tombos por ano e prefixo em vigor — relatam, nunca barram |

Três estados por checagem, e o terceiro é o que a tela não pode esconder:

| `ok` | Significa | Como aparece |
|---|---|---|
| `true` | passou | verde, com valor × esperado |
| `false` | falhou | vermelho, com uma amostra de até 10 exemplos |
| `null` | **não deu para verificar** (tabela ausente, sem `GRANT`) | âmbar, com o motivo — nunca como "passou" |

A checagem de **sequences** é bloqueante antes de liberar a circulação, e o
porquê está em [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md): a migração
grava id explícito, id explícito não avança a sequence, e o primeiro
empréstimo feito pelo app estoura chave duplicada — no balcão, com fila.

É `POST`, e não `GET`, porque custa uma dezena de varreduras na base inteira:
não é coisa para laço de tela.

### O backup leva dado pessoal

O `.b5bz` é um dump completo: `users_values` guarda CPF, RG, nome da mãe,
endereço e telefone dos leitores, e o arquivo leva tudo consigo, com URL de
download. Quem apertar o botão precisa ler isso antes, e é por isso que a
manutenção inteira exige operador identificado — inclusive os `GET`.

Efeito colateral aceito, que vale escrever para ninguém se surpreender: como
toda rota de manutenção exige sessão, e sessão exige a tabela `logins` no
Postgres, **uma instalação com o Postgres fora do ar não consegue disparar
reindex nem backup pela API**. O caminho de socorro continua sendo a tela do
próprio BibLivre.

### Custo do painel

Com o BibLivre configurado, `GET /api/manutencao` faz até três chamadas HTTP
ao Tomcat (estado, progresso do reindex, estado do backup) — só a primeira tem
cache curto dentro do pacote. Logo: **laço lento (10s ou mais) para o painel, e
laço rápido só nas rotas de progresso, e só enquanto `rodando` for `true`.**
