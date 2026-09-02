/**
 * @fileoverview Detecção ultraleve de candidatos (ROI) e cálculo do quadrado do código.
 *
 * PROPOSITO:
 * Localiza regiões com alta densidade de transições de contraste (padrão de barras)
 * em um canvas reduzido (~320px) e expande a geometria para englobar o quadrado
 * completo da etiqueta (barras + números do ISBN).
 *
 * INTERFACE:
 * - encontrarCandidatos(video: HTMLVideoElement, alvo?: object): Array<object>
 * - recortarRegiao(video: HTMLVideoElement, regiao: object, padding?: number): HTMLCanvasElement | null
 *
 * FLUXO:
 * Chamado a cada ciclo pelo laço de varredura (`scannerLoop.js`). Se houver candidato,
 * alimenta o `recortarRegiao` para decodificação focada e OCR.
 *
 * LIMITACOES:
 * Otimizado para códigos de barras predominantemente horizontais (barras verticais).
 * Códigos com giro maior que 45 graus podem exigir a salvaguarda de tela cheia.
 */

const MAX_DIMENSAO = 400

let canvasAnalise = null
let ctxAnalise = null
let canvasRecorte = null
let ctxRecorte = null

function obterCanvasAnalise(largura, altura) {
  if (!canvasAnalise) canvasAnalise = document.createElement('canvas')
  if (canvasAnalise.width !== largura || canvasAnalise.height !== altura) {
    canvasAnalise.width = largura
    canvasAnalise.height = altura
    ctxAnalise = canvasAnalise.getContext('2d', { willReadFrequently: true })
  }
  return { canvas: canvasAnalise, ctx: ctxAnalise }
}

function obterCanvasRecorte(largura, altura) {
  if (!canvasRecorte) canvasRecorte = document.createElement('canvas')
  if (canvasRecorte.width !== largura || canvasRecorte.height !== altura) {
    canvasRecorte.width = largura
    canvasRecorte.height = altura
    ctxRecorte = canvasRecorte.getContext('2d', { willReadFrequently: true })
  }
  return { canvas: canvasRecorte, ctx: ctxRecorte }
}

