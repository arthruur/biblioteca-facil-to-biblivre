# Nota de Sessão — 2026-09-01
## Catalogação por ISBN: Lote, ZXing + Tesseract e Export integrado ao Biblivre 5

### Objetivo da sessão
Operacionalizar a proposta de catalogação automática por ISBN (codigo de barras) com fluxo de **Lote → Fila → Biblivre 5**, validar com ISBN brasileiro e corrigir inserção direta sem travar o servidor.

### O que funcionou
- **Foto isolada** do codigo de barras decodificou corretamente (confirmou ZXing ativo).
- **ISBN 9786559870530** (`2041`, Globo Livros) passou a resolver após incluir **BrasilAPI/CBL** — antes Google 429 + Open Library 404 → `nao_encontrado`. Agora `BrasilAPI/CBL` retorna capa/titulo/autor/ano/paginas.
- **Export → Reindex** funcionou: `2 exemplares no CSV`, `INSERT INTO single.biblio_records/holdings` + **Administração → Manutenção → Reindexar** → obras aparecem no catálogo com exemplares emprestáveis.

### Mudanças implementadas
**ZXing com TRY_HARDER + Fallback OCR**
- `static/index.html:232` — `Html5Qrcode` com `formatsToSupport:[EAN_13, EAN_8, UPC_A, UPC_E, CODE_128, CODE_39]` e `experimentalFeatures:{useBarCodeDetectorIfSupported:false}`. `TRY_HARDER` força varredura em múltiplas alturas/ângulos para desviar de vinco/dano superficial.
- Fallback após 5 falhas: captura frame do `<video>`, recorta faixa inferior (números OCR-B), upscale 2× + binarização, `Tesseract.js@5` (`eng`, `whitelist 0-9`, `psm 7`), regex `\d{13}` + validação dígito ISBN-13. Throttle `ocrEmAndamento` evita sobrecarga.

**Lote (antes “Carrinho”) — padrão scanner de documentos**
- Renomeado: `Carrinho → Lote` (alias `/api/carrinho` mantido). Novo `scripts/catalogacao/` (140 linhas `servidor.py` vs 382): `config.py`, `lookup.py`, `ficha.py`, `fila.py`, `rede.py`, `cert.py`, `export.py`.
- Galeria horizontal que **acumula** sem parar o scanner (duplicação via `Set vistos` + dedup no servidor). Click no card abre **modal** com ficha completa (capa, titulo/subtitulo, autor, editora, ano, paginas, idioma, descricao, ISBN, fonte, CDD/Cutter editáveis) e botão Remover.
- Foto direta (`#foto-teste` → `scanFile`) e **entrada manual** (`#manual-input` + `validarISBN` 10/13 + Enter) caem no mesmo `POST /api/lote {isbn}`.

**Export integrado ao pipeline existente**
- `scripts/catalogacao/export.py:49` `exportar_itens()` reaproveita `scripts/gerar_marc.py:172` `montar_registro()` + `chave_obra()` (agrupamento conservador por conteúdo) para gerar `data/export/obras_<ts>.mrc` + `exemplares_<ts>.csv` (`numacervo` base 900000).
- `scripts/servidor.py:89` `POST /api/fila/exportar-biblivre {executar, db:{senha}}` — com `executar:false` só gera arquivos; com `true` insere direto via `biblio.biblivre.obras` (`001/005/008`, `biblio_records`) e `biblio.biblivre.exemplares` (`biblio_holdings`).
- **Senha no frontend**: `apps/web` (tela de revisão) checkbox + input `password` (`#senha-box`). `export.py:117` exige `db.senha`; se ausente retorna `senha_requerida` sem `getpass` (antes bloqueava o Uvicorn com `Senha de biblivre@localhost:` + `UnicodeDecodeError 0xe7`). Exemplares agora herdam `PGPASSWORD`/`--senha` no subprocess (`export.py:183`).
- Listagem `/fila` mostra Lote + Fila e botão **Exportar para Biblivre 5** com download de JSON de conferência.

**Lookup**
- `scripts/catalogacao/lookup.py:71` ordem `Google Books → BrasilAPI/CBL → Open Library`. Essencial para 97865* brasileiros.

### Como conferir no catálogo (validado)
1. Celular `https://<ip>:8000` → Escanear/Foto/Manual → Lote → **Enviar para fila** → `/fila` → **Exportar para Biblivre 5** (marcar *Inserir direto* + senha) → `Inseridos N registro(s)`
2. **Administração → Manutenção → Reindexar** (sem isso não aparece na busca)
3. `Busca` por título/ISBN → obra → aba **Exemplares** (tombo `Bib.<ano>.<n>`)

Manual (se sem `executar`):
```bash
python scripts/inserir_obras.py data/export/obras_*.mrc --executar
# Reindexar
python scripts/inserir_exemplares.py data/export/exemplares_*.csv --executar --senha SUA_SENHA
```

### Logs da sessão
```
POST /api/lote 200 OK → GET /api/lote 200 → POST /api/lote/enviar 200 → POST /api/fila/exportar-biblivre 200 → 2 exemplares no CSV
Antes: prompt terminal + UnicodeDecodeError 0xe7 em inserir_exemplares + ConnectionResetError 10054 (Windows Proactor, inofensivo)
Depois: senha via modal, sem prompt, gerado_sem_inserir apenas se auth falhar
```

### Próximos passos sugeridos
- Reindex automático ou aviso mais visível pós-inserção
- Pagina `/fila` com edição inline de CDD/Cutter antes de exportar
- Teste de campo com códigos com vinco para medir ganho TRY_HARDER + OCR
