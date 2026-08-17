# Importação no BibLivre 5

Este documento registra como o BibLivre 5 realmente aceita dados, apurado
lendo o código-fonte (github.com/Biblivre/Biblivre-5). Ele existe porque a
decisão de formato do `.mrc` depende inteiramente destes detalhes.

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
   bibliográfica**. Inserção por SQL não passa pelo indexador, então sem
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

7. **Administração → Backup → Full**, que produz o `.b5bz`.

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