function converterCinza(data, total) {
  const bw = new Uint8Array(total)
  for (let i = 0, p = 0; p < total; i += 4, p++) {
    bw[p] = (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8
  }
  return bw
}

function calcularTransicoesLinha(bw, linhas, colunas) {
  const transicoes = new Uint32Array(linhas)
  for (let y = 0; y < linhas; y++) {
    let count = 0
    const offset = y * colunas
    for (let x = 1; x < colunas; x++) {
      if (Math.abs(bw[offset + x - 1] - bw[offset + x]) > 14) count++
    }
    transicoes[y] = count
  }
  return transicoes
}

function limitesHorizontais(bw, y1, y2, colunas, altura) {
  const colTrans = new Uint32Array(colunas)
  for (let y = y1; y < y2; y++) {
    const offset = y * colunas
    for (let x = 1; x < colunas; x++) {
      if (Math.abs(bw[offset + x - 1] - bw[offset + x]) > 14) colTrans[x]++
    }
  }
  let x1 = -1
  let x2 = -1
  const minV = Math.max(2, Math.round(altura * 0.12))
  for (let x = 0; x < colunas; x++) {
    if (colTrans[x] > minV) {
      if (x1 === -1) x1 = x
      x2 = x
    }
  }
  return { x1, x2 }
}

function expandirQuadrado(x1, x2, y1, y2, colunas, linhas, densidade) {
  const wBarras = x2 - x1
  const hBarras = y2 - y1
  const padYTopo = Math.round(hBarras * 0.20)
  const padYBase = Math.round(hBarras * 0.38)
  const padX = Math.round(wBarras * 0.14)

  const bx1 = Math.max(0, x1 - padX)
  const bx2 = Math.min(colunas, x2 + padX)
  const by1 = Math.max(0, y1 - padYTopo)
  const by2 = Math.min(linhas, y2 + padYBase)

  return {
    x: bx1 / colunas,
    y: by1 / linhas,
    largura: (bx2 - bx1) / colunas,
    altura: (by2 - by1) / linhas,
    mioloBarras: { x: x1 / colunas, y: y1 / linhas, largura: wBarras / colunas, altura: hBarras / linhas },
    densidade,
  }
}

/**
 * Encontra regiões do frame que contêm o quadrado do código de barras.
 *
 * @param {HTMLVideoElement} video
 * @param {{ largura: number, altura: number }} [alvo]
 * @returns {Array<object>}
 */
export function encontrarCandidatos(video, alvo) {
  const w = video?.videoWidth
  const h = video?.videoHeight
  if (!w || !h) return []

  const escala = Math.min(1, MAX_DIMENSAO / Math.max(w, h))
  const colunas = Math.max(1, Math.round(w * escala))
  const linhas = Math.max(1, Math.round(h * escala))

  const { ctx } = obterCanvasAnalise(colunas, linhas)
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(video, 0, 0, colunas, linhas)

  const bw = converterCinza(ctx.getImageData(0, 0, colunas, linhas).data, colunas * linhas)
  const transLinha = calcularTransicoesLinha(bw, linhas, colunas)
  const LIMIAR = Math.max(8, Math.round(colunas * 0.035))
  const candidatos = []
  let fInicio = -1

  for (let y = 0; y <= linhas; y++) {
    const alto = y < linhas && transLinha[y] > LIMIAR
    if (alto && fInicio === -1) fInicio = y
    else if (!alto && fInicio !== -1) {
      const hFaixa = y - fInicio
      if (hFaixa >= Math.max(3, Math.round(linhas * 0.02))) {
        const { x1, x2 } = limitesHorizontais(bw, fInicio, y, colunas, hFaixa)
        if (x1 !== -1 && (x2 - x1) >= Math.max(14, Math.round(colunas * 0.05))) {
          candidatos.push(expandirQuadrado(x1, x2, fInicio, y, colunas, linhas, transLinha[(fInicio + y) >> 1]))
        }
      }
      fInicio = -1
    }
  }

  candidatos.sort((a, b) => b.densidade - a.densidade)
  if (!alvo) return candidatos
  return candidatos.map((c) => {
    const cx = c.x + c.largura / 2
    const cy = c.y + c.altura / 2
    const dentro = Math.abs(cx - 0.5) <= (alvo.largura / 2) + 0.10 && Math.abs(cy - 0.5) <= (alvo.altura / 2) + 0.10
    return { ...c, dentroAlvo: dentro }
  })
}

/**
 * Recorta o quadrado do código (barras + números) do vídeo em alta resolução.
 *
 * @param {HTMLVideoElement} video
 * @param {object} regiao
 * @param {number} [padding=0.06]
 * @returns {HTMLCanvasElement | null}
 */
export function recortarRegiao(video, regiao, padding = 0.06) {
  const w = video?.videoWidth
  const h = video?.videoHeight
  if (!w || !h || !regiao) return null

  const px = regiao.largura * padding
  const py = regiao.altura * padding
  const rx = Math.max(0, Math.floor(w * (regiao.x - px)))
  const ry = Math.max(0, Math.floor(h * (regiao.y - py)))
  const rw = Math.min(w - rx, Math.ceil(w * (regiao.largura + px * 2)))
  const rh = Math.min(h - ry, Math.ceil(h * (regiao.altura + py * 2)))

  if (rw <= 0 || rh <= 0) return null
  const canvasW = Math.min(rw, 1280)
  const canvasH = Math.min(rh, 720)

  const { canvas, ctx } = obterCanvasRecorte(canvasW, canvasH)
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(video, rx, ry, rw, rh, 0, 0, canvasW, canvasH)
  canvas.origem = { rx, ry, rw, rh, videoW: w, videoH: h }
  return canvas
}
