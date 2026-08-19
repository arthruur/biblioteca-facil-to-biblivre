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

## 🚧 Próximos passos

Falta executar a carga de circulação e empacotar. O `.b5bz` é um dump
PostgreSQL e carrega tudo junto — montá-lo à mão exigiria reproduzir 61
tabelas de schema válido, então deixamos o BibLivre gerá-lo. Ver
[IMPORTACAO_BIBLIVRE.md](IMPORTACAO_BIBLIVRE.md).

- [x] Conferir na interface: busca no catálogo, aba Exemplares de uma obra,
      etiqueta de teste e um empréstimo de teste (feito e devolvido)
- [ ] Apagar o usuário e o empréstimo de teste (o `users.id` 1 é o primeiro
      leitor da origem)
- [ ] Rodar `inserir_leitores.py --executar` e **reiniciar o Tomcat**
      (`UserFields`/`Translations` são caches estáticos)
- [ ] Rodar `inserir_emprestimos.py --executar`
- [ ] Conferir na interface: ficha de um leitor, lista de atrasos de quem tem
      pendência, relatório de devoluções em atraso
- [ ] Gerar o `.b5bz` (Administração → Backup → Full) — o backup só do acervo,
      gerado antes da circulação, vira ponto de retorno
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

## Circulação: o que entra e o que não entra

A circulação entrou no escopo depois do acervo, com estas decisões:

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
