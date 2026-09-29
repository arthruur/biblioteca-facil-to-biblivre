# biblioteca-facil-to-biblivre

Ferramentas de gestão de acervo para bibliotecas que rodam **BibLivre 5**.

Três coisas que se apoiam no mesmo núcleo:

1. **Catalogação por ISBN** — bipar o código de barras no celular, revisar no PC
   e gravar no BibLivre, sem duplicar o que a biblioteca já tem.
2. **Migração de acervo legado** — trazer um acervo inteiro do *Biblioteca
   Fácil* para o BibLivre 5, pela mesma interface (`/migracao`) ou pelos CLIs.
   Executado e validado em campo: 14.880 obras, 16.251 exemplares, 2.743
   leitores e 19.592 empréstimos.
3. **Circulação** — emprestar, devolver, renovar e consultar no balcão, pelo
   celular (bipando) ou pelo PC, gravando no PostgreSQL do próprio BibLivre.
   Mais os passos de manutenção que antes eram instrução de papel: reindexar,
   limpar caches, conferir a base e gerar o `.b5bz`.

As três compartilham o mesmo núcleo e a mesma postura: o BibLivre **continua
instalado** e continua sendo a verdade. Este projeto tira do caminho o que a
tela dele torna penoso no dia a dia — não substitui o sistema.

> **Status:** migração completa e validada em campo
> (`docs/IMPORTACAO_BIBLIVRE.md`). Catalogação por ISBN em uso. Circulação e
> manutenção implementadas e cobertas por verificação offline, **ainda não
> exercitadas contra um BibLivre real** — a pauta desse primeiro teste está em
> `docs/ROADMAP.md`.

---

## 1) Como está organizado

```
apps/
  api/          FastAPI — só monta os routers, sem regra de negócio
  web/          React + Vite — as telas
packages/
  bf-legado/         biblio.legado      lê o .bkp do Biblioteca Fácil
  biblivre-client/   biblio.biblivre    fala com o PostgreSQL do BibLivre —
                                        e, na manutenção, por HTTP com ele
  catalogacao/       biblio.catalogacao ISBN, lote, fila, export
  migracao/          biblio.migracao    o pipeline do .bkp ao BibLivre
scripts/        CLIs finos por cima dos pacotes (dry-run por padrão)
tests/          verificação de fumaça, sem banco e sem rede
docs/           formato do .bkp, tabelas, importação, spec de UI, roadmap
```

O namespace Python é `biblio`, e a regra que atravessa os pacotes é: **nada
neles commita**. Toda função de gravação recebe a conexão e devolve o commit
para quem chamou, porque obras e exemplares precisam fechar na mesma transação
— não existe "gravou metade". Com a circulação essa regra ganhou a outra
metade: **uma operação de balcão é uma transação e um commit, e quem commita é
o router** — recusa faz `ROLLBACK`, porque uma recusa pode ter deixado trava
ou `UPDATE` no meio do caminho.

| Pacote | Responde por |
|---|---|
| `biblio.legado` | `bkp`, `tabela`, `consolidar` — o formato proprietário do sistema antigo |
| `biblio.biblivre` | `conexao`, `marc`, `obras`, `exemplares`, `acervo`, `leitores`, `circulacao` (carga), `emprestimo` (balcão), `operador` (sessão), `web` (HTTP com o BibLivre), `verificacao` (conferência) |
| `biblio.catalogacao` | `lookup`, `fila`, `export`, `ficha` (OCR), `config`, `cert` |
| `biblio.migracao` | `pipeline` (o que fazer, na ordem dos CLIs), `execucao` (uma por vez, em segundo plano, com estado persistido) |

---

## 2) Rodar

### Desenvolvimento (sem Docker)

O PostgreSQL do BibLivre já roda na máquina — o container nunca foi o banco,
só um empacotamento do servidor. Em desenvolvimento ele só acrescenta um
rebuild entre você e o efeito da linha que acabou de escrever.

