/**
 * @fileoverview Funções puras de geometria, cálculo de área e enquadramento de códigos.
 *
 * PROPOSITO:
 * Isola cálculos matemáticos de caixas delimitadoras (bounding boxes), filtros de
 * proximidade ao centro do visor (mira do alvo) e normalização de coordenadas para 0..1.
 *
 * INTERFACE:
 * - ALVO: { largura: number, altura: number }
 * - calcularArea(caixa: { width: number, height: number } | null): number
 * - maiorArea(codigos: Array<{ boundingBox?: object, rawValue?: string }>): object | null
 * - estaDentroDoAlvo(caixa: object, largura: number, altura: number, alvo?: object): boolean
 * - maiorDentroDoAlvo(codigos: Array<object>, largura: number, altura: number, alvo?: object): object | null
 * - normalizarCaixa(caixa: object, w: number, h: number, tipo: string, raw: string, dentro: boolean): object
 *
 * FLUXO:
 * Utilizado por `scannerLoop.js`, `useScanner.js` e `candidatos.js` para filtrar
 * e posicionar caixas na tela e selecionar o código prioritário na mira do usuário.
 *
 * LIMITACOES:
 * Opera estritamente com retângulos alinhados aos eixos (Axis-Aligned Bounding Boxes).
 */

export const ALVO = Object.freeze({
  largura: 0.86,
  altura: 0.62,
})

/**
 * Calcula a área de uma caixa retangular em pixels.
 *
 * @param {{ width?: number, height?: number } | null} caixa
 * @returns {number} Área em pixels ou 0 se nula
 */
export function calcularArea(caixa) {
  if (!caixa || typeof caixa.width !== 'number' || typeof caixa.height !== 'number') {
    return 0
  }
  return caixa.width * caixa.height
}

/**
 * Retorna o código com maior área de bounding box da lista.
 *
 * @param {Array<{ boundingBox?: object }>} codigos
 * @returns {object | null}
 */
export function maiorArea(codigos) {
  if (!Array.isArray(codigos) || codigos.length === 0) return null

  let escolhido = null
  let maior = -1

  for (const c of codigos) {
    const area = calcularArea(c?.boundingBox)
    if (area > maior) {
      maior = area
      escolhido = c
    }
  }
  return escolhido
}

/**
 * Verifica se o centro da caixa está dentro da mira do alvo.
 *
 * @param {{ x: number, y: number, width: number, height: number }} caixa
 * @param {number} largura - Largura do quadro
 * @param {number} altura - Altura do quadro
 * @param {{ largura: number, altura: number }} [alvo=ALVO]
 * @returns {boolean}
 */
export function estaDentroDoAlvo(caixa, largura, altura, alvo = ALVO) {
  if (!caixa || !largura || !altura) return false
  const cx = (caixa.x + caixa.width / 2) / largura
  const cy = (caixa.y + caixa.height / 2) / altura

  return (
    Math.abs(cx - 0.5) <= alvo.largura / 2 &&
    Math.abs(cy - 0.5) <= alvo.altura / 2
  )
}

/**
 * Seleciona o código com maior área posicionado dentro do alvo visual.
 *
 * @param {Array<{ boundingBox?: object }>} codigos
 * @param {number} largura
 * @param {number} altura
 * @param {{ largura: number, altura: number }} [alvo=ALVO]
 * @returns {object | null}
 */
export function maiorDentroDoAlvo(codigos, largura, altura, alvo = ALVO) {
  if (!Array.isArray(codigos) || codigos.length === 0) return null

  const dentro = codigos.filter((c) => {
    if (!c.boundingBox) return true
    return estaDentroDoAlvo(c.boundingBox, largura, altura, alvo)
  })

  return maiorArea(dentro)
}

/**
 * Normaliza as coordenadas de uma caixa para o padrão de tela 0..1.
 *
 * @param {{ x: number, y: number, width: number, height: number }} b
 * @param {number} w - Largura nativa do vídeo
 * @param {number} h - Altura nativa do vídeo
 * @param {string} tipo - 'isbn' | 'candidato' | 'ean' | 'invalido'
 * @param {string} raw - Texto lido
 * @param {boolean} dentroAlvo - Flag se está na mira
 * @returns {object} Objeto pronto para renderização na camada de overlay
 */
export function normalizarCaixa(b, w, h, tipo, raw, dentroAlvo) {
  return {
    x: b.x / w,
    y: b.y / h,
    w: b.width / w,
    h: b.height / h,
    dentroAlvo,
    tipo,
    raw,
  }
}
