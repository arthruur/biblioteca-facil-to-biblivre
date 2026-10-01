# Roadmap

## ✅ Feito

- [x] Decodificar o container `.bkp` (zlib + 16 tabelas)
- [x] **Decodificar o cabeçalho dos `.dat`** — cada arquivo traz um
      catálogo com nome, tipo, tamanho e offset de todos os seus campos.
      Isso tornou desnecessária a caça manual de offsets e resolveu de uma
      vez o mapeamento das 16 tabelas. Ver [TABELAS.md](TABELAS.md).
- [x] Leitor genérico (`biblio.legado.tabela`) — as 16 tabelas passam no
      teste de sanidade de layout
- [x] Mapear ISBN, Tombo, Páginas, CDU (e todo o resto do Acervo)
- [x] Vínculo Autor↔Livro: é a `T10_AUAC`, "Cadastro de Autores nas
      Obras" (17.883 vínculos, integridade referencial verificada)
- [x] Mapear Editoras (`T06_EDIT`) — inclui `LOCALIZACAO`, que serve
      como local de publicação
- [x] Consolidar tudo num CSV (`scripts/consolidar.py`)
- [x] Levantar como o BibLivre 5 aceita dados, lendo o código-fonte —
      ver [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md)
- [x] Decidir o tratamento de exemplares (ver abaixo)
- [x] `biblio.biblivre.marc` — gera `obras.mrc` (14.866 registros
      bibliográficos, ISO 2709/UTF-8) e `exemplares.csv` (16.251 linhas)
- [x] `biblio.biblivre.obras` — carrega `obras.mrc` direto em
      `biblio_records`, já na base principal, reproduzindo
      `BiblioRecordBO.save` (id da sequence, `001` de 7 dígitos, `005`,
      `008`, `material='book'`). Validado byte a byte contra 25 registros
      importados pela tela. Nasceu porque a importação pela tela não escala
      para 14.866 registros no heap de 256 MB do Tomcat e não tem "mover
      todos" — ver [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).
- [x] `biblio.biblivre.exemplares` — o passo dos exemplares: casa cada
      linha do `exemplares.csv` com `biblio_records.id` pelo `035 $a`,
      gera o tombo no formato do próprio BibLivre
      (`<prefixo>.<ano>.<contador>`) e insere em `biblio_holdings`.
      Escrito contra o fonte (Leader, indicadores, colunas e valores dos
      enums conferidos em `HoldingBO`/`HoldingDAO`/`MarcUtils`).
- [x] **Carga real executada** contra uma instância (Windows, BibLivre
      5.0.x, PostgreSQL 9.1, Tomcat 7): 14.866 registros em `biblio_records`
      e 16.251 exemplares em `biblio_holdings`, base `main`, integridade
      referencial verificada (0 holdings órfãos, 0 obras sem exemplar,
      16.251 tombos únicos). Índice reconstruído pela tela.

- [x] **Circulação decodificada e mapeada** — leitores (`T04_LEIT`),
      empréstimos (`T13_MOVM` + `T11_MOVI`), multas e reservas
      (`T15_RESE`). O `holding_id` de cada empréstimo sai do
      `exemplares_mapa.csv` pelo tombo: **19.707 das 19.711**
      movimentações têm exemplar (as 4 restantes são de um registro de
      acervo excluído, nenhuma em aberto).
- [x] `scripts/inserir_leitores.py` — `T04_LEIT` → `users` +
      `users_values`, preservando o `NUMLEITOR` como `users.id`. Cria em
      `users_fields` os 9 campos que o BibLivre não tem (nome dos pais,
      naturalidade, escolaridade, bairro, ponto de referência, contato de
      emergência, matrícula) com as traduções nos três idiomas.
- [x] `scripts/inserir_emprestimos.py` — `lendings`, `lending_fines` e
      `reservations`. Verificado no fonte que empréstimo em aberto **não**
      altera `biblio_holdings.availability`: "emprestado" é derivado de
      `return_date IS NULL`.

