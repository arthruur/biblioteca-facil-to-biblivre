/**
 * Socorro por OCR: lê a faixa de dígitos impressa junto ao código de barras.
 *
 * Entra em cena quando o decodificador não fecha — barras riscadas, plástico
 * amassado, etiqueta colada por cima. Os dígitos em OCR-B logo abaixo das
 * barras costumam sobreviver a tudo isso.
 *
 * Duas coisas aqui são resposta a bugs reais da versão anterior:
 *
 *  1. `Tesseract.recognize(img, lang, opts)` ignora `tessedit_*` — aquelas
 *     opções só existem via `worker.setParameters`. O OCR antigo rodava sem
 *     whitelist nenhuma, lendo letras onde só há número.
 *  2. Cada chamada de `recognize` criava um worker novo, com o custo de
 *     inicialização inteiro a cada tentativa. Agora o worker é um só, criado
 *     na primeira necessidade e reaproveitado pelo resto do turno.
 */

import { isbnsEmDigitos } from './isbn'

/** Largura para onde o recorte é reescalado antes do OCR (~300 DPI). */
const LARGURA_ALVO = 1400

/**
 * Recorte do quadro onde os dígitos costumam cair.
 *
 * Generoso na vertical porque não sabemos se a pessoa centrou as barras ou os
 * números na marcação — pegar os dois custa alguns décimos e evita o caso em
 * que o OCR falha só por enquadramento.
 */
const RECORTE = { x: 0.08, largura: 0.84, y: 0.28, altura: 0.46 }

let workerPromessa = null

function obterWorker() {
  if (!workerPromessa) {
    // Import dinâmico: o Tesseract são alguns megabytes e a maioria dos lotes
    // nunca precisa dele. Só entra na rede quando o código realmente falhou.
    workerPromessa = (async () => {
      const { createWorker, PSM } = await import('tesseract.js')
      const worker = await createWorker('eng')
      await worker.setParameters({
        tessedit_char_whitelist: '0123456789',
        tessedit_pageseg_mode: PSM.SINGLE_BLOCK,
      })
      return worker
    })().catch((erro) => {
      workerPromessa = null // deixa a próxima tentativa recomeçar do zero
      throw erro
    })
  }
  return workerPromessa
}

export async function encerrarOcr() {
  const pendente = workerPromessa
  workerPromessa = null
  if (!pendente) return
  try {
    ;(await pendente).terminate()
  } catch {
    /* já morreu junto com a página */
  }
}

/**
 * Otsu: escolhe o limiar a partir do próprio histograma do recorte.
 *
 * O limiar fixo de antes (140) assumia iluminação de mesa. Numa estante, com a
 * sombra da prateleira em cima do livro, ele apagava os dígitos inteiros.
 */
function binarizarOtsu(imagem) {
  const d = imagem.data
  const total = d.length / 4
  const luz = new Uint8Array(total)
  const hist = new Uint32Array(256)

  for (let i = 0, p = 0; p < total; i += 4, p++) {
    const v = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) | 0
    luz[p] = v
    hist[v]++
  }

  let soma = 0
  for (let t = 0; t < 256; t++) soma += t * hist[t]

  let somaFundo = 0
  let pesoFundo = 0
  let variancia = -1
  let limiar = 127

  for (let t = 0; t < 256; t++) {
    pesoFundo += hist[t]
    if (pesoFundo === 0) continue
    const pesoFrente = total - pesoFundo
    if (pesoFrente === 0) break
    somaFundo += t * hist[t]
    const mediaFundo = somaFundo / pesoFundo
    const mediaFrente = (soma - somaFundo) / pesoFrente
    const entre = pesoFundo * pesoFrente * (mediaFundo - mediaFrente) ** 2
    if (entre > variancia) {
      variancia = entre
      limiar = t
    }
  }

  for (let i = 0, p = 0; p < total; i += 4, p++) {
    const bw = luz[p] > limiar ? 255 : 0
    d[i] = bw
    d[i + 1] = bw
    d[i + 2] = bw
    d[i + 3] = 255
  }
  return imagem
}

/**
 * Roda o OCR sobre o quadro atual do vídeo, em resolução nativa.
 *
 * Só devolve algo se o dígito verificador do ISBN-13 fechar: o OCR erra, e um
 * ISBN errado catalogaria o livro errado — falha silenciosa, cara de arrumar.
 */
export async function lerNumerosDoVideo(video) {
  const w = video?.videoWidth
  const h = video?.videoHeight
  if (!w || !h) return null

  const rx = Math.floor(w * RECORTE.x)
  const rw = Math.floor(w * RECORTE.largura)
  const ry = Math.floor(h * RECORTE.y)
  const rh = Math.floor(h * RECORTE.altura)

  const escala = Math.min(3, Math.max(1, LARGURA_ALVO / rw))
  const tela = document.createElement('canvas')
  tela.width = Math.round(rw * escala)
  tela.height = Math.round(rh * escala)

  const ctx = tela.getContext('2d', { willReadFrequently: true })
  // Sem suavização: a borda dura do glifo é justamente o que o Tesseract usa.
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(video, rx, ry, rw, rh, 0, 0, tela.width, tela.height)
  ctx.putImageData(binarizarOtsu(ctx.getImageData(0, 0, tela.width, tela.height)), 0, 0)

  const worker = await obterWorker()
  const {
    data: { text },
  } = await worker.recognize(tela)

  const [isbn] = isbnsEmDigitos(text.replace(/\D/g, ''))
  return isbn || null
}
