# biblioteca-facil-to-biblivre

Engenharia reversa do formato de backup `.bkp` do software **Biblioteca
Fácil**, com o objetivo de migrar o acervo para o **BibLivre 5**.

> Status: 🚧 em andamento. Ver [docs/ROADMAP.md](docs/ROADMAP.md) para o
> que já funciona e o que falta.

## Por que isso existe

O Biblioteca Fácil não documenta o formato do seu backup, e não existe
exportação oficial para MARC21/ISO 2709 (o formato que o BibLivre importa).
Este repositório documenta o processo de descobrir o formato do zero —
container, compressão e layout de registros — e as ferramentas resultantes
para extrair os dados.

## O que já foi descoberto

- O `.bkp` é um **container proprietário** que empacota 16 tabelas
  **Paradox** (pares `.dat`/`.idx`), comprimidas em blocos **zlib**.
  Ver [docs/FORMATO_BKP.md](docs/FORMATO_BKP.md).
- Layout de registro (offsets de campo) mapeado parcialmente para as
  tabelas **Acervo** (livros) e **Autores**.
  Ver [docs/TABELAS.md](docs/TABELAS.md).

## Uso rápido

```bash
pip install -r requirements.txt

# 1. Descompacta o .bkp nas tabelas Paradox originais
python scripts/extrair_bkp.py caminho/para/backup.bkp saida/

# 2. Extrai os registros já mapeados para CSV
python scripts/extrair_acervo.py saida/
python scripts/extrair_autores.py saida/
```

## Estrutura

```
scripts/          scripts de extração
docs/
  FORMATO_BKP.md   engenharia reversa do container .bkp
  TABELAS.md       offsets de campo mapeados por tabela
  ROADMAP.md       o que falta até a importação no BibLivre
```

## Aviso importante

Os dados extraídos de um backup real (nomes de leitores, usuários etc.)
**não devem ser commitados** neste repositório — são dados pessoais. O
`.gitignore` já exclui `.bkp`, `.csv` e tabelas extraídas por padrão.

## Licença

MIT — ver [LICENSE](LICENSE).