- [x] **Carga de circulação executada (2026-08-19):** 2.743 leitores em
      `users` (2.488 active, 255 inactive) e 39.580 valores em
      `users_values`; 9 campos criados em `users_fields` com as traduções;
      19.592 empréstimos em `lendings` (974 em aberto, 707 leitores com
      pendência), 8 multas, 12 reservas. Integridade verificada: 0
      empréstimos com leitor ou exemplar inexistente, 0 exemplares com dois
      empréstimos em aberto, 0 chaves de `users_values` sem campo, 0 reservas
      sem registro, sequences em 2.743 e 19.592.
- [x] Reiniciar o Tomcat, conferir leitor/atrasos na interface e gerar o
      `.b5bz` com a circulação. **A migração está completa e validada**: o
      processo roda de ponta a ponta.

Reindexar exemplares **não** entra na lista: exemplar não tem tabela de
índice no BibLivre, e a busca por tombo é subconsulta ao vivo em
`biblio_holdings`. Ver [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).

- [x] **Reorganização em monorepo (2026-09-01/02).** Os scripts soltos viraram
      pacotes com o namespace `biblio`: `biblio.legado` (lê o `.bkp`),
      `biblio.biblivre` (fala com o PostgreSQL do BibLivre) e
      `biblio.catalogacao` (ISBN, lote, fila, export). A API HTTP (`apps/api`)
      e os CLIs (`scripts/`) passaram a ser duas cascas finas sobre os mesmos
      módulos — antes cada script tinha a própria cópia de `conectar()` e do
      MARC do exemplar. As telas viraram um app React (`apps/web`).
      `python tests/verificar.py` cobre as rotas, a persistência da fila e o
      formato do MARC gerado.

- [x] **Migração pela mesma interface da catalogação (`/migracao`).** O que
      antes eram oito CLIs em sequência virou três passos na tela: enviar o
      `.bkp`, conferir e gravar. O pacote `biblio.migracao` orquestra os mesmos
      módulos que os CLIs usam — nada foi reimplementado —, e acrescenta o que
      a linha de comando não precisava: relatório estruturado em vez de
      `print`; uma transação só para acervo **e** circulação (na linha de
      comando cada passo commitava porque havia uma pessoa lendo o relatório
      entre eles); e o casamento entre exemplar, obra e empréstimo em memória,
      sem depender do `--mapa-out` em disco. Os CLIs continuam de pé, e
      continuam sendo a referência.
- [x] **Verificação offline da migração** (`tests/amostra_bkp.py` escreve um
      `.bkp` sintético; `tests/banco_falso.py` responde ao que a carga
      pergunta). Um botão que grava dezenas de milhares de linhas no PostgreSQL
      da biblioteca não podia ter como única garantia "rodou uma vez em campo",
      e backup real não entra no repositório.

- [x] **Circulação no app: emprestar, devolver, renovar e consultar
      (2026-09-06).** O balcão saiu do BibLivre e entrou na mesma interface da
      catalogação, em duas telas para duas posturas — celular (bipando, de pé,
      com o leitor na frente) e PC (leitor USB, ficha completa, painel de
      atrasados). Grava no PostgreSQL do próprio BibLivre, reproduzindo o
      `LendingBO`: nada de tabela nova, nada de schema paralelo, um empréstimo
      nosso indistinguível de um feito pela tela dele. As regras que isso
      exigiu — as quatro condições de `checkLending`, o prazo em dias corridos
      empurrado para o próximo dia útil, a multa por dia e por item, a
      renovação que é linha nova com `previous_lending_id` — estão em
      [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md), arquivo por arquivo.
      Três invariantes carregam o resto: uma operação é uma transação com
      `SELECT … FOR UPDATE` no exemplar e revalidação **dentro** dela (o
      BibLivre pode estar aberto na mesma base no PC ao lado); só o router
      commita; e impedimento barra enquanto aviso passa com confirmação que
      diz o que está sendo ignorado. O desenho das telas está na §10 do
      [SPEC_UI.md](SPEC_UI.md).
