# biblioteca-facil-to-biblivre

Engenharia reversa do formato de backup `.bkp` do software **Biblioteca
Fácil**, com o objetivo de migrar o acervo e a circulação (leitores,
empréstimos, reservas) para o **BibLivre 5**.

> Status: 🚧 em andamento. Ver [docs/ROADMAP.md](docs/ROADMAP.md) para o
> que já funciona e o que falta.

## Por que isso existe

O Biblioteca Fácil não documenta o formato do seu backup, e não existe
exportação oficial para MARC21/ISO 2709 (o formato que o BibLivre importa).
Este repositório documenta o processo de descobrir o formato do zero —
container, compressão e layout de registros — e as ferramentas resultantes
para extrair os dados.

## O que já foi descoberto

- O `.bkp` é um **container proprietário** que empacota 16 tabelas (pares
  `.dat`/`.idx`), comprimidas em blocos **zlib**.
  Ver [docs/FORMATO_BKP.md](docs/FORMATO_BKP.md).
- Os `.dat` **não são Paradox**, apesar da cara de aplicativo Delphi da
  época. São um formato próprio — e, felizmente, **auto-descritivo**:
  cada arquivo traz no cabeçalho um catálogo com nome, tipo, tamanho e
  offset de todos os seus campos. Com isso, as **16 tabelas estão
  completamente decodificadas**. Ver [docs/TABELAS.md](docs/TABELAS.md).

## Uso rápido

```bash
pip install -r requirements.txt

# 1. Descompacta o .bkp nas tabelas originais
python scripts/extrair_bkp.py caminho/para/backup.bkp saida/

# 2. Mostra o layout de todas as tabelas
python scripts/extrair_tabela.py saida/ --listar

# 3. Exporta uma tabela qualquer para CSV
python scripts/extrair_tabela.py saida/ T09_ACER.dat acervo.csv

# 4. Gera o CSV consolidado (acervo + autores + editoras + idiomas...)
python scripts/consolidar.py saida/ acervo_consolidado.csv

# 5. Gera o MARC21/ISO 2709 + o CSV de exemplares
python scripts/gerar_marc.py acervo_consolidado.csv obras.mrc

# 6. Carrega os registros no banco do BibLivre (base principal)
#    Sem --executar é só relatório; não escreve nada.
python scripts/inserir_obras.py obras.mrc --executar
#    -> agora Reindexe pela tela: Administração → Manutenção → base bibliográfica

# 7. Cria os exemplares (holdings) no banco do BibLivre
python scripts/inserir_exemplares.py exemplares.csv --executar

# 8. Carrega os leitores (cria os campos que faltam em users_fields)
#    -> depois reinicie o Tomcat: UserFields/Translations são caches estáticos
python scripts/inserir_leitores.py saida/ --executar --mapa-out saida/leitores_mapa.csv

# 9. Carrega empréstimos, multas e reservas
python scripts/inserir_emprestimos.py saida/ --executar
```

`obras.mrc` é o MARC21/ISO 2709 do acervo; `exemplares.csv` é 1 linha por
cópia física. A carga é feita **direto no banco** do BibLivre por dois
motivos apurados no código-fonte: a importação pela tela não escala para
~15 mil registros no heap padrão do Tomcat (256 MB) e não tem "mover todos"
da base de trabalho para a principal; e a importação **não cria exemplares**
— sem eles o acervo não pode ser emprestado. Todo o procedimento (com a
validação byte a byte contra a tela) está em
[docs/IMPORTACAO_BIBLIVRE.md](docs/IMPORTACAO_BIBLIVRE.md).

## Estrutura

```
scripts/
  extrair_bkp.py     descompacta o container .bkp
  bf_tabela.py       leitor genérico (lê o layout do próprio cabeçalho)
  extrair_tabela.py  exporta qualquer tabela para CSV
  consolidar.py      join entre as tabelas → CSV pronto para virar MARC
  gerar_marc.py      CSV → obras.mrc (ISO 2709) + exemplares.csv
  inserir_obras.py   obras.mrc → biblio_records, no banco do BibLivre
  inserir_exemplares.py
                     exemplares.csv → biblio_holdings, no banco do BibLivre
  inserir_leitores.py    T04_LEIT → users + users_values (+ campos novos)
  inserir_emprestimos.py T13_MOVM/T11_MOVI/T15_RESE → lendings,
                     lending_fines e reservations
docs/
  FORMATO_BKP.md          engenharia reversa do container .bkp
  TABELAS.md              formato do cabeçalho e layout das 16 tabelas
  IMPORTACAO_BIBLIVRE.md  o que o BibLivre 5 aceita, apurado no código
  ROADMAP.md              o que falta até a importação no BibLivre
```

## Aviso importante

Os dados extraídos de um backup real (nomes de leitores, usuários etc.)
**não devem ser commitados** neste repositório — são dados pessoais. O
`.gitignore` já exclui `.bkp`, `.csv` e tabelas extraídas por padrão.

## Licença

MIT — ver [LICENSE](LICENSE).
