# Importação no BibLivre 5

Este documento registra como o BibLivre 5 realmente aceita dados, apurado
lendo o código-fonte (github.com/Biblivre/Biblivre-5). Ele existe porque a
decisão de formato do `.mrc` depende inteiramente destes detalhes.

Ele cresceu junto com o produto e hoje cobre duas coisas: a **carga** de um
acervo inteiro (a metade de cima) e as regras que o app precisa reproduzir
para **emprestar e devolver todo dia** (a metade de baixo — `LendingBO`,
prazo, multa, `logins` e a etiqueta impressa). Entre as duas está a armadilha
das sequences, que é o que liga uma coisa na outra: é a carga que a arma e é o
primeiro empréstimo que a dispara.

## A restrição que define tudo: a importação não cria exemplares

`src/java/biblivre/cataloging/Handler.java`, método `saveImport()`, aceita
três tipos de registro:

```java
switch(recordType) {
    case BIBLIO:      dto = new BiblioRecordDTO(); break;
    case AUTHORITIES: dto = new AuthorityRecordDTO(); break;
    case VOCABULARY:  dto = new VocabularyRecordDTO(); break;
    default:          dto = new RecordDTO();
}
```

`RecordType` tem quatro valores — `BIBLIO`, `AUTHORITIES`, `VOCABULARY` e
`HOLDING` —, mas **`HOLDING` não é tratado na importação**. Não existe
formato de arquivo que crie exemplares no BibLivre.

E não é um descuido que dê para contornar: exemplar é um registro MARC
separado ligado ao bibliográfico por uma **chave estrangeira no banco**
(`HoldingDTO.setRecordId(...)` → coluna `biblio_holdings.record_id`). Essa
ligação não tem representação dentro de um arquivo MARC.

## E empréstimo é feito contra exemplar

```java
public boolean doLend(HoldingDTO holding, UserDTO user, int createdBy)
```

`LendingBO` opera exclusivamente sobre `HoldingDTO`. Um acervo importado
sem exemplares aparece no catálogo mas **não pode ser emprestado**.

Consequência prática: gerar 1 registro bibliográfico por exemplar físico
não resolve nada — não cria exemplar, não habilita empréstimo, e ainda
duplica fichas no catálogo.

## Anatomia de um exemplar

`HoldingBO.createAutomaticHolding()` monta o registro assim:

| Campo | Conteúdo |
|---|---|
| Leader | `MaterialType.HOLDINGS` |
| `090 $a` | copiado do `090 $a` do registro bibliográfico |
| `090 $b` | copiado do `090 $b` do registro bibliográfico |
| `090 $c` | copiado do `090 $c` do bibliográfico; se vazio, `"v.N"` |
| `090 $d` | `"ex.N"` — o número do exemplar |
| `541 $a` | biblioteca depositária |
| `541 $c` | tipo de aquisição |
| `541 $d` | data de aquisição |
| `949 $a` | número de tombo (`MarcConstants.ACCESSION_NUMBER`) |

**É por isso que o `gerar_marc.py` preenche o `090 $a$b$c`** do registro
bibliográfico com CDD, Cutter e volume: o BibLivre propaga esses três
subcampos para cada exemplar que cria.

O Leader sai de `MarcUtils.createBasicLeader(MaterialType.HOLDINGS,
RecordStatus.NEW)`, que fixa cada posição:

| Posição | Valor | Origem |
|---|---|---|
| 05 | `n` | `RecordStatus.NEW` |
| 06 | `u` | `MaterialType.HOLDINGS('u', "  ", false)` |
| 07-08 | `  ` | idem (`implDefined1`) |
| 09 | `a` | Unicode, fixo |
| 10-11 | `22` | `indicatorCount` / `subfieldCodeLength` |
| 17-19 | `un ` | ramo `HOLDINGS` de `createBasicLeader` |
| 20-23 | `4500` | `entryMap` |

Ou seja: `00000nu  a2200000un 4500` (00-04 e 12-16 são recalculados na
serialização).

Detalhe de indicadores: `createHoldingMarcRecord` grava `090` e `541` com
indicadores **`_`** (sublinhado literal, é o que o formulário do BibLivre usa
para "em branco"), enquanto `MarcUtils.setAccessionNumber` grava o `949` com
espaços. Inconsistente, mas é o que o BibLivre produz — o
`inserir_exemplares.py` reproduz assim.

## O contrato do INSERT, coluna por coluna

`HoldingDAO.save` é a referência:

```sql
INSERT INTO biblio_holdings
  (id, record_id, iso2709, availability, database, material,
   accession_number, location_d, created_by)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

| Coluna | Valor | Por quê |
|---|---|---|
| `id` | `nextval('biblio_holdings_id_seq')` | a coluna tem DEFAULT; deixar a sequence trabalhar mantém o contador certo |
| `record_id` | `biblio_records.id` | a FK que o arquivo MARC não expressa |
| `iso2709` | MARC serializado em UTF-8 | `MarcUtils.recordToIso2709` usa `MarcStreamWriter(os, "UTF-8")`; os tamanhos no Leader são contados em **bytes** |
| `availability` | `available` | `HoldingAvailability.toString()` é `name().toLowerCase()` |
| `database` | `main` / `work` | mesmo do bibliográfico (`setRecordDatabase(autoDto.getDatabase())`) |
| `material` | `holdings` | `MaterialType.toString()` também é minúsculo |
| `accession_number` | tombo | NOT NULL + `IX_biblio_holdings_accession_number` UNIQUE |
| `location_d` | `ex.N` | mesmo valor do `090 $d` |
| `created_by` | `1` | o `logins.id` do admin criado na instalação; a coluna não tem FK |

Sobre o `created_by`: na **carga** ele é `1` mesmo — o admin do instalador é
quem "cadastrou" o acervo, e não há outra resposta honesta para uma migração.
No **dia a dia** ele deixou de ser `1`: o app autentica contra `logins` e grava
o `logins.id` de quem está no balcão, porque quem emprestou é informação de
balcão (ver "O operador: a tabela `logins`", abaixo).

## O formato do tombo

`HoldingBO.getNextAccessionNumber()` monta
`<prefixo>.<ano corrente>.<contador>`, com o prefixo vindo de
`configurations['cataloging.accession_number_prefix']` (padrão `Bib`) e o
contador de `HoldingDAO.getNextAccessionNumber`:

```sql
SELECT max(COALESCE(CAST(SUBSTRING(accession_number FROM '([0-9]{1,10})$') AS INTEGER), 0)) + 1
  FROM biblio_holdings WHERE accession_number > ? AND accession_number < ?;