- [x] **`created_by` passa a ser o operador de verdade.** O app autentica
      contra a tabela `logins` do próprio BibLivre (SHA-1 + Base64, o hash
      provado contra o `admin` que o instalador semeia) e usa o `logins.id`
      real. Não inventamos cadastro: quem sai de férias é desligado num lugar
      só, e o `created_by` faz sentido dentro das telas do BibLivre também. A
      sessão é um token opaco em memória, expirando por inatividade — é
      também o mínimo de barreira que a circulação exige, porque sem ela
      qualquer celular no wi-fi da biblioteca registraria empréstimo.
- [x] **Reindex automático depois de gravar obra nova** — o que era aviso na
      tela virou ação do app. Reproduzir o indexador em SQL estava fora de
      questão (seria copiar a tokenização Java do `IndexingBO`, e índice
      errado falha em silêncio), então o app **manda o BibLivre indexar**, por
      HTTP, logado como admin: as ações `reindex` e `progress` de
      `administration.indexing`, com barra de progresso, uma reindexação por
      vez e o aviso de que o índice fica vazio no meio do trabalho
      (`clearIndexes` roda antes de reconstruir). O que **não** foi ligado, e
      está em Próximos passos: o disparo automático dentro da gravação de obra
      nova e a tela que aciona o botão — hoje o caminho é a rota
      `POST /api/manutencao/reindexar`, e a tela de export continua mostrando
      o lembrete.
- [x] **Backup, caches e conferência pelo mesmo canal.** O `.b5bz` é gerado
      pelo próprio BibLivre (`prepare` → `backup` → `progress`, com URL de
      download) porque ele é um `pg_dump` empacotado, não um formato de
      intercâmbio — reimplementá-lo seria entregar um restore que ninguém
      testou. As traduções são derrubadas sem reiniciar o Tomcat
      (`administration.translations/list`). E ficou **provado no fonte** que o
      cache de campos de leitor não tem saída por HTTP: os três chamadores de
      `StaticBO.resetCache()` são destrutivos, então o restart do Tomcat
      continua necessário para campo novo em `users_fields` — o botão diz isso
      na resposta em vez de prometer o que não cumpre.
- [x] **Conferência pós-carga em SQL** (`biblio.biblivre.verificacao`,
      `scripts/conferir.py`, `POST /api/manutencao/conferencia`): 26 checagens
      só de leitura — o índice, as quatro sequences, 12 de integridade
      referencial e 9 contagens informativas. Checagem que não pôde rodar
      (tabela ausente, sem `GRANT`) volta como "não verificada", nunca como
      "passou". Ela existe por causa de dois sintomas silenciosos: obra fora de
      `biblio_idx_fields` (o catálogo existe e não aparece na busca) e
      sequence atrás do `max(id)` — a armadilha que a migração arma e que o
      **primeiro empréstimo do app** dispara, no balcão, com fila. Por isso a
      checagem das sequences é bloqueante antes de liberar a circulação.
- [x] **Scanner em modo circulação** — além do EAN-13 da capa, o decodificador
      passa a ler Code 39 e Code 128, com o conjunto de formatos escolhido por
      modo (`isbn` ou `circulacao`) tanto no motor nativo quanto no de
      reserva. A classificação local do que foi lido é **dica de interface** e
      nada mais: quem decide se aquilo é tombo, ISBN ou leitor é o servidor.
      Ficou documentado no fonte do BibLivre o que a etiqueta impressa
      realmente carrega — e não é o tombo (ver Próximos passos).
- [x] **Tombo estável entre backups (2026-10-01).** O tombo da migração passou
      a ser o `NUMACERVO` do Biblioteca Fácil, o número que está no livro e
      que o balcão usa. Antes ele era gerado (`<prefixo>.<ano>.<contador>`) e
      mudava a cada carga. O formato gerado ficou como opção
      (`tombo_numacervo=False`, `--tombo-gerado`).
