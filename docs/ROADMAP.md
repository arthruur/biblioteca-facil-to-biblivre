# Roadmap

## ✅ Feito

- [x] Decodificar o container `.bkp` (zlib + 16 tabelas Paradox)
- [x] Extrair Título, CDD, Cutter e Ano de edição do Acervo
- [x] Extrair Nome de Autores

## 🚧 Próximos passos

- [ ] Mapear ISBN, Tombo, Páginas, CDU no Acervo
- [ ] Descobrir o vínculo Autor↔Livro (investigar `T10_AUAC` primeiro —
      pelo nome, parece ser exatamente a tabela de relacionamento)
- [ ] Mapear Editoras (`T06_EDIT`) — nome, seguindo o mesmo processo de
      Autores
- [ ] Cruzar Acervo + Autores + Editoras num único CSV/DataFrame
      (`pandas`), já no formato final que vai virar um registro
      bibliográfico
- [ ] Escrever `gerar_marc.py`: ler o CSV consolidado e gerar um arquivo
      `.mrc` (MARC21 / ISO 2709, UTF-8) usando `pymarc`, mapeando:
      - Título → tag 245
      - Autor → tag 100 (autor principal) / 700 (autores secundários)
      - Editora + Ano → tag 260
      - ISBN → tag 020
      - CDD → tag 082
- [ ] Testar a importação do `.mrc` gerado num BibLivre 5 de teste
      (Catalogação → Importação de Registros)
- [ ] Documentar quaisquer ajustes necessários depois do teste real de
      importação (encoding, campos obrigatórios do BibLivre, etc.)

## Por que MARC21/ISO 2709 e não XML ou texto simples

O BibLivre 5 aceita três formatos de importação: texto, XML ou ISO 2709.
Optamos por ISO 2709 (MARC21, codificado em UTF-8) porque existe uma
biblioteca Python madura (`pymarc`) que cuida de toda a formatação
binária exigida pelo padrão — reduz a superfície de erro comparado a
montar o XML MARCXML à mão.
