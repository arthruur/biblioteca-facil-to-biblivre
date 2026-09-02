# biblioteca-facil-to-biblivre

Migração **Biblioteca Fácil → Biblivre 5** (14.880 obras / 16.251 exemplares validados) + **MVP de Catalogação por ISBN** com lote, ZXing e export integrado.

> **Status:** Migração validada byte-a-byte (`docs/IMPORTACAO_BIBLIVRE.md`). MVP em `https://<ip>:8000` após `docker compose up` — ver abaixo.

## 1) MVP Catalogação ISBN — o que entrega

Fluxo validado em campo (ex.: `9786559870530` → *2041*, Globo Livros via `BrasilAPI/CBL`):

**Celular:** `Escanear` (ZXing `TRY_HARDER` EAN-13 em tempo real) → **Lote** (galeria que acumula, padrão scanner de documentos, debounce 2s) → clique para ver ficha completa (capa, descrição, ISBN, CDD/Cutter editáveis) e ajustar **Exemplares ×N** → **Foto** (fallback `scanFile`) → **Manual** (ISBN 10/13) → **Enviar lote para fila**

**Dedup por ISBN:** antes de gerar qualquer MARC, cada ISBN é confrontado com o acervo já catalogado (`scripts/catalogacao/acervo.py` indexa 020 $a de `biblio_records` — ~10.5 mil ISBNs em <1s, com equivalência ISBN-10 ↔ ISBN-13). Livro que já existe **não vira ficha nova**: entra como exemplar a mais no `record_id` que já está lá. Sem isso, reescanear o acervo duplicaria o catálogo.

**Fila (`/fila`) — dashboard de revisão:** persiste em `data/fila/*.json` e sobrevive a reinício. Indicadores (a exportar / pendentes / revisados / obras novas / já no acervo / precisam de atenção), busca, filtro por situação, ordenação, edição embutida de 12 campos, ações em lote (revisado/pendente/ignorar/remover), stepper de exemplares e export dos selecionados. **Exportar** gera `data/export/obras_<ts>.mrc` + `exemplares_<ts>.csv` via `scripts/gerar_marc.py` (`chave_obra` conservadora) e, com senha, grava em `single.biblio_records/holdings` numa transação só (`Bib.<ano>.<seq>` continuando do maior existente). Reindexar só é pedido quando nasceu obra nova.

Ver [docs/SPEC_UI.md](docs/SPEC_UI.md) para a spec das telas.

Fallback robusto: ZXing falha 5× → Tesseract.js (OCR-B abaixo do código, `eng` `psm 7`, valida dígito ISBN-13).

```
Celular (ZXing) --ISBN--> /api/lote --lookup--> Google Books → BrasilAPI → Open Library
                                    --acervo--> ISBN já catalogado?
                                                 ├── não → obra nova  (biblio_records + N holdings)
                                                 └── sim → só exemplar (N holdings no record_id existente)
PC /fila (revisão) --------> /api/fila/exportar-biblivre --> Biblivre 5
```

Para ligar a checagem de duplicata é preciso dar ao servidor acesso ao Postgres do Biblivre — pela tela `/fila`, por `--db-senha`, ou por `PGPASSWORD`/`BIBLIVRE_DB_SENHA`:

```bash
python scripts/servidor.py --db-senha SUA_SENHA
```

Sem isso o app funciona igual, mas trata todo livro como obra nova — e a tela avisa disso em vez de degradar em silêncio.

## 2) Implantação rápida (recomendado: container)

**Pré-requisitos:** Docker + Docker Compose.

```bash
# 1. Build + sobe (gera cert auto-assinado em data/certs)
docker compose up --build

# 2. Abra no celular (mesma rede)
# https://<IP-DO-PC>:8000  (aceite o certificado)
# Teste: Escanear → aponte para código de barras → Lote → Enviar → /fila → Exportar
```