- [x] **Recarregar um backup por cima do outro (2026-10-01).** A opção
      "substituir a base pelo backup" (`biblio.biblivre.substituicao`) apaga o
      que a migração carrega, índice incluído, e grava o backup novo na mesma
      transação. Vale o último backup. Não usa `TRUNCATE … CASCADE`: uma FK
      desconhecida faz a carga inteira voltar atrás, em vez de apagar em
      silêncio o que ninguém conferiu.
- [x] **Busca de livro pelo título no balcão (2026-10-01)**, no PC e no
      celular, sem depender do índice do BibLivre (que fica vazio até o
      reindex). Junto veio o `preferir` do `resolver`, porque o tombo só de
      dígitos pode coincidir com o número de um leitor.
- [x] **Subir com o Windows (2026-10-01):** `scripts/inicializacao.py
      instalar` cria uma tarefa agendada de logon que roda o servidor de
      produção sem janela e o reinicia se ele cair. Não precisa de
      administrador.

## 🚧 Próximos passos

Duas frentes deixaram de ser trabalho pendente e viraram **feature de
produto**: a migração de acervo legado (o onboarding de uma biblioteca que vem
de sistema legado) e a circulação (o balcão de todo dia). O que sobra em aberto
é de três naturezas — o que precisa de um BibLivre real na frente, o que ficou
sem tela, e o que continua obrigando a abrir o outro sistema.

### O primeiro teste contra o BibLivre real (a pauta, nesta ordem)

Nada da circulação foi exercitado contra um Postgres de verdade nem contra um
Tomcat de verdade: a garantia de hoje é a verificação offline
(`python tests/verificar.py` cobre as rotas, a transação, o vocabulário de
erro e a conferência contra um banco de mentira) e a leitura do fonte. A ordem
abaixo não é arbitrária — cada passo desarma o risco do seguinte:

1. [ ] `python scripts/conferir.py` — **as sequences primeiro.** Sequence
       atrás do `max(id)` faz o primeiro empréstimo estourar chave duplicada.
2. [ ] Login de operador: que `POST /api/sessao` devolve o `logins.id` certo,
       e que ele aparece em `lendings.created_by` depois.
3. [ ] Um empréstimo de teste: que o prazo calculado bate com o que a tela do
       BibLivre calcularia para o mesmo leitor e o mesmo dia.
4. [ ] A devolução do mesmo: atraso, multa (se houver `fine_value`
       configurado) e o aviso de reserva pendente.
5. [ ] Reindex e backup pela rota (`POST /api/manutencao/reindexar` e
       `.../backup`, com os `GET` de progresso) — enquanto não há tela, é por
       aí que se dispara.
6. [ ] Só então: encostar num acervo de produção.

### O que ainda precisa ser confirmado na instalação (5.0.x)

Todo o fonte que sustenta a circulação e a manutenção foi lido num **fork** no
GitHub. A biblioteca roda um 5.0.x instalado pelo instalador de Windows, e
estas afirmações são as que uma diferença de versão derrubaria:

- [ ] **A etiqueta impressa e o `resolver`** — é o item mais urgente. No fonte,
      `HoldingBO.printLabelsToPDF` imprime na barra o `biblio_holdings.id` com
      zeros à esquerda até 10 dígitos, **não** o `accession_number`; e
      `UserBO` imprime a carteirinha do leitor exatamente na mesma forma
      (`users.id`, 10 dígitos). Hoje o `resolver` procura tombo exato, tenta
      ISBN e depois procura leitor por id — então `0000000842` cai no
      **leitor** 842, não no exemplar 842. Precisa ser testado com uma
      etiqueta de verdade desta biblioteca, e a ordem de resolução decidida
      com essa informação na mão.
- [ ] `configurations['general.business_days']` na base da biblioteca: o
      instalador semeia segunda-a-sexta e o template tem uma linha comentada
      com segunda-a-sábado. Se a biblioteca abre sábado, o prazo muda.
- [ ] `users_types.fine_value` — vale 0,00 nos dois tipos semeados, o que quer
      dizer que **nenhuma multa é gravada** até alguém configurar o valor em
      Administração. Se esta biblioteca cobra multa hoje, é configuração no
      BibLivre, não código. Conferir também se existem tipos além de Leitor e
      Funcionário, porque limite e prazo saem de lá.