```bash
pip install -r requirements.txt      # instala os 4 pacotes em modo editável
cp .env.example .env                 # host/senha do Postgres do BibLivre
python scripts/dev.py                # sobe API + Vite num terminal só
```

```
[api]  https://<IP-DO-PC>:8000   uvicorn --reload   reinicia ao salvar .py
[web]  https://<IP-DO-PC>:5173   vite              HMR no JSX/CSS
```

**Trabalhe pela 5173**: o Vite faz proxy de `/api` para o backend, então o
frontend recarrega em milissegundos, sem `npm run build`. A 8000 continua
servindo o bundle buildado quando ele existe — é o que a biblioteca usa.

| | |
|---|---|
| `python scripts/dev.py` | API com reload + Vite, Ctrl+C encerra os dois |
| `--so-api` | sem o dev server do Vite |
| `--sem-ssl` | HTTP em localhost (a câmera do celular não funciona) |
| `python scripts/servidor.py --reload` | só o backend, se preferir dois terminais |
| `python tests/verificar.py` | fumaça: sem banco, sem rede, sem câmera |

O `.env` da raiz é lido tanto pelo `docker compose` quanto pelo servidor local
(`biblio.biblivre.ambiente`), e **nunca sobrescreve** variável que já esteja no
ambiente. Sem senha do Postgres o app funciona igual, mas trata todo livro como
obra nova — e a tela diz isso, em vez de degradar em silêncio.

Duas coisas que o modo reload muda de propósito:

- a **subida mora no ciclo de vida da aplicação** (`biblio.api.main:ciclo`), não
  no processo que a lança — com reload quem serve é um subprocesso, e a fila
  reidratada no pai ficaria no pai;
- o **índice de ISBN é montado sob demanda** (`BIBLIO_SEM_INDICE=1`), no
  primeiro bipe. Pagar a varredura da `biblio_records` a cada save não se
  justifica.

HTTPS não é preciosismo: `getUserMedia` só funciona em contexto seguro, então
sem TLS não há câmera — e sem câmera não há scanner. O certificado é
autoassinado, nasce na primeira execução em `data/certs`, e o Vite reusa o
mesmo.

### Instalação na biblioteca (container)

É onde o Docker paga: embute Tesseract, OpenCV e o bundle já buildado numa
imagem só, sem depender do que está instalado na máquina.

```bash
docker compose up --build
# https://<IP-DO-PC>:8000            celular — escanear (aceite o certificado)
# https://<IP-DO-PC>:8000/fila       PC — revisar e exportar
# https://<IP-DO-PC>:8000/migracao   PC — trazer o acervo legado
# https://<IP-DO-PC>:8000/circulacao balcão — emprestar e devolver (celular e PC)
# https://<IP-DO-PC>:8000/docs       OpenAPI
```