```

Isto é: **o maior número no fim do tombo, dentro do prefixo do ano corrente,
mais um** — sem zeros à esquerda. Gerar os tombos da migração no mesmo formato
(`Bib.<ano de aquisição>.<n>`) faz o contador do BibLivre continuar de onde a
migração parou, em vez de recomeçar do 1 e colidir com o índice UNIQUE.

## Reindexar **não** é necessário para os exemplares

Ao contrário do que se supôs no começo: exemplar não tem tabela de índice.
Existem `biblio_idx_*`, `authorities_idx_*` e `vocabulary_idx_*` — nenhuma de
holdings —, e o pacote `administration/indexing` não menciona holdings em
lugar nenhum. A busca por tombo, id ou data de exemplar é subconsulta ao vivo:

```java
// SearchDAO.createAdvancedFilterClause, para holding_accession_number et al.
clause.append("R.id IN (SELECT record_id FROM biblio_holdings ");
```

`ReportsDAO` conta exemplares com `SELECT count(id) ... WHERE record_id = ?`,
também ao vivo. Logo, exemplares inseridos por SQL já aparecem e já podem ser
emprestados sem passo de reindexação. (Reindexar não faz mal, só não resolve
nada aqui.)

## Tabela de exemplares

```sql
CREATE TABLE biblio_holdings (
    id               integer NOT NULL,
    record_id        integer NOT NULL,   -- FK -> biblio_records.id
    iso2709          text NOT NULL,
    database         varchar(10) DEFAULT 'main' NOT NULL,
    accession_number varchar NOT NULL,   -- tombo, precisa ser único
    location_d       varchar,
    created          timestamp DEFAULT now() NOT NULL,
    created_by       integer,
    modified         timestamp DEFAULT now() NOT NULL,
    modified_by      integer,
    material         varchar(20),
    availability     varchar DEFAULT 'available' NOT NULL,
    label_printed    boolean DEFAULT false
);
```

O próprio BibLivre popula essa tabela direto por SQL na migração dele do
Biblivre 3 (`DataMigrationDAO.java` + `HoldingDAO.saveFromBiblivre3`) —
ou seja, inserir exemplares por SQL é o caminho que o projeto usa, não uma
gambiarra.

## Circulação: leitores, empréstimos e reservas

Também não há importação por arquivo aqui — a única entrada de usuário é o
formulário de Circulação, um leitor por vez. E, de novo, o próprio BibLivre faz
esta carga por SQL na migração dele do Biblivre 3: `UserDAO.saveFromBiblivre3` e
`LendingDAO.saveFromBiblivre3` gravam com **id explícito**, o que permite
preservar a numeração de origem.

### O leitor é chave/valor

`users` guarda só id, name, type, status e `name_ascii`. Todo o resto vive em
`users_values (user_id, key, value, ascii)`, e as chaves válidas são as linhas
de `users_fields` — há FK, então **campo que não existe em `users_fields` não
pode ser gravado**. A instalação padrão traz 16 campos (email, gender, telefones,
id_rg, id_cpf, endereço em 6 partes, birthday, obs).

| Detalhe | Onde está | Consequência |
|---|---|---|
| `users.status` | enum `UserStatus`: active, pending_issues, inactive, blocked | `LendingBO.checkLending` recusa empréstimo para inactive/blocked e `UserDAO.search` esconde inactive — serve para os desativados/excluídos da origem |
| `name_ascii`, `users_values.ascii` | usados com `ilike` em `UserDAO.search` | preencher com `TextUtils.removeDiacriticals` (NFD sem acentos, **sem** mudar a caixa), senão a busca não acha |
| rótulo do campo | tradução `circulation.custom.user_field.<chave>` em `global.translations` (6.395 linhas; a tabela do schema da biblioteca está vazia) | campo novo sem tradução aparece sem nome na tela |
| opções de `gender` | `...user_field.gender.1` = Masculino, `.2` = Feminino | o valor gravado é `"1"`/`"2"` |
| `birthday` | `UserFieldsDAO` força o tipo para DATE, com um comentário `//BACALHAAAAAAU` | o valor é texto livre, renderizado pelo date picker no padrão do idioma (dd/mm/aaaa em pt-BR) |
| `users_fields.required` | validado em `user/Validator.java`, não no banco | inserir sem email passa, mas a tela exigiria preencher em qualquer edição futura |
| cache | `UserFields` e `Translations` são `StaticBO` | criar campo ou tradução por SQL exige **reiniciar o Tomcat** para aparecer |

Campos do Biblioteca Fácil sem equivalente (nome dos pais, naturalidade,
escolaridade, bairro, ponto de referência, contato de emergência, matrícula)
entram como campos novos em `users_fields` + tradução nos três idiomas. Isso é
uso previsto, não gambiarra: o nome da chave de tradução é literalmente
`circulation.custom.user_field.*`.

