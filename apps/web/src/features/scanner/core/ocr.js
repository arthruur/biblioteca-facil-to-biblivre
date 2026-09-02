/**
 * @fileoverview Reconhecimento óptico de caracteres (OCR) para dígitos impressos de ISBN.
 *
 * PROPOSITO:
 * Lê os dígitos numéricos impressos junto ao código de barras quando as barras físicas
 * estão danificadas, riscadas ou com baixa legibilidade.
 *
 * INTERFACE:
 * - obterWorker(): Promise<Tesseract.Worker>
 * - encerrarWorkerOcr(): Promise<void>
 * - binarizarOtsu(imagem: ImageData): ImageData
 * - lerNumerosDoQuadro(video: HTMLVideoElement, regiao?: object): Promise<string | null>
 *
 * FLUXO:
 * Chamado sob demanda por `useScanner.js` (botão manual "123" ou estagnação prolongada).
 * Utiliza o candidato detectado em `candidatos.js` para focar o processamento.
 *
 * LIMITACOES:
 * Exige biblioteca `tesseract.js` carregada sob demanda e suporte a Web Workers.
 * Apenas números (0-9) são reconhecidos.
 */

import { isbnsEmDigitos } from '../isbn.js'

const LARGURA_ALVO = 1400
const RECORTE_PADRAO = Object.freeze({ x: 0.08, largura: 0.84, y: 0.28, altura: 0.46 })

let workerPromessa = null

/**
 * Cria ou recupera o worker persistente do Tesseract configurado para números.
 *
 * @returns {Promise<any>}
 */
export function obterWorker() {
  if (!workerPromessa) {
    workerPromessa = (async () => {
      const { createWorker, PSM } = await import('tesseract.js')
      const worker = await createWorker('eng')
      await worker.setParameters({
        tessedit_char_whitelist: '0123456789',
        tessedit_pageseg_mode: PSM.SINGLE_BLOCK,
      })
      return worker
    })().catch((erro) => {
      workerPromessa = null
      throw erro
    })
  }
  return workerPromessa
}

/**
 * Encerra o worker de OCR liberando memória do navegador.
 */
export async function encerrarWorkerOcr() {
  const pendente = workerPromessa
  workerPromessa = null
  if (!pendente) return
  try {
    const w = await pendente
    await w.terminate()
  } catch {
    /* worker já encerrado */
  }
}

function calcularLimiarOtsu(hist, total) {
  let soma = 0
  for (let t = 0; t < 256; t++) soma += t * hist[t]

  let somaB = 0
  let pesoB = 0
  let varMax = -1
  let limiar = 127

  for (let t = 0; t < 256; t++) {
    pesoB += hist[t]
    if (pesoB === 0) continue
    const pesoF = total - pesoB
    if (pesoF === 0) break
    somaB += t * hist[t]
    const mediaB = somaB / pesoB
    const mediaF = (soma - somaB) / pesoF
    const entre = pesoB * pesoF * (mediaB - mediaF) ** 2
    if (entre > varMax) {
      varMax = entre
      limiar = t
    }
  }
  return limiar
}

/**
 * Aplica binarização adaptativa pelo método de Otsu sobre a imagem.
 *
 * @param {ImageData} imagem
 * @returns {ImageData}
 */
export function binarizarOtsu(imagem) {
  const d = imagem.data
  const total = d.length / 4
  const luz = new Uint8Array(total)
  const hist = new Uint32Array(256)

  for (let i = 0, p = 0; p < total; i += 4, p++) {
    const v = (d[i] * 77 + d[i + 1] * 150 + d[i + 2] * 29) >> 8
    luz[p] = v
    hist[v]++
  }

  const limiar = calcularLimiarOtsu(hist, total)
  for (let i = 0, p = 0; p < total; i += 4, p++) {
    const val = luz[p] > limiar ? 255 : 0
    d[i] = val
    d[i + 1] = val
    d[i + 2] = val
    d[i + 3] = 255
  }
  return imagem
}

function extrairCanvasRecorte(video, regiao) {
  const w = video.videoWidth
  const h = video.videoHeight
  const r = regiao || RECORTE_PADRAO
  const rx = Math.floor(w * r.x)
  const rw = Math.floor(w * r.largura)
  const ry = Math.floor(h * r.y)
  const rh = Math.floor(h * r.altura)

  const escala = Math.min(3, Math.max(1, LARGURA_ALVO / rw))
  const tela = document.createElement('canvas')
  tela.width = Math.round(rw * escala)
  tela.height = Math.round(rh * escala)

  const ctx = tela.getContext('2d', { willReadFrequently: true })
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(video, rx, ry, rw, rh, 0, 0, tela.width, tela.height)
  ctx.putImageData(binarizarOtsu(ctx.getImageData(0, 0, tela.width, tela.height)), 0, 0)
  return tela
}

/**
 * Executa OCR na região indicada e devolve o primeiro ISBN-13 válido.
 *
 * @param {HTMLVideoElement} video
 * @param {object} [regiaoDetectada]
 * @returns {Promise<string | null>}
 */
export async function lerNumerosDoQuadro(video, regiaoDetectada = null) {
  if (!video?.videoWidth || !video?.videoHeight) return null

  const tela = extrairCanvasRecorte(video, regiaoDetectada)
  const worker = await obterWorker()
  const { data: { text } } = await worker.recognize(tela)

  const [isbn] = isbnsEmDigitos(text.replace(/\D/g, ''))
  return isbn || null
}

/**
 * Executa o fluxo de tentativa de OCR com mensagens de status.
 *
 * @param {object} params
 * @returns {Promise<void>}
 */
export async function executarTentativaOcr({
  video,
  regiao,
  ocrRodandoRef,
  ultimoOcrRef,
  setOcrAtivo,
  anunciar,
  entregar,
}) {
  if (ocrRodandoRef.current || !video?.videoWidth) return
  ocrRodandoRef.current = true
  setOcrAtivo(true)
  anunciar('Sem leitura pelas barras — lendo os números…', 'info')
  try {
    const isbn = await lerNumerosDoQuadro(video, regiao)
    if (isbn) {
      anunciar(`Lido pelos números: ${isbn}`, 'ok')
      entregar(isbn, 'ocr')
    } else {
      anunciar('Não foi possível ler os números — aproxime mais', 'erro')
    }
  } catch (e) {
    console.error('Falha no OCR:', e)
    anunciar('O leitor de números falhou neste aparelho', 'erro')
  } finally {
    ocrRodandoRef.current = false
    setOcrAtivo(false)
    ultimoOcrRef.current = Date.now()
  }
}

