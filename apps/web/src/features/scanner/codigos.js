/**
 * @fileoverview Classificação local do que o leitor entregou, no modo circulação.
 *
 * PROPOSITO:
 * Dar FEEDBACK IMEDIATO no visor — "isso parece um tombo", "isso parece um ISBN" —
 * enquanto a resposta do servidor não chega. É uma dica de interface, barata e
 * síncrona, para o visor não ficar mudo entre o bipe e a confirmação.
 *
 * QUEM DECIDE DE VERDADE É O SERVIDOR.
 * A identidade do que foi lido é resolvida por `GET /api/circulacao/resolver`, que
 * consulta o banco do BibLivre. Nada nesta tela pode tomar decisão de circulação com
 * base no que está aqui: emprestar, devolver e renovar seguem SEMPRE o `tipo` que o
 * servidor devolveu. Duas fontes de verdade divergindo — uma no celular, outra no
 * banco — seria bug garantido, e do tipo que só aparece no balcão.
 *
 * INTERFACE:
 * - normalizarCodigo(texto: string): string
 * - classificarCirculacao(texto: string): { tipo: 'tombo'|'isbn'|'numero'|'desconhecido', valor: string }
 *
 * O QUE O BIBLIVRE 5 IMPRIME NA ETIQUETA (conferido no fonte, cleydyr/Biblivre-5):
 * - `HoldingBO.printLabelsToPDF` monta a etiqueta do exemplar com
 *   `com.lowagie.text.pdf.Barcode39`, `setExtended(true)`, `setStartStopText(false)`,
 *   e o conteúdo é `String.valueOf(ldto.getId())` preenchido com zeros à esquerda até
 *   10 caracteres — ou seja, o `biblio_holdings.id`, NÃO o `accession_number`.
 *   Um exemplar de id 842 vira a barra `0000000842`.
 * - `UserBO` imprime a carteirinha do leitor do mesmo jeito: `users.id` com zeros à
 *   esquerda até 10 dígitos, também em Code 39. As duas etiquetas têm a MESMA forma.
 *   Por isso um número de 10 dígitos aqui é `numero`, e não `tombo`: localmente é
 *   impossível saber se é exemplar ou leitor — quem separa é o servidor.
 * - Sem dígito verificador: o Barcode39 é criado sem `generateChecksum`.
 * - O `accession_number` (`<prefixo>.<ano>.<contador>`, `HoldingBO.getNextAccessionNumber`)
 *   aparece na etiqueta só como texto legível, não como barra. Ele chega aqui quando a
 *   etiqueta foi impressa por outro meio, ou quando alguém digita.
 *
 * LIMITACOES:
 * - Colisão conhecida: o id do exemplar com zeros à esquerda tem 10 dígitos, e um
 *   ISBN-10 também. Um `0006470734` é ISBN-10 válido E é a cara de um id preenchido.
 *   A regra local prefere `numero` para todo código de 10 dígitos começado em zero,
 *   porque na etiqueta Code 39 do acervo essa é a leitura provável; se for mesmo um
 *   ISBN-10, o servidor corrige. Nenhuma regra local resolve essa ambiguidade.
 * - Prefixo de tombo que contenha o próprio separador (um prefixo configurado como
 *   `B.I`, por exemplo) não é reconhecido como tombo — cai em `desconhecido` e o
 *   servidor resolve.
 * - Code 39 Estendido codifica minúscula como par de deslocamento (`+B` = `b`). Um
 *   leitor que não implemente a extensão devolve o par cru; isso não é tratado aqui.
 */

import { classificarCodigo } from './isbn.js'

/**
 * Tombo do BibLivre: `<prefixo>.<ano>.<contador>`.
 *
 * O prefixo NÃO é fixo — sai da configuração `CONFIG_ACCESSION_NUMBER_PREFIX` do
 * BibLivre e é "Bib" só por padrão do instalador. Aceitamos ponto, hífen, barra ou
 * espaço como separador porque etiqueta digitada à mão varia; o `valor` devolvido é
 * sempre normalizado para a forma com ponto, que é a única que o banco guarda.
 */
const TOMBO = /^([A-Za-z0-9]{1,16})[.\-/\s]+(\d{4})[.\-/\s]+(\d{1,10})$/

/** Id de exemplar ou de leitor como o BibLivre imprime: 10 dígitos com zeros à esquerda. */
const ID_PREENCHIDO = /^0\d{9}$/

/** Um id do Postgres cabe em 10 dígitos; acima disso não é identificador de circulação. */
const NUMERO_SOLTO = /^\d{1,10}$/

/**
 * Tira a sujeira que o decodificador pode deixar no texto lido.
 *
 * Code 39 delimita o dado com `*` no início e no fim. O ZXing e o `BarcodeDetector`
 * removem os delimitadores, mas leitor USB de balcão e etiqueta impressa com fonte
 * Code 39 (o caminho mais comum fora do BibLivre) costumam devolver `*0000000842*`.
 *
 * @param {string} texto
 * @returns {string}
 */
export function normalizarCodigo(texto) {
  let bruto = String(texto ?? '').trim()
  if (bruto.length >= 2 && bruto.startsWith('*') && bruto.endsWith('*')) {
    bruto = bruto.slice(1, -1).trim()
  }
  return bruto.replace(/\s+/g, ' ')
}

function lerTombo(valor) {
  const m = TOMBO.exec(valor)
  if (!m) return null
  // A caixa do prefixo é preservada de propósito: `HoldingDAO.getByAccessionNumber`
  // compara com `=`, não com `ilike`. Trocar "Bib" por "BIB" aqui inventaria um
  // tombo que não existe no banco.
  return `${m[1]}.${m[2]}.${m[3]}`
}

/**
 * Classifica o código lido para a interface de circulação.
 *
 * Dica de UI, não decisão: veja o cabeçalho do arquivo. O `tipo` devolvido serve
 * para escolher o texto do visor e o som enquanto `GET /api/circulacao/resolver`
 * não responde.
 *
 * - `tombo`      — `<prefixo>.<ano>.<contador>`, o `accession_number`.
 * - `isbn`       — ISBN-13 (Bookland 978/979) ou ISBN-10 válido, pela regra de `isbn.js`.
 * - `numero`     — dígitos soltos: id de exemplar ou de leitor, matrícula, carteirinha.
 * - `desconhecido` — inclusive o EAN-13 de preço da contracapa, que é código de
 *   produto e não identifica nada na circulação.
 *
 * @param {string} texto
 * @returns {{ tipo: 'tombo'|'isbn'|'numero'|'desconhecido', valor: string }}
 */
export function classificarCirculacao(texto) {
  const valor = normalizarCodigo(texto)
  if (!valor) return { tipo: 'desconhecido', valor: '' }

  const tombo = lerTombo(valor)
  if (tombo) return { tipo: 'tombo', valor: tombo }

  const digitos = valor.replace(/[\s.\-]/g, '')

  // Antes do ISBN de propósito — veja a colisão documentada no cabeçalho.
  if (ID_PREENCHIDO.test(digitos)) return { tipo: 'numero', valor: digitos }

  const { tipo, codigo } = classificarCodigo(valor)
  if (tipo === 'isbn') return { tipo: 'isbn', valor: codigo }

  if (NUMERO_SOLTO.test(digitos)) return { tipo: 'numero', valor: digitos }

  return { tipo: 'desconhecido', valor }
}