### Empréstimo em aberto não mexe no exemplar

`lendings` é uma linha por exemplar (holding_id, user_id,
expected_return_date, return_date, created). O ponto que precisava ser
verificado: **`LendingBO.doLend` não altera `biblio_holdings.availability`**.
"Emprestado" é estado derivado — `isLent` e `LendingDAO` consultam
`lendings.return_date IS NULL`; `availability` responde outra pergunta (se o
exemplar pode circular). Logo, empréstimo em aberto migrado é só uma linha em
`lendings`, sem UPDATE em exemplar.

O elo com o acervo é o exemplar, e ele existe: `exemplares_mapa.csv` guarda
`numacervo -> tombo`, o tombo é UNIQUE em `biblio_holdings`, e daí sai o
`holding_id`. `previous_lending_id` (cadeia de renovação) fica nulo — o
Biblioteca Fácil não guarda essa relação.

Multa vai em `lending_fines` (lending_id, user_id, fine_value, payment_date).
Reserva vai em `reservations`, ligada ao **registro**, não ao exemplar
(`record_id`).

## A armadilha das sequences

Este parágrafo tem seção própria porque é a única coisa neste documento que
**quebra em produção, no balcão, com fila esperando** — e que não dá sintoma
nenhum antes disso.

A migração grava **id explícito**. É deliberado: é o que preserva a numeração
de origem (`users.id` = `T04_NUMLEITOR`, `lendings.id` na ordem cronológica) e
é o que o próprio BibLivre faz na migração dele do Biblivre 3
(`UserDAO.saveFromBiblivre3`, `LendingDAO.saveFromBiblivre3`). Só que no
PostgreSQL um `INSERT` com id explícito **não avança a sequence**. Quem carrega
sem o `setval` no fim deixa `users_id_seq` em 1 com 2.743 leitores na tabela, e
`lendings_id_seq` em 1 com 19.592 empréstimos — e nada acontece.

Nada acontece porque **ler não usa a sequence**. O catálogo abre, a ficha do
leitor abre, o relatório de atrasados sai. A bomba arma no primeiro `INSERT`
feito pela tela: o BibLivre pede `getNextSerial`, recebe 1, tenta gravar e
leva violação de chave duplicada. A mensagem que aparece não diz nada sobre
migração — e agora, com a circulação dentro do app, **o primeiro empréstimo
que o app tentar gravar é o que estoura**, porque no balcão a decisão é
justamente deixar a sequence trabalhar (`nextval`) em vez de atribuirmos ids
nós mesmos, como a carga faz.

Daí a checagem 5 da conferência (`sequence de users`, e as três irmãs de
`biblio_records`, `biblio_holdings` e `lendings`) ser **bloqueante antes de
liberar a circulação**:

```bash
python scripts/conferir.py            # relatório completo, só leitura
```

Se alguma sequence aparecer atrás do `max(id)`, o conserto é um `setval` por
tabela, e ele é seguro — as sequences não têm outro uso:

```sql
SELECT setval('users_id_seq',           (SELECT max(id) FROM users));
SELECT setval('lendings_id_seq',        (SELECT max(id) FROM lendings));
SELECT setval('biblio_records_id_seq',  (SELECT max(id) FROM biblio_records));
SELECT setval('biblio_holdings_id_seq', (SELECT max(id) FROM biblio_holdings));
```

A carga validada em campo terminou com as sequences em 2.743 e 19.592, ou seja
certas — mas isso vale para a base que **nós** carregamos. Base que chegou por
outro caminho (um `.b5bz` restaurado, uma carga manual, um `psql` de alguém)
precisa passar pela conferência antes de o primeiro leitor levar um livro.

## O empréstimo do dia a dia: o que o `LendingBO` decide

Até aqui este documento tratava de **carga**: como enfiar um acervo inteiro no
BibLivre uma vez. A partir do momento em que o app passou a emprestar e
devolver todo dia, passou a valer outra pergunta — quais são as regras que o
BibLivre aplica em cada empréstimo, para que uma linha gravada por nós seja
indistinguível de uma gravada pela tela dele.

Tudo abaixo foi lido no fonte (github.com/cleydyr/Biblivre-5, um **fork**; a
instalação da biblioteca é 5.0.x, e o que precisa ser confirmado contra ela
está marcado no fim de cada bloco). É a mesma natureza do que já está escrito
aqui sobre `HoldingBO` e `UserDAO`.

### As quatro condições que barram — e as três que não existem

`LendingBO.checkLending(holding, user)` recusa em quatro condições, **e só
nelas**:

| # | Condição | Origem |
|---|---|---|
| 1 | `UserStatus.BLOCKED` ou `INACTIVE` | `users.status` |
| 2 | `holding.availability != AVAILABLE` | `biblio_holdings.availability` (só existem `available` e `unavailable`) |
| 3 | `isLent(holding)` | há `lendings` com `return_date IS NULL` |
| 4 | `getCurrentLendingsCount(user) < type.getLendingLimit()` | contagem × `users_types.lending_limit` |

O que **não** está ali é tão importante quanto o que está: não há checagem de
**multa em aberto**, não há checagem de **atraso** e não há checagem de
**reserva de terceiro**. Isso não é ambiguidade do fonte — é ausência
declarada, e foi ela que definiu a divisão entre impedimento e aviso da §10 do
[SPEC_UI.md](SPEC_UI.md): barrar por multa deixaria o app mais rígido que a
tela do PC ao lado, e o balcão veria "não pode" um segundo antes de o BibLivre
emprestar o mesmo livro.

`checkRenew` é o mesmo `checkLending` menos o `isLent` (o exemplar está
emprestado justamente para quem renova) e com o limite frouxo (`count <=
limite`).