O compose fala com o PostgreSQL do host via `host.docker.internal`. Numa
instalação com host, porta ou senha diferentes do default, sobrescreva no
`.env` (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`).

Sem container e sem reload (o mesmo que o container roda):

```bash
cd apps/web && npm install && npm run build && cd ../..
python scripts/servidor.py           # ou: biblio-servidor
```

---

## 3) Catalogação por ISBN

**Celular (`/`)** — scanner contínuo (ZXing, EAN-13), lote que acumula sem
pedir decisão nenhuma, ficha completa ao toque, quantidade de exemplares.
Código riscado cai num OCR da faixa de números logo abaixo das barras, validado
pelo dígito verificador.

**PC (`/fila`)** — sete indicadores, busca, filtro por situação, edição
embutida de 12 campos, ações em lote e export.

**A regra que sustenta o produto — dedup por ISBN:** antes de gerar qualquer
MARC, o ISBN é confrontado com o acervo já catalogado
(`biblio.biblivre.acervo` indexa o 020 $a de `biblio_records`, ~10.5 mil ISBNs
em menos de 1s, casando ISBN-10 com ISBN-13). Livro que já existe **não vira
ficha nova**: entra como exemplar a mais no `record_id` que já está lá. Sem
isso, reescanear a estante duplicaria o catálogo.

```
Celular (ZXing) --ISBN--> /api/lote --lookup--> Google Books → BrasilAPI → Open Library
                                    --acervo--> ISBN já catalogado?
                                                 ├── não → obra nova  (biblio_records + N holdings)
                                                 └── sim → só exemplar (N holdings no record_id existente)
PC /fila (revisão) --------> /api/fila/exportar-biblivre --> BibLivre 5
```

Para ligar a checagem é preciso dar ao servidor acesso ao Postgres do BibLivre.
No compose isso já vem configurado; rodando local, é pela tela `/fila`, por
`--db-senha`, ou por `PGPASSWORD` / `BIBLIVRE_DB_SENHA`:

```bash
python scripts/servidor.py --db-senha SUA_SENHA
```

Sem isso o app funciona igual, mas trata todo livro como obra nova — **e a tela
avisa disso** em vez de degradar em silêncio. A senha vive só na memória do
processo; nunca vai para disco.

Ver [docs/SPEC_UI.md](docs/SPEC_UI.md) para os estados que as telas cobrem e o
contrato das rotas.

---

## 4) Migração de acervo legado

O acervo inteiro do *Biblioteca Fácil* — obras, exemplares, leitores,
empréstimos, multas e reservas — entra no BibLivre 5 por dois caminhos, e os
dois chamam o mesmo código (`biblio.migracao`, sobre `biblio.legado` e
`biblio.biblivre`). O que muda é quem está na frente.

### Pela tela — `/migracao`

É o caminho de quem vai instalar numa biblioteca: nenhum terminal, nenhum
arquivo intermediário para carregar de um passo ao outro.

```
1. enviar o .bkp   arrasta o backup; o servidor extrai e lista as 16 tabelas
2. conferir        NÃO toca no banco — devolve o relatório inteiro:
                   obras, exemplares, leitores, empréstimos, descartes,
                   o que já existe no destino e o que barra a gravação
3. gravar          uma transação só, com confirmação explícita
```

O passo 2 existe porque o 3 não tem desfazer: é o mesmo dry-run que os CLIs
imprimem no terminal, em números na tela. Ele roda **sem senha do Postgres** —
o que depende do banco (contagens do destino, prefixo de tombo, base já
ocupada) aparece como aviso, em vez de o passo inteiro falhar.

Três coisas que a tela garante e que valem repetir:

- **Uma transação, do primeiro registro bibliográfico à última reserva.** Os
  CLIs commitam por passo porque entre um e outro havia uma pessoa lendo o
  relatório; aqui a decisão é tomada uma vez. Falhou no meio, não entrou nada.
- **Base ocupada barra a gravação.** Migração é carga de base nova; rodar por
  cima duplicaria o cadastro e colidiria ids. Existe a opção de prosseguir
  assim mesmo (o `--permitir-existentes` dos CLIs), e ela é a única marcada em
  âmbar na tela.
- **O relatório sobrevive a F5 e a restart** (`data/migracao/<id>/estado.json`),
  como a fila de revisão. Se o processo cair *durante* a gravação, a execução
  volta dizendo exatamente isso — daqui não dá para saber se a transação
  chegou a commitar, e fingir que dá seria pior.

O `.bkp` enviado e os CSVs gerados ficam em `data/migracao/<id>/` e têm nome,
CPF e endereço de leitores dentro. O botão **Descartar** apaga a pasta.

Depois de gravar sobravam dois passos fora do app: reindexar a base
bibliográfica e reiniciar o Tomcat. O **reindex virou botão** — o app pede ao
próprio BibLivre que indexe, por HTTP (ver a seção 5) —, e vale a mesma
recomendação de conferir a base antes de liberar o balcão
(`python scripts/conferir.py`). O **restart do Tomcat continua manual**, e não
por falta de tentativa: está verificado no fonte que nenhuma ação alcançável
por HTTP derruba o cache de campos de leitor sem destruir a instalação.

### Pelos CLIs

Continuam sendo a referência, e são o caminho de quem quer parar entre um passo
e outro ou automatizar:

```bash
python scripts/extrair_bkp.py backup.bkp saida/
python scripts/extrair_tabela.py saida/ --listar
python scripts/consolidar.py saida/ acervo_consolidado.csv
python scripts/gerar_marc.py acervo_consolidado.csv obras.mrc   # + exemplares.csv
python scripts/inserir_obras.py obras.mrc --executar            # → Reindexar
python scripts/inserir_exemplares.py exemplares.csv --executar
python scripts/inserir_leitores.py saida/ --executar            # → reinicie o Tomcat
python scripts/inserir_emprestimos.py saida/ --executar
```

Sem `--executar` é dry-run: o script relata exatamente o que faria e não escreve
nada. Os CLIs são casca fina — a lógica está em `biblio.legado` e
`biblio.biblivre`, e é a mesma que a tela usa.

Duas decisões que moldaram tudo, detalhadas em
[docs/IMPORTACAO_BIBLIVRE.md](docs/IMPORTACAO_BIBLIVRE.md):

- **Um registro bibliográfico por obra, não por exemplar.** A importação por
  arquivo do BibLivre só cria registros bibliográficos, nunca exemplares, e
  empréstimo é feito contra exemplar. Importar 1:1 não criaria exemplar nenhum.
- **O agrupamento é por conteúdo, nunca por ISBN.** No acervo antigo o ISBN era
  digitado à mão: três livros diferentes da mesma editora dividiam o mesmo
  número. ISBN entra no registro (020), mas não na chave.

---

## 5) Circulação — o balcão

Emprestar, devolver, renovar e consultar sem abrir o BibLivre. É a frente que
mais gente usa por dia: catalogação acontece quando chega livro novo, migração
acontece uma vez, e o balcão acontece toda hora em que a biblioteca está
aberta — e é exatamente onde a tela do BibLivre pesa mais.

**Celular (`/circulacao`)** — dois modos no topo, EMPRESTAR e DEVOLVER. Empréstimo
é o único fluxo com duas etapas, porque precisa de duas identidades: bipa a
carteirinha (ou busca pelo nome), o leitor fica fixo no topo, e os livros
entram em sequência. Devolução é uma etapa: o exemplar já sabe de quem é.

**PC (`/circulacao`)** — uma barra de comando só, sempre com foco, que aceita
tombo, ISBN ou número de leitor; o leitor de código de barras USB é, para o
navegador, um teclado que digita rápido e aperta Enter. Aqui **bipar nunca
grava**: a tela mostra o exemplar "em mãos" com o estado real e oferece a ação
explícita. Mais a ficha completa do leitor (empréstimos em aberto, multas,
histórico) e o painel de atrasados do dia.

**Aqui o celular espera** — e é exceção declarada à regra de que a tela do
celular nunca bloqueia. Na captura, bipe é rascunho e o servidor reconcilia
depois. No balcão não existe rascunho: dizer "levou" antes do commit é mentir
para quem está na frente. Cada bipe passa por "Gravando…" e termina em
confirmação, recusa, aviso — ou "não deu para confirmar", quando a rede cai
depois do envio e a tela admite não saber.

**Grava no PostgreSQL do próprio BibLivre, reproduzindo o `LendingBO`.** Nada
de tabela nova, nada de schema paralelo: um empréstimo feito aqui tem de ser
indistinguível de um feito pela tela do BibLivre, porque ele continua
instalado, pode estar aberto na mesma base no PC ao lado, e o `.b5bz` continua
sendo a verdade da biblioteca. Daí três invariantes:

- **uma operação, uma transação, um commit** — com `SELECT … FOR UPDATE` no
  exemplar e revalidação **dentro** da transação, porque entre consultar e
  clicar o livro pode ter saído pela tela do outro sistema;
- **`created_by` é o operador de verdade** — o app autentica contra a tabela
  `logins` do próprio BibLivre (SHA-1 + Base64, como ele faz) e usa o
  `logins.id` real. Não inventamos cadastro de usuário, e é também o mínimo de
  barreira que o recurso exige: sem login, qualquer celular no wi-fi da
  biblioteca registraria empréstimo;
- **impedimento barra, aviso passa com confirmação.** Os que barram são
  exatamente os que o `LendingBO` recusa; atraso, multa em aberto e reserva de
  terceiro apenas **avisam**, porque o BibLivre não checa nenhum dos três e
  barrar deixaria o app mais rígido que a tela do PC ao lado. A confirmação
  precisa dizer o que está sendo ignorado.

**O caminho do ISBN é de primeira classe.** Boa parte do acervo migrado não tem
etiqueta impressa — os 16.251 tombos existem no banco, nem todos no papel.
Bipar o código de barras da capa devolve os exemplares da obra com o estado de
cada um, e o operador escolhe qual está na mão.

Continuam no BibLivre, e a tela diz isso quando o caso aparece: cadastro e
edição de leitor, reativar ou desbloquear cadastro, receber multa, a fila de
reservas e a catalogação avançada. Ver [docs/SPEC_UI.md](docs/SPEC_UI.md) §10
para os estados e as frases de balcão de cada impedimento, e
[docs/IMPORTACAO_BIBLIVRE.md](docs/IMPORTACAO_BIBLIVRE.md) para as regras
lidas no fonte (prazo, multa, renovação, `logins`).

### Manutenção

Os passos que o roteiro de importação terminava mandando fazer "no BibLivre,
depois" — reindexar, limpar caches, conferir a base e gerar o `.b5bz`. Eles
são feitos por **HTTP contra o próprio BibLivre**, logado como admin, e não
reimplementados: reproduzir o indexador seria copiar a tokenização Java, e
índice errado falha em silêncio.

| Ação | Rota | Observação |
|---|---|---|
| Reindexar | `POST` / `GET /api/manutencao/reindexar` | dispara e volta; o progresso é o `GET`. O índice fica **vazio** no meio do trabalho |
| Limpar caches | `POST /api/manutencao/caches` | traduções sim; campo de leitor **continua** exigindo restart do Tomcat, e a resposta diz isso |
| Conferir a base | `POST /api/manutencao/conferencia` | 26 checagens em SQL, só leitura — também por `python scripts/conferir.py` |
| Gerar backup | `POST` / `GET /api/manutencao/backup` | quem gera é o BibLivre; o `.b5bz` leva dado pessoal de todos os leitores |

**As rotas existem; a tela de manutenção ainda não** — hoje o caminho é a API
ou o `scripts/conferir.py`. O contrato que essa tela vai cumprir está na §11 do
[SPEC_UI.md](docs/SPEC_UI.md).

A conferência é o que responde à pergunta que nenhuma tela responde: **as
sequences estão à frente do `max(id)`?** A migração grava id explícito (é o que
preserva a numeração de origem), id explícito não avança a sequence, e o
primeiro empréstimo que o app tentar gravar é o que estoura chave duplicada —
no balcão, com fila. Rode `scripts/conferir.py` **antes** de ligar a circulação
contra uma base real.

---

## 6) Produção

Atrás de Nginx com Let's Encrypt (trocando o certificado autoassinado),
`PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` por ambiente e
`restart: unless-stopped`. O volume `./data` guarda a fila de revisão, os
exports, as execuções de migração e o certificado — é trabalho de gente
pendente e não pode morrer com o container.

O BibLivre 5 continua no instalador Windows/Java-Tomcat-Postgres: são 61
tabelas e um restore `.b5bz` destrutivo, não vale replicar no Compose. Por isso
o compose sobe só o app e conecta no Postgres que já existe — não há banco de
demonstração: um Postgres vazio ao lado só serviria para desligar o dedup em
silêncio e disputar a porta 5432 com o BibLivre real.

## Aviso

Backups reais (`.bkp`, `.csv`, `data/fila/*.json`, `data/migracao/**`) contêm
dados pessoais de leitores — o `.gitignore` já os exclui. Ver [LICENSE](LICENSE) (MIT).