* Imagem `python:3.11-slim` + `tesseract-ocr` + `tesseract-ocr-por` + `libgl1` (`Dockerfile:6`). `TESSERACT_CMD=/usr/bin/tesseract` no Linux (fallback do path Windows).
* `docker-compose.yml` sobe `app:8000` + `postgres:15` demo (remova `db` e aponte `PGHOST` para o Postgres do Biblivre em produção).
* Volumes: `./data:/app/data` persiste `fila/*.json` e `export/*.mrc`.

**Sem Docker (dev local):**
```bash
pip install -r requirements.txt  # opencv, pymarc, fastapi, uvicorn, qrcode, psycopg2, pytesseract
# Instale Tesseract + por.traineddata (Windows: tesseract-ocr-w64-setup + por.traineddata em tessdata)
python scripts/servidor.py  # https://0.0.0.0:8000
# HTTP apenas em localhost:
python scripts/servidor.py --sem-ssl --porta 8000
```

**Produção B2G:** atrás de Nginx com Let's Encrypt (troca cert auto-assinado), `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` via env, `restart: unless-stopped`.

## 3) Migração legada (uso rápido)

```bash
pip install -r requirements.txt

python scripts/extrair_bkp.py backup.bkp saida/
python scripts/extrair_tabela.py saida/ --listar
python scripts/extrair_tabela.py saida/ T09_ACER.dat acervo.csv
python scripts/consolidar.py saida/ acervo_consolidado.csv
python scripts/gerar_marc.py acervo_consolidado.csv obras.mrc  # + exemplares.csv
python scripts/inserir_obras.py obras.mrc --executar           # -> Reindexar
python scripts/inserir_exemplares.py exemplares.csv --executar
python scripts/inserir_leitores.py saida/ --executar           # -> reinicie Tomcat
python scripts/inserir_emprestimos.py saida/ --executar
```

Sem `--executar` é dry-run. Detalhe byte-a-byte e por que importação por arquivo não cria holdings em `docs/IMPORTACAO_BIBLIVRE.md`.

## 4) Estrutura

```
scripts/
  extrair_bkp.py, bf_tabela.py, extrair_tabela.py, consolidar.py
  gerar_marc.py, inserir_obras.py, inserir_exemplares.py, inserir_leitores.py, inserir_emprestimos.py
  detectar_ficha.py, extrair_isbn.py, gerar_ficha_sintetica.py
  servidor.py (140 linhas) + catalogacao/ (config, lookup, ficha, fila, export, rede, cert)
static/ index.html (scanner Lote + modal + Foto/Manual)  fila.html (Exportar)
docs/  FORMATO_BKP.md  TABELAS.md  IMPORTACAO_BIBLIVRE.md  ROADMAP.md  CATALOGACAO_POR_FOTO.md  NOTA_SESSAO_2026-09-01.md
Dockerfile  docker-compose.yml
```

## 5) Estratégia de conteinerização (estado atual)

**Decisão:** containerizar **apenas o MVP** (app Python). Biblivre 5 permanece no instalador Windows/Java-Tomcat-Postgres (61 tabelas, restore `.b5bz` destrutivo) — não vale replicar no Compose para produção. Para demo, o `db` Postgres no compose simula o alvo.

* Build leve: `python:3.11-slim` (~350MB com tesseract-por) vs `python:3.11` (~900MB).
* `tesseract-ocr-por` já na imagem — sem download em runtime; mobile envia ISBN, OCR fica no device (Tesseract.js) exceto ficha CIP (server `por`).
* Cert auto-assinado gerado em `data/certs` (volume persistido) — produção troca por volume de certs do Nginx.
* Logs: `ConnectionResetError 10054` no Windows + HTTPS é inofensivo (Proactor fecha keep-alive).

Próximo passo infra: `ghcr.io` + `docker compose pull` na FPC, backup `pg_dump` diário de `single`.

## Aviso

Dados de backup real (`.bkp`, `.csv`, `data/fila/*.json`) são pessoais — `.gitignore` já exclui. Ver `LICENSE` (MIT).