### O prazo: dias corridos, empurrados para o próximo dia útil

`CalendarUtils.calculateExpectedReturnDate` chama **`moveByDays(dias)`** — a
chamada `moveByBusinessDays` está **comentada** no fonte. Então o prazo é em
dias **corridos**, e só o resultado é empurrado para frente até cair num dia
de funcionamento (`HolidayHandlerType.FORWARD`).

A semana útil vem de `configurations['general.business_days']`, no formato do
`java.util.Calendar` (**1 = domingo … 7 = sábado**). O instalador semeia
`2,3,4,5,6` no schema `global` — segunda a sexta. E `loadHolidays()` está
**comentado**: nenhum feriado é registrado no calendário. Ou seja, a resposta
à pergunta "feriado entra no prazo?" é **não** — só o dia da semana entra.

> **A confirmar na instalação real:** o valor de `general.business_days` na
> base desta biblioteca. O template traz uma linha comentada com
> `2,3,4,5,6,7` (segunda a sábado); se a biblioteca abre sábado e alguém
> mexeu nisso pela tela, o prazo muda. O código lê o schema da biblioteca,
> depois o `global`, depois cai no padrão — então acerta sozinho; o que
> precisa ser conferido é se o valor lido bate com o horário de verdade.

### Prazo e limite são por **tipo de leitor**

Saem de `users_types`: `lending_time_limit` (dias) e `lending_limit`
(quantidade). A instalação semeia dois tipos:

| id | Nome | Limite | Prazo | `fine_value` |
|---|---|---|---|---|
| 1 | Leitor | 3 | 15 dias | 0,00 |
| 2 | Funcionário | 99 | 365 dias | 0,00 |

A migração deste repositório põe **todos** os leitores no tipo 1. Leitor sem
tipo cai no que o `LendingBO` usa como último recurso: limite **1** e prazo
**7 dias** (os ternários `: 1` e `: 7`).

### A multa: por dia, por item, e hoje ela é zero

`LendingFineBO`: multa = **dias de atraso × `users_types.fine_value`**, valor
por dia e por item, com `calculateLateDays` contando dias **corridos** entre
`expected_return_date` e agora, nunca negativo. `createFine` só é chamada pela
devolução quando o valor é maior que zero, e grava

```sql
INSERT INTO lending_fines (user_id, lending_id, fine_value, payment_date, created_by)
```

com `payment_date` **nulo** — quem quita é o `payFine`, com `UPDATE … SET
payment_date = now()`. Nós calculamos igual e gravamos igual.

Duas consequências que ninguém adivinha lendo a tela:

- **`fine_value` é 0,00 nos dois tipos semeados.** Enquanto ninguém configurar
  o valor em Administração, nenhuma linha de multa é gravada — o cálculo está
  certo e simplesmente não insere nada. Se esta biblioteca cobra multa hoje,
  isso é configuração no BibLivre, não código nosso.
- **Renovar livro atrasado não gera multa.** `doRenew` chama o `doReturn` do
  DAO direto, sem passar pelo `LendingFineBO`. É quirk do BibLivre, e nós o
  reproduzimos — mas a renovação devolve `atraso_dias` e um aviso, para o
  balcão ver o que está perdoando.

> **A confirmar na instalação real:** o `fine_value` de cada tipo e se existem
> tipos além dos dois semeados. Limite e prazo saem de lá.

### Renovação é linha nova, não `UPDATE`

`LendingDAO`, os três verbos que importam:

| Verbo | SQL |
|---|---|
| `doLend` | `INSERT INTO lendings (holding_id, user_id, previous_lending_id, expected_return_date, created_by)` — **sem `id` e sem `created`**: os dois vêm do DEFAULT (a sequence e o `now()`) |
| `doReturn` | `UPDATE lendings SET return_date = now() WHERE id = ?` |
| `doRenew` | `doReturn(antigo)` **+** `doLend(nova)` com `previous_lending_id` = id do antigo, na mesma transação |

Ou seja: renovação **não** é `UPDATE` de `expected_return_date`, é uma linha
nova apontando para a anterior — e é assim que o recibo do próprio BibLivre
separa "empréstimos" de "renovações" (`previousLendingId != null && > 0`). O
prazo da renovação é recalculado a partir de **hoje**, não da data prevista
antiga.

Detalhe que a base migrada obriga a respeitar: a consulta do empréstimo
corrente é `WHERE holding_id = ? AND return_date IS NULL ORDER BY id DESC`.
O `ORDER BY id DESC` está reproduzido porque base carregada de sistema legado
pode ter duas linhas abertas para o mesmo exemplar — e a conferência tem uma
checagem só para isso.

### A reserva é da obra, e o empréstimo apaga a do próprio leitor

`reservations` liga-se ao **registro** (`record_id`), não ao exemplar, e vale
enquanto `expires > localtimestamp`. Depois de gravar o empréstimo,
`LendingBO.doLend` apaga a reserva **do próprio leitor** para aquela obra
(`ReservationBO.delete(userId, recordId)`) — uma reserva, a que expira
primeiro. Reproduzido igual.

Reserva de **outro** leitor o BibLivre nem consulta ao emprestar. Nós
consultamos e mostramos como aviso, porque é informação que o balcão precisa
ver; e por ser acréscimo nosso, ela nunca barra.

### O leitor: busca, matrícula e os dois avisos

`UserDAO.search` é `U.name_ascii ilike '%' || <busca sem acento> || '%'` com
`U.status <> 'inactive'` e `ORDER BY UPPER(U.name)`; busca numérica cai em
`U.id = ?`. Daí sair de graça a definição dos dois avisos que a tela mostra:

| Aviso | Consulta |
|---|---|
| multa em aberto | `lending_fines` com `fine_value > 0 AND payment_date IS NULL` |
| em atraso | `lendings` com `return_date IS NULL AND expected_return_date < now()` |

E `UserDTO.getEnrollment()` é `leftPad(id, 5, "0")`: a "matrícula" impressa na
carteirinha é o `users.id` com zeros à esquerda. Por isso o `resolver` aceita
`00317` tanto quanto `317`, e por isso a matrícula do sistema antigo — que a
migração guardou como campo `registration` em `users_values` — é um terceiro
caminho, não o principal.

### O operador: a tabela `logins`, e o que ela não tem

`created_by` deixou de ser `1`. O app autentica contra a tabela `logins` do
próprio BibLivre, o que dá o `logins.id` verdadeiro (o `created_by` passa a
fazer sentido dentro das telas do BibLivre também) e é uma senha a menos para
a biblioteca administrar.

O hash está verificado e é provado por um teste: `LoginBO` chama
`TextUtils.encodePassword`, que é `MessageDigest.getInstance("SHA")` (SHA-1)
sobre os bytes **UTF-8** da senha, em **Base64 padrão** com padding, sem salt
e sem `trim`. O instalador semeia `admin` com
`C4wx3TpMHnSwdk1bUQ/V6qwAQmw=`, que é exatamente o hash de `abracadabra` — a
senha pública do instalador, que vale trocar antes de expor a instalação.

O que a tabela **não** tem, e que muda o desenho:

- **não há coluna `name`.** O nome mostrado vem de `users`, pelo
  `LEFT JOIN users U ON U.login_id = L.id` com `coalesce(U.name, L.login)`.
  Funcionário sem ficha de leitor aparece com o próprio login;
- **não há coluna de status.** Desativar alguém no BibLivre é **apagar** a
  linha (`LoginDAO.delete` zera `users.login_id` e faz `DELETE FROM logins`).
  Não existe login desabilitado;
- **não há contador de tentativas nem expiração de senha.** Bloqueio por força
  bruta não existe no BibLivre, e nós também não implementamos — fica
  registrado como decisão consciente, não esquecimento. Se o app for exposto
  fora da LAN da biblioteca, alguma contenção passa a ser necessária.

`logins.employee` é o que separa funcionário de leitor com senha: um login com
`employee = false` sequer recebe os pontos de autorização de escopo EMPLOYEE,
entre eles `CIRCULATION_LENDING_LEND`. E `admin` é `logins.id == 1`.

> **A confirmar na instalação real:** que `logins` tem exatamente essas
> colunas, que a tabela `permissions` existe e é legível pelo papel
> `biblivre`, e se o `admin` ainda está com o hash público do instalador. Um
> `SELECT id, login, employee, password FROM logins;` responde os três.
> E a biblioteca vai precisar de **um login por pessoa de balcão** para o
> `created_by` valer a pena — hoje só existe o admin, e criar login continua
> sendo tela do BibLivre.

### A etiqueta impressa não carrega o tombo

Esta é a descoberta que mais mexe com a promessa "empresta bipando", e ela
contraria o que se supunha. `HoldingBO.printLabelsToPDF` monta a etiqueta do
exemplar com `Barcode39`, `setExtended(true)`, `setStartStopText(false)`, sem
dígito verificador — e o conteúdo da barra é
`String.valueOf(ldto.getId())` **preenchido com zeros à esquerda até 10
caracteres**. Isto é: a barra carrega o `biblio_holdings.id`, não o
`accession_number`. Um exemplar de id 842 vira a barra `0000000842`. O tombo
(`Bib.2019.842`) aparece na etiqueta só como **texto legível**.

Pior: `UserBO` imprime a carteirinha do leitor do mesmo jeito — `users.id` com
zeros à esquerda até 10 dígitos, também em Code 39. **Etiqueta de exemplar e
carteirinha de leitor são, na barra, indistinguíveis pela forma.** Nem o
celular nem o servidor conseguem separá-las olhando o texto; só consultando as
duas tabelas, e um id pequeno existe nas duas.

> **A confirmar na instalação real, e é o item mais urgente da lista:** hoje o
> `resolver` procura `accession_number` exato, tenta ISBN e depois procura
> leitor por id — então uma etiqueta impressa pelo BibLivre (`0000000842`)
> **não** cai no exemplar 842: cai no **leitor** 842, se ele existir. Bipar a
> etiqueta de um livro precisa ser testado contra uma etiqueta de verdade
> desta biblioteca, e a ordem de resolução decidida com essa informação na
> mão. Enquanto isso, os caminhos que funcionam são o ISBN da capa (que é de
> primeira classe justamente por isso), o tombo digitado e a busca por nome.

## Outros detalhes que afetam a importação

**O 001 é sobrescrito.** `BiblioRecordBO.save()` faz:

```java
Integer id = this.rdao.getNextSerial("biblio_records_id_seq");
MarcUtils.setCF001(record, id);
MarcUtils.setCF005(record);
MarcUtils.setCF008(record);
```

Qualquer identificador nosso em 001/005/008 é perdido. Por isso o
`NUMACERVO` de origem vai no **`035 $a`**, no formato `(BF)<numero>` — é o
que permite casar os exemplares com o registro certo depois da importação.

**Registros importados caem na base de trabalho.** `saveImport()` faz
`dto.setRecordDatabase(RecordDatabase.WORK)`. Depois de conferir, é preciso
movê-los para a base principal (`main`) pela própria interface — os
exemplares só são pesquisáveis em `RecordDatabase.MAIN`.