- [ ] A tabela `logins`: que tem as colunas que o fonte diz, que `permissions`
      é legível pelo papel `biblivre`, e se o `admin` ainda está com o hash
      público do instalador.
- [ ] O canal HTTP: o contexto da URL (`/Biblivre5/` é padrão, mas é
      configurável), o nome do schema, e se as ações `reindex`/`progress`,
      `translations/list` e as três de `backup` respondem como o fonte diz.
- [ ] O leitor de código de barras USB do balcão: que ele entrega os dígitos e
      o Enter no campo com foco permanente, inclusive logo depois de um clique
      em botão.
- [ ] A carga completa da migração disparada **pela tela** (o código de
      gravação é o mesmo já validado pelos CLIs; o que falta medir é o tempo
      de uma base de 14 mil obras num clique).

### O que ficou sem tela

- [ ] **Tela de manutenção.** As oito rotas de `/api/manutencao` estão
      implementadas e testadas, e nenhuma tela as consome: hoje o caminho é a
      API ou o `scripts/conferir.py`. O contrato que essa tela vai cumprir
      está escrito na §11 do [SPEC_UI.md](SPEC_UI.md), inclusive o custo do
      painel (laço lento) e o aviso de que o índice fica vazio durante o
      reindex.
- [ ] **Reindex automático dentro da gravação de obra nova.** A capacidade
      existe (`web.reindexar`); o que falta é chamá-la quando o export cria
      registro novo, em vez de mostrar o lembrete. Enquanto isso o lembrete
      continua correto e continua aparecendo só quando houve obra nova.
- [ ] **O contador de atrasos na barra de navegação** nasce em zero e nunca é
      alimentado — quem alimentaria é o `App.jsx`, com a mesma rota que o
      painel do PC já consome.
- [ ] **O histórico do leitor.** A ficha do PC tem a seção, paginada, e ela
      está vazia: `GET /api/circulacao/leitor/{id}` devolve só os empréstimos
      em aberto. Fazer a rota devolver os devolvidos exige paginação **no
      servidor** — leitor antigo desta base tem centenas de linhas, e a
      migração trouxe 18.618 devolvidos.

### O que continua obrigando a abrir o BibLivre

Recorte deliberado — o balcão é 90% do uso diário e é onde a tela do BibLivre
pesa; o resto é uso ocasional, de gente sentada. Mas é o que o usuário vai
perguntar primeiro:

| Continua no BibLivre | Consequência no balcão |
|---|---|
| Cadastro e edição de leitor | leitor novo interrompe o atendimento e obriga a abrir o outro sistema — é o primeiro candidato à fase 2 |
| Reativar ou desbloquear cadastro | o app diz o motivo e manda para lá |
| Receber/quitar multa | o app mostra o valor apurado; receber dinheiro é operação de caixa |
| Fila de reservas | a devolução avisa "separe para tal leitor", mas administrar a fila não tem rota |
| Restart do Tomcat depois de criar campo de leitor | provado no fonte que não há saída por HTTP |
| Restore do `.b5bz` | é destrutivo por natureza |
| Catalogação avançada, etiquetas, cartões, relatórios, permissões, Z39.50 | uso ocasional, de gente sentada |

### Fica em aberto, sem urgência

- [ ] Medir em campo quanto o dedup por ISBN de fato pega — o teste com a fila
      real pegou 19 de 26.
- [ ] OCR de ficha CIP para livro sem código de barras (fase de projeto, ver
      [CATALOGACAO_POR_FOTO.md](CATALOGACAO_POR_FOTO.md)).
- [ ] Duas rotas que o contrato não previu e que as telas pediriam:
      um `GET /api/circulacao/checar` (mostrar o prazo previsto e os avisos
      **antes** do clique, em vez de descobrir tudo pelo 409) e um
      `GET /api/sessao/ativas` (quem está no balcão). As duas funções de
      domínio já existem; falta decidir se entram no contrato.
