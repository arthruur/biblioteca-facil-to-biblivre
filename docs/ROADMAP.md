# Roadmap

## ✅ Feito

- [x] Decodificar o container `.bkp` (zlib + 16 tabelas)
- [x] **Decodificar o cabeçalho dos `.dat`** — cada arquivo traz um
      catálogo com nome, tipo, tamanho e offset de todos os seus campos.
      Isso tornou desnecessária a caça manual de offsets e resolveu de uma
      vez o mapeamento das 16 tabelas. Ver [TABELAS.md](TABELAS.md).
- [x] Leitor genérico (`scripts/bf_tabela.py`) — as 16 tabelas passam no
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
- [x] `scripts/gerar_marc.py` — gera `obras.mrc` (14.866 registros
      bibliográficos, ISO 2709/UTF-8) e `exemplares.csv` (16.251 linhas)
- [x] `scripts/inserir_obras.py` — carrega `obras.mrc` direto em
      `biblio_records`, já na base principal, reproduzindo
      `BiblioRecordBO.save` (id da sequence, `001` de 7 dígitos, `005`,
      `008`, `material='book'`). Validado byte a byte contra 25 registros
      importados pela tela. Nasceu porque a importação pela tela não escala
      para 14.866 registros no heap de 256 MB do Tomcat e não tem "mover
      todos" — ver [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).
- [x] `scripts/inserir_exemplares.py` — o passo dos exemplares: casa cada
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

## 🚧 Próximos passos

Falta só empacotar e implantar. O `.b5bz` é um dump PostgreSQL e carrega
registros + exemplares juntos — montá-lo à mão exigiria reproduzir 61
tabelas de schema válido, então deixamos o BibLivre gerá-lo. Ver
[IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).

- [ ] Conferir na interface: busca no catálogo, aba Exemplares de uma obra,
      impressão de etiqueta de teste e um empréstimo de teste
- [ ] Gerar o `.b5bz` (Administração → Backup → Full)
- [ ] Restaurar o `.b5bz` na máquina final (o restore **apaga** o schema de
      destino — ok em máquina limpa, perigoso sobre dados existentes)

Reindexar exemplares **não** entra na lista: exemplar não tem tabela de
índice no BibLivre, e a busca por tombo é subconsulta ao vivo em
`biblio_holdings`. Ver [IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).

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

## Dados que ficam de fora

A migração cobre o acervo bibliográfico. **Não** estão no escopo:
leitores (`T04_LEIT`, 2.743 pessoas — dados pessoais), empréstimos
(`T13_MOVM`), movimentações (`T11_MOVI`) e reservas (`T15_RESE`). Se o
histórico de circulação precisar ir junto, é um segundo projeto — o
leitor genérico já decodifica essas tabelas.

## Por que MARC21/ISO 2709 e não XML ou texto simples

O BibLivre 5 aceita três formatos de importação: texto, XML ou ISO 2709.
Optamos por ISO 2709 (MARC21, codificado em UTF-8) porque existe uma
biblioteca Python madura (`pymarc`) que cuida de toda a formatação
binária exigida pelo padrão — reduz a superfície de erro comparado a
montar o XML MARCXML à mão.