**Tipo de material.** `MaterialType.BOOK` é `('a', "m ")`, lido do Leader
posições 06 e 07-08. O `gerar_marc.py` usa o leader
`00000nam a2200000 a 4500`, que dá `a`/`m`/` ` — Livro — e posição 09 = `a`
(Unicode).

**Tombo é obrigatório e único.** `accession_number` é `NOT NULL` e
`HoldingBO` valida unicidade (`isAccessionNumberAvailable`). No acervo de
origem só 188 registros têm tombo preenchido, e nem esses são únicos —
então os tombos precisarão ser gerados no passo de exemplares.

## O formato de backup `.b5bz`

O backup do BibLivre **não é um formato de intercâmbio** — é um dump
PostgreSQL. `BackupBO.java` chama `pg_dump --format p` (texto puro) e
empacota tudo num zip:

```
Biblivre Backup AAAA-MM-DD HHhMMmSSs Full.b5bz   (zip)
├── backup.meta          JSON: {schemas, type, backup_scope, created}
├── global.schema.b5b    pg_dump --schema-only  (schema "global")
├── global.data.b5b      pg_dump --data-only
├── single.schema.b5b    pg_dump --schema-only  (schema da biblioteca)
├── single.data.b5b      pg_dump --data-only --exclude-table digital_media
├── single.media.b5b     pg_dump --data-only --table digital_media
└── single/              arquivos de mídia digital
```

Ou seja: `.b5b` é SQL. Um install de biblioteca única usa dois schemas,
`global` (configuração) e `single` (a biblioteca).

**O restore é uma substituição total, não uma fusão.** `RestoreBO`
descompacta e joga os `.b5b` num `psql --single-transaction -v
ON_ERROR_STOP=1`, depois de **renomear o schema de destino para o lado e
recriá-lo**. Com `purgeAll`, apaga também os schemas restantes. Restaurar
um `.b5bz` numa instalação que já tem dados **destrói o que estava lá**.

### Dá para montar um `.b5bz` à mão?

Tecnicamente sim — é SQL, e ele carregaria `biblio_records` **e**
`biblio_holdings` de uma vez, o que resolveria o segundo passo. Mas o
dump precisa reproduzir um schema BibLivre **completo e válido**: são
**61 tabelas**, incluindo configuração, traduções, as definições de
formulário MARC (`biblio_form_datafields`, `biblio_form_subfields`),
`biblio_brief_formats`, os grupos de indexação e as tabelas de índice
(`biblio_idx_fields`, `biblio_idx_sort`, `biblio_idx_autocomplete`) que
fazem a busca funcionar — além das sequences no valor certo.

Com `ON_ERROR_STOP=1`, qualquer detalhe errado aborta tudo. E como o
restore já destruiu o schema de destino, o erro não é parcial.

**Não vale a pena montar à mão.** O caminho abaixo entrega o mesmo
arquivo único, deixando o BibLivre construir as partes arriscadas.

## Por que os registros também entram por SQL

O plano inicial era importar `obras.mrc` pela tela e só os exemplares por
SQL. Ao rodar contra uma instância real, dois fatos derrubaram a rota pela
tela para os 14.866 registros:

1. **O upload devolve tudo num JSON só.** `Handler.importUpload` parseia o
   arquivo inteiro e manda a lista completa de registros de volta ao
   navegador; `save_import` depois **reenvia o MARC de cada registro** como
   parâmetro `marc_<i>`. O Tomcat do instalador roda com heap de **256 MB**
   (`JvmMx`), e 14.866 registros nessa ida-e-volta é frágil.
2. **Não existe "mover todos".** A importação salva na base de trabalho
   (`RecordDatabase.WORK`); `CatalogingHandler.moveRecords` recebe uma lista
   de ids montada clicando registro por registro nos resultados paginados.
   Mover 14.866 à mão é inviável.

Como um passo em SQL era inevitável de qualquer forma, o `inserir_obras.py`
carrega os registros direto em `biblio_records`, já na base **principal**,
reproduzindo `BiblioRecordBO.save` (id da sequence, `001` de 7 dígitos,
`005`, `008`, `material='book'`). Isso foi **validado**: importando 25
registros pela tela e comparando com o que o script gera, a saída é
**byte a byte idêntica** (o Leader difere só nas posições de tamanho e
endereço-base, que a serialização recalcula).

## Roteiro de importação (executado e validado)

A ideia é montar o acervo uma vez numa instância de teste e usar o
backup **gerado pelo próprio BibLivre** como o arquivo único de
implantação. Todos os passos abaixo foram rodados contra uma instância
real (Windows, BibLivre 5.0.x, PostgreSQL 9.1, Tomcat 7).

> As cargas em SQL deste roteiro também rodam pela tela `/migracao`, num clique
> e numa transação só — ver `biblio.migracao` e a seção 9 de
> [SPEC_UI.md](SPEC_UI.md). O que está aqui continua sendo a referência do
> **porquê** de cada passo, e é o caminho de quem precisa parar entre um e outro.

**Na instância de teste:**