- [ ] Contenção no `POST /api/sessao`. Não há bloqueio por tentativas — nem
      aqui, nem no BibLivre (verificado no fonte). Enquanto o app vive na LAN
      da biblioteca isso é aceitável; exposto para fora, não.
- [ ] Cobertura automatizada da lógica das telas de circulação. O repositório
      não tem runner de DOM (`npm test` é `node --test src`), então o que
      existe são as funções puras e a verificação do servidor; montar
      componente exigiria dependência nova.

## Decisão tomada: 1 registro bibliográfico por obra

O Biblioteca Fácil grava **cada exemplar físico como um registro separado
do acervo** — 16.251 registros ativos para 14.866 obras distintas, com um
título chegando a 18 cópias.

A decisão foi **agrupar por obra**, e o motivo não é preferência
catalográfica: é que a alternativa não funciona. A importação de arquivo
do BibLivre **só cria registros bibliográficos, nunca exemplares**, e
empréstimo é feito contra exemplar. Importar 1 registro por cópia não
criaria exemplar nenhum — só duplicaria fichas e deixaria o acervo
inemprestável. As duas opções exigem um segundo passo para os exemplares,
então não há motivo para aceitar o catálogo pior. Ver
[IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md) para as referências no
código.

### Os tradeoffs que sobram

**O que se ganha:** catálogo correto (uma ficha por obra, com a contagem
de exemplares); busca que não devolve 18 resultados idênticos; e o
caminho para circulação funcionando.

**O que se paga:**

1. **O segundo passo é obrigatório e mexe direto no banco.** Sem ele, o
   acervo fica catalogado e inemprestável. Não é opcional.
2. **O agrupamento é heurístico.** Não existe identificador de obra no
   Biblioteca Fácil; a identidade é inferida do conteúdo.
3. **O `NUMACERVO` original deixa de ser a identidade do registro
   bibliográfico.** Ele sobrevive por exemplar (em `exemplares.csv`) e o
   menor do grupo vai no `035 $a`, mas quem depender do número antigo
   precisa passar pelo exemplar.

### Por que o agrupamento não usa ISBN

Testamos e o resultado foi ruim: o maior grupo por ISBN juntou *"Paixão –
Doce Traição"* (Maya Blake), *"Felizes... Para Sempre?"* (Raye Morgan) e
*"Corações Blindados"* (Diana Palmer) — três livros diferentes da Editora
HR cadastrados com o mesmo ISBN. ISBN aqui é digitado à mão e não é
identidade confiável. Ele entra no registro (020), mas não na chave.

A chave é o conteúdo normalizado: título, subtítulo, autor, editora, ano,
volume e edição. **O volume é essencial** — sem ele os quatro volumes de
*Português – Palavra Aberta* (5ª a 8ª série) virariam um registro só.

O critério é deliberadamente conservador: **preferir separar demais a
juntar demais**. Separar a mais gera duas fichas do mesmo livro, que o
bibliotecário funde em minutos. Juntar a mais faz uma obra distinta
sumir do catálogo — e ninguém percebe. Por isso variações de grafia
("CORES SONHOS E SILÊNCIO" vs "CORES, SONHOS E SILÊNCIO") são
normalizadas, mas nada além disso é adivinhado. Dos 16.251 registros,
1.385 foram reconhecidos como cópias; o que restou de duplicata real
aparece como fichas separadas, não como perda.

## A circulação migrada: o que entra e o que não entra

Esta seção é sobre a **carga** dos dados de circulação do sistema antigo, não
sobre o balcão de todo dia (esse está na §10 do [SPEC_UI.md](SPEC_UI.md)). Ela
entrou no escopo depois do acervo, com estas decisões:

- **Histórico completo de empréstimos**, não só os abertos: 19.592 linhas em
  `lendings` (974 em aberto, 18.618 devolvidos). O `--apenas-abertos` existe
  para quem preferir o contrário.
