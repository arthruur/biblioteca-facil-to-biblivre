# biblioteca-facil-to-biblivre

Ferramentas de gestão de acervo para bibliotecas que rodam **BibLivre 5**.

Duas coisas que se apoiam no mesmo núcleo:

1. **Catalogação por ISBN** — bipar o código de barras no celular, revisar no PC
   e gravar no BibLivre, sem duplicar o que a biblioteca já tem.
2. **Migração de acervo legado** — trazer um acervo inteiro do *Biblioteca
   Fácil* para o BibLivre 5, pela mesma interface (`/migracao`) ou pelos CLIs.
   Executado e validado em campo: 14.880 obras, 16.251 exemplares, 2.743
   leitores e 19.592 empréstimos.

> **Status:** migração completa e validada (`docs/IMPORTACAO_BIBLIVRE.md`).
> Catalogação por ISBN em uso. Ver `docs/ROADMAP.md`.

---

## 1) Como está organizado

```
apps/
  api/          FastAPI — só monta os routers, sem regra de negócio
  web/          React + Vite — as telas
packages/
  bf-legado/         biblio.legado      lê o .bkp do Biblioteca Fácil
  biblivre-client/   biblio.biblivre    fala com o PostgreSQL do BibLivre
  catalogacao/       biblio.catalogacao ISBN, lote, fila, export
  migracao/          biblio.migracao    o pipeline do .bkp ao BibLivre
scripts/        CLIs finos por cima dos pacotes (dry-run por padrão)
tests/          verificação de fumaça, sem banco e sem rede
docs/           formato do .bkp, tabelas, importação, spec de UI
```

O namespace Python é `biblio`, e a regra que atravessa os pacotes é: **nada
neles commita**. Toda função de gravação recebe a conexão e devolve o commit
para quem chamou, porque obras e exemplares precisam fechar na mesma transação
— não existe "gravou metade".

| Pacote | Responde por |
|---|---|
| `biblio.legado` | `bkp`, `tabela`, `consolidar` — o formato proprietário do sistema antigo |
| `biblio.biblivre` | `conexao`, `marc`, `obras`, `exemplares`, `acervo`, `leitores`, `circulacao` |
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

Depois de gravar sobram dois passos fora do app, e a tela os repete: reindexar
a base bibliográfica no BibLivre e reiniciar o Tomcat (os campos novos de
leitor são cache estático).

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

## 5) Produção

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