1. **Instalar o BibLivre 5 limpo** — o instalador de Windows, baixado em
   [biblivre.org.br](https://biblivre.org.br/index.php/baixar/category/5-biblivre-5),
   traz Apache HTTPd, Tomcat e PostgreSQL de uma vez. Login inicial:
   `admin` / `abracadabra` (SHA-1+Base64 em `logins.password`); troque
   depois. Schema da biblioteca: `single`.

2. *(opcional, mas recomendado)* **Validar o formato com uma amostra.**
   Gerar um `.mrc` pequeno, importar pela tela (Catalogação → Importação de
   Registros, **ISO 2709**, **UTF-8**, "Importar todos") e comparar com o
   banco. Foi assim que se confirmou o contrato de `001/005/008/material`.
   Apagar a amostra e zerar as sequences antes da carga real:

   ```sql
   DELETE FROM biblio_idx_fields; DELETE FROM biblio_idx_sort;
   DELETE FROM biblio_idx_autocomplete; DELETE FROM biblio_holdings;
   DELETE FROM biblio_records;
   SELECT setval('biblio_records_id_seq', 1, false);
   SELECT setval('biblio_holdings_id_seq', 1, false);
   ```

3. **Carregar os registros bibliográficos** com o `inserir_obras.py`
   (entra direto em `main`, dispensando o passo de mover da base de
   trabalho):

   ```bash
   # relatório, sem escrever nada (não consome a sequence)
   python scripts/inserir_obras.py saida/obras.mrc

   # grava, numa transação só
   python scripts/inserir_obras.py saida/obras.mrc --executar \
       --mapa-out saida/obras_mapa.csv
   ```

4. **Reindexar** — Administração → Manutenção → **Reindexar base
   bibliográfica**. *(Hoje também é um botão do app:
   `POST /api/manutencao/reindexar` — ver "Os passos manuais que viraram
   botão", no fim deste documento.)* Inserção por SQL não passa pelo indexador, então sem
   isto os registros existem mas não aparecem na busca. O reindex lê
   `biblio_records` em lotes de 30 (`IndexingBO.reindex`), seguro para o
   heap de 256 MB. Só a base bibliográfica precisa; autoridades e
   vocabulário ficam vazias. `biblio_idx_autocomplete` nasce em **0** e
   isso é correto: a configuração de formulário padrão não tem nenhum
   subcampo do tipo `previous_values`/`fixed_table_with_previous_values`,
   os únicos que alimentam essa tabela (`Fields.loadAutocompleteSubFields`).

5. **Criar os exemplares** com o `inserir_exemplares.py`, que casa cada
   linha do `exemplares.csv` com `biblio_records.id` pelo `035 $a` e insere
   em `biblio_holdings`:

   ```bash
   # relatório, sem escrever nada
   python scripts/inserir_exemplares.py saida/exemplares.csv

   # grava, numa transação só
   python scripts/inserir_exemplares.py saida/exemplares.csv --executar \
       --biblioteca "Nome da Biblioteca" --mapa-out saida/exemplares_mapa.csv
   ```

   Sem `--executar` ele só relata: quantos exemplares casaram, quantos
   registros ficariam sem exemplar, os tombos por ano e o primeiro exemplar
   em MARC legível. Recusa rodar se `biblio_holdings` já tiver linhas (para
   não duplicar) e aborta se algum tombo gerado colidir com o índice UNIQUE.
   **Não precisa reindexar de novo:** exemplar não tem tabela de índice (ver
   acima).

6. **Conferir na interface** — buscar no catálogo, abrir uma obra e ver a
   aba Exemplares, imprimir uma etiqueta de teste e simular um empréstimo.

7. **Carregar os leitores** com o `inserir_leitores.py`. Ele cria os campos que
   faltam em `users_fields` (com as traduções), desmarca o `required` do email
   e preserva o `NUMLEITOR` como `users.id`:

   ```bash
   # relatório, sem escrever nada
   python scripts/inserir_leitores.py saida

   # grava, numa transação só
   python scripts/inserir_leitores.py saida --executar \
       --mapa-out saida/leitores_mapa.csv
   ```

   O usuário e o empréstimo de teste do passo 6 precisam ser apagados antes
   (`users.id` 1 é o primeiro leitor da origem), ou use `--offset-id`. Depois
   **reinicie o Tomcat**: `UserFields` e `Translations` são caches estáticos.
   *Este é o único passo que continua manual, e o motivo está no fim deste
   documento: nenhuma ação por HTTP derruba o cache de campos de leitor.*

8. **Carregar a circulação** com o `inserir_emprestimos.py`, que junta
   `T13_MOVM` + `T11_MOVI` e resolve o exemplar pelo tombo:

   ```bash
   python scripts/inserir_emprestimos.py saida
   python scripts/inserir_emprestimos.py saida --executar
   ```

   Padrões: histórico completo (o `--apenas-abertos` limita aos não
   devolvidos), sem as 113 movimentações apagadas na origem, e só as reservas
   pendentes de 2026 em diante (`--reservas-desde`).

9. **Administração → Backup → Full**, que produz o `.b5bz`. *(Também é um
   botão do app: `POST /api/manutencao/backup`.)*

**Na máquina final:** restaurar esse `.b5bz`. Um arquivo, uma operação,
com exemplares e tudo mais dentro. O restore **apaga o schema de destino** —
desejável numa implantação inicial em máquina limpa, perigoso sobre uma
instalação que já tem dados.

**Resultado da carga real:** 14.866 registros em `biblio_records` (base
`main`) e 16.251 exemplares em `biblio_holdings`, com integridade
referencial verificada (0 holdings órfãos, 0 obras sem exemplar, 16.251
tombos únicos).

Conexão do banco, para os passos SQL: `PGDATABASE=biblivre4`,
`PGUSER=biblivre`, porta 5432, schema `single` (`Constants.SINGLE_SCHEMA`).
A senha do papel `biblivre` está no `WebContent/META-INF/context.xml` do
projeto e é a mesma que o hash MD5 de `sql/createdatabase.sql` — um default
público do BibLivre (`abracadabra`), que vale trocar antes de expor a
instalação. Na máquina instalada, o valor em vigor é o do `context.xml` sob
o Tomcat. O instalador não põe o `psql` no PATH — daí os passos SQL serem
Python com `psycopg2`, e não scripts de linha de comando.

## Os passos manuais que viraram botão

O roteiro acima termina em três instruções de papel — reindexar, reiniciar o
Tomcat, conferir — e depois num quarto passo de tela, o backup. Instrução de
papel no fim de um processo longo é a que mais se esquece, e o esquecimento
mais caro é o do reindex: o catálogo **existe**, a aba Exemplares mostra tudo,
o livro é emprestável pelo tombo, e a busca não acha nada. Ninguém descobre
isso sem procurar um título de cor.

Por isso o app passou a fazer esses passos, e não por comodidade. O canal é
**HTTP contra o próprio BibLivre** (logado como admin), nunca uma
reimplementação: reproduzir o indexador seria copiar a tokenização Java do
`IndexingBO`, e índice errado falha em silêncio. O que muda de canal é só quem
aperta o botão.

| Passo do roteiro | Hoje | Como, e o que foi verificado no fonte |
|---|---|---|
| **4. Reindexar** | `POST /api/manutencao/reindexar` + `GET` da mesma rota para o progresso | ações `reindex` (parâmetro `record_type`, default `biblio`) e `progress` de `administration/indexing/Handler.java`. `progress` devolve `{success, current, total, complete}`. O `IndexingBO.reindex` limpa os índices e relê `biblio_records` em lotes de 30, com lock `volatile` por tipo de registro — duas chamadas em paralelo fazem a segunda voltar **calada, sem indexar nada**, e por isso a segunda vira 409 aqui |
| **6. Conferir na interface** | `POST /api/manutencao/conferencia` (ou `python scripts/conferir.py`) | 26 checagens em SQL puro, só leitura: índice, as quatro sequences, 12 de integridade referencial e 9 contagens informativas. Ver a §11 do [SPEC_UI.md](SPEC_UI.md) |
| **7. Reiniciar o Tomcat** | **continua manual**, e o botão de caches diz isso | `UserFields.reset()` só é alcançado por `StaticBO.resetCache()`, cujos três chamadores são destrutivos (restore, `importBiblivre3`, `deleteSchema`). Nenhuma ação por HTTP derruba o cache de campos de leitor. O que dá é a tradução: `administration/translations/Handler.java`, ação `list`, chama `Languages.reset` e `Translations.reset` |
| **9. Backup Full** | `POST /api/manutencao/backup` + `GET` para o progresso e a URL | três ações em sequência em `administration/backup`: `prepare` (parâmetro `type`, um de `full`, `exclude_digital_media`, `digital_media_only`; devolve `{success, id}`), `backup` (parâmetro `id`, **síncrono** — roda o `pg_dump` e só responde no fim) e `progress`. O arquivo se recupera por `controller=download`, não `json` |
| **Restore do `.b5bz`** | **continua no BibLivre**, e continua destrutivo | `RestoreBO` renomeia o schema de destino para o lado e recria — ver "O formato de backup `.b5bz`", acima |

O que a conferência **não** substitui: a parte de papel do passo 6. Imprimir
uma etiqueta de teste e ver se a impressora e o leitor da biblioteca leem o que
saiu é conferência física, e nenhuma automação responde isso.

### O que a conferência responde e a tela do BibLivre não

`biblio_records` sem linha em `biblio_idx_fields` é a **única resposta
objetiva** para "o reindex funcionou?". Inserir por SQL não passa pelo
indexador (`BiblioRecordBO.save` chama o `IndexingBO`; o nosso
`obras.inserir` não), e o sintoma é traiçoeiro justamente porque tudo o mais
funciona. Um catálogo de 14.866 obras invisível na busca é um acervo perdido —
e o `.b5bz` empacota o índice vazio junto, levando o problema para a máquina
final.

### Como o canal HTTP funciona (e o que confirmar)

Um servlet só, mapeado em `/`. A URL é
`<base>?controller=json&module=<pacote>&action=<método>` — a forma que o
próprio fonte documenta em comentário. O `module` vira
`Class.forName("biblivre." + module + ".Handler")` e o `action` vira o método,
em camelCase. O **schema** sai do primeiro segmento do path depois do
contexto; sem segmento, uma instalação de biblioteca única cai em
`Constants.SINGLE_SCHEMA` (`single`). Ou seja: a URL base configurada é quem
escolhe o schema — `.../Biblivre5/` numa instalação única,
`.../Biblivre5/<schema>/` numa multi-biblioteca.

A sessão é a do Tomcat (cookie `JSESSIONID`), obtida pela ação `login` do
módulo `login`, que lê `username` e `password` e nada mais. Sem sessão, o
`JsonController` responde `{"success": false, "message":
"<error.no_permission>", "message_level": "warning"}` — é essa a assinatura de
sessão expirada que o app reconhece para relogar e repetir a chamada uma vez.

A credencial de admin segue a regra da senha do Postgres: **memória, nunca
disco, nunca de volta na resposta**, e viaja no corpo do POST — nunca na query
string, para não cair no access log do Tomcat.

> **A confirmar contra o WAR instalado** (tudo acima foi lido num fork no
> GitHub; a biblioteca roda um 5.0.x do instalador de Windows): o contexto da
> URL (`/Biblivre5/` é o padrão do instalador, mas é configurável), o nome do
> schema, e se a ação `administration.translations/list` responde JSON numa
> base com muitas traduções — ela devolve o mapa inteiro, que é grande. Nada
> aqui depende do tamanho da resposta, só do `success`.

Uma consequência de desenho que vale escrever: **toda** rota de manutenção
exige operador identificado, e a sessão de operador é autenticada contra
`logins`, no Postgres. Logo, com o Postgres fora do ar não há como disparar
reindex nem backup pela API — o caminho de socorro continua sendo a tela do
próprio BibLivre. A alternativa (deixar aberto na LAN um botão que produz um
`.b5bz` com nome, CPF e endereço de todos os leitores, com URL de download)
seria pior.