- **Todos os 2.743 leitores**, inclusive os 255 excluídos/desativados na
  origem — que entram como `inactive`, o status que o BibLivre esconde da
  busca e recusa em empréstimo. Sem eles, 89 movimentações históricas
  ficariam sem dono.
- **Só as 12 reservas pendentes de 2026.** Das 115 pendentes, 103 são de
  2016-2020 — reserva vencida há anos não é intenção viva.
- **Fora:** as 113 movimentações apagadas na origem (`T11_EXCLUSAO` é a data
  da exclusão), 2 sem cabeçalho em `T13_MOVM` (sem leitor, e `user_id` é NOT
  NULL), as fotos de leitor (só o caminho da máquina antiga está no backup) e
  12 datas de nascimento impossíveis.

Vale lembrar o que isso significa: `users_values` passa a guardar CPF, RG,
nome da mãe, endereço e telefone de 2.743 pessoas, e o `.b5bz` leva tudo
consigo.

Um efeito colateral esperado: 717 dos empréstimos em aberto venceram entre
2013 e 2025. Eles migram como atraso, e é assim que o acervo realmente está —
o BibLivre vai mostrar esses leitores como pendentes até que a biblioteca dê
baixa neles.

## Por que MARC21/ISO 2709 e não XML ou texto simples

O BibLivre 5 aceita três formatos de importação: texto, XML ou ISO 2709.
Optamos por ISO 2709 (MARC21, codificado em UTF-8) porque existe uma
biblioteca Python madura (`pymarc`) que cuida de toda a formatação
binária exigida pelo padrão — reduz a superfície de erro comparado a
montar o XML MARCXML à mão.

## Projeto derivado: catalogar livro novo por foto

A migração cobre o acervo que já existia. Para o livro que entra depois,
há um projeto separado — fotografar a **ficha CIP** impressa na página de
crédito e chegar a um registro pré-preenchido para revisão, reaproveitando
o `gerar_marc.py` e a carga já validada.

O caminho por **código de barras** (mais confiável que OCR de ficha CIP) já
está implementado e em uso — ver [SPEC_UI.md](SPEC_UI.md) para as telas e o
[README](../README.md) para o fluxo. O que sobra de OCR de ficha CIP segue em
fase de projeto: decisões de arquitetura, o que é fato apurado no fonte, o que
ainda é hipótese e as três métricas que a fase 1 precisa medir estão em
[CATALOGACAO_POR_FOTO.md](CATALOGACAO_POR_FOTO.md).

### O que a catalogação por ISBN já resolve

- [x] **Dedup por ISBN contra o acervo** (`biblio.biblivre.acervo`) — o
      ISBN lido é confrontado com o 020 $a de `biblio_records` antes de gerar
      MARC. Livro que já existe entra como **exemplar** do registro que já está
      lá, não como ficha nova. O casamento aceita ISBN-10 e ISBN-13 como o
      mesmo livro. Índice em memória (~10.5 mil ISBNs varridos em <1s, TTL de
      5 min, invalidado a cada gravação) porque o ISBN mora dentro do blob
      `iso2709`: não há coluna nem índice, e buscar um a um seria varredura de
      tabela a cada bipe.
- [x] **Fila persistida e revisável** (`biblio.catalogacao.fila`,
      `apps/web` (tela de revisão)) — os itens já viviam em `data/fila/*.json`, mas o
      servidor nunca os relia: reiniciar o processo dava fila vazia com os
      arquivos intactos no disco. Agora carregam na subida, têm `id` e ciclo
      de vida (`pendente → revisado → exportado`, ou `ignorado`), e o
      dashboard do PC edita, filtra, agrupa e exporta em lote.
- [x] **Exemplares no mesmo lugar da migração**
      (`biblio.biblivre.exemplares`) — reusa `montar_exemplar`,
      `gerar_tombos` e `ler_prefixo_tombo` de `inserir_exemplares.py` em vez de
      chamar o script por subprocesso. Obras e exemplares fecham na **mesma
      transação**: não existe mais obra gravada com exemplar faltando.

O que ainda está em aberto na catalogação está em **Próximos passos**, no
começo deste arquivo.
