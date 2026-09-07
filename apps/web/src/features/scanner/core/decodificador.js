/**
 * @fileoverview Motores de decodificação de código de barras (Nativo e Reserva ZXing).
 *
 * PROPOSITO:
 * Centraliza os dois motores de decodificação: o nativo (`BarcodeDetector`), que lê em
 * resolução nativa sem intermediários, e o motor de reserva (`html5-qrcode` / ZXing)
 * para navegadores sem suporte nativo (iOS Safari, desktop).
 *
 * INTERFACE:
 * - FORMATOS_ISBN: string[]            (modo 'isbn' — catalogação, o de sempre)
 * - FORMATOS_CIRCULACAO: string[]      (modo 'circulacao' — etiqueta de tombo)
 * - FORMATOS_NATIVOS: string[]         (apelido histórico de FORMATOS_ISBN)
 * - formatosNativos(modo?: 'isbn' | 'circulacao'): Promise<string[] | null>
 * - nomesFormatosReserva(modo?: 'isbn' | 'circulacao'): string[]
 * - criarDetectorNativo(formatos: string[]): BarcodeDetector
 * - iniciarLeitorReserva(elementoId: string, restricoes: object, aoLer: Function, modo?: string): Promise<any>
 * - decodificarFoto(arquivo: Blob, formatos: string[] | null): Promise<string | null>
 *
 * FLUXO:
 * Invocado por `useScanner.js` na inicialização para decidir qual motor usar e para
 * decodificar fotos do rolo da câmera.
 *
 * MODOS:
 * Na catalogação o que interessa é o EAN-13 da capa; na circulação o que identifica o
 * exemplar é a etiqueta colada nele, que o BibLivre 5 imprime em Code 39 Estendido
 * (veja o cabeçalho de `../codigos.js`). São dois conjuntos de formatos, e cada um
 * vale para os dois motores — o nativo e o de reserva.
 *
 * LIMITACOES:
 * Chrome desktop expõe a classe `BarcodeDetector`, mas `getSupportedFormats` pode não
 * ter `ean_13` caso a biblioteca do sistema operacional não esteja presente. Na
 * circulação a exigência é maior: sem `code_128` nem `code_39` o motor nativo não lê
 * etiqueta nenhuma, e é melhor cair para o de reserva, que lê as duas simbologias.
 */

import { BarcodeDetector as BarcodeDetectorPolyfill } from 'barcode-detector'
import { maiorArea } from './geometria.js'

/**
 * Modo catalogação: a lista de sempre, intocada. O alvo é o EAN-13 da capa, mas
 * UPC e Code 39/128 continuam ligados porque o acervo tem livro antigo com ISBN-10
 * impresso em etiqueta e livro importado com UPC-A.
 */
export const FORMATOS_ISBN = Object.freeze([
  'ean_13',
  'ean_8',
  'upc_a',
  'upc_e',
  'code_128',
  'code_39',
])

/**
 * Modo circulação: a etiqueta do exemplar (Code 39 no BibLivre 5, Code 128 em
 * etiqueta impressa por outros meios) mais o EAN-13, que é o caminho alternativo —
 * bipar o ISBN da capa devolve a lista de exemplares da obra. Código de produto
 * (UPC) fica de fora: não identifica exemplar nem leitor.
 */
export const FORMATOS_CIRCULACAO = Object.freeze([
  'ean_13',
  'code_128',
  'code_39',
])

/** Apelido do conjunto de catalogação, mantido para quem já importava este nome. */
export const FORMATOS_NATIVOS = FORMATOS_ISBN

const FORMATOS_POR_MODO = Object.freeze({
  isbn: FORMATOS_ISBN,
  circulacao: FORMATOS_CIRCULACAO,
})

/**
 * Nomes dos formatos no vocabulário do `html5-qrcode` (`Html5QrcodeSupportedFormats`).
 *
 * Separado da inicialização do motor para poder ser conferido em teste sem carregar
 * a biblioteca, que só existe no navegador.
 *
 * @param {'isbn' | 'circulacao'} [modo]
 * @returns {string[]}
 */
export function nomesFormatosReserva(modo = 'isbn') {
  return (FORMATOS_POR_MODO[modo] || FORMATOS_ISBN).map((f) => f.toUpperCase())
}

const suporteNativoPromessas = new Map()

/**
 * Retorna a classe BarcodeDetector adequada: nativa se existir, ou polyfill WASM.
 */
export function obterClasseDetector() {
  if (typeof window !== 'undefined' && window.BarcodeDetector) {
    return window.BarcodeDetector
  }
  return BarcodeDetectorPolyfill
}

/**
 * Identifica se o motor em uso é o nativo do navegador ou o polyfill WebAssembly.
 *
 * @returns {'nativo' | 'wasm'}
 */
export function tipoMotor() {
  if (typeof window !== 'undefined' && 'BarcodeDetector' in window) {
    return 'nativo'
  }
  return 'wasm'
}

/**
 * Consulta os formatos realmente suportados pelo BarcodeDetector deste sistema (ou polyfill WASM).
 *
 * Devolver `null` é o sinal de "use o motor de reserva". Na catalogação basta faltar
 * `ean_13`; na circulação também falta o essencial se não houver nenhuma simbologia
 * linear de etiqueta (`code_128` ou `code_39`), porque aí o nativo leria a capa e
 * ficaria cego para o tombo.
 *
 * @param {'isbn' | 'circulacao'} [modo]
 * @returns {Promise<string[] | null>}
 */
export function formatosNativos(modo = 'isbn') {
  if (!suporteNativoPromessas.has(modo)) {
    const desejados = FORMATOS_POR_MODO[modo] || FORMATOS_ISBN
    suporteNativoPromessas.set(modo, (async () => {
      try {
        const Detector = obterClasseDetector()
        if (!Detector?.getSupportedFormats) return null
        const disponiveis = await Detector.getSupportedFormats()
        const uteis = desejados.filter((f) => disponiveis.includes(f))
        if (!uteis.includes('ean_13')) return null
        if (modo === 'circulacao' && !uteis.some((f) => f === 'code_128' || f === 'code_39')) {
          return null
        }
        return uteis
      } catch {
        return null
      }
    })())
  }
  return suporteNativoPromessas.get(modo)
}

/**
 * Cria uma nova instância de BarcodeDetector configurada.
 *
 * @param {string[]} formatos
 * @returns {any}
 */
export function criarDetectorNativo(formatos) {
  const Detector = obterClasseDetector()
  return new Detector({ formats: formatos })
}

/**
 * Inicializa o motor de reserva ZXing via html5-qrcode.
 *
 * O `formatsToSupport` sai do mesmo conjunto por modo do motor nativo: cada formato
 * a mais é uma passada a mais por quadro no ZXing, que já é o caminho lento (iOS
 * Safari, desktop). Na circulação o que entra é CODE_39 e CODE_128, sem os códigos
 * de produto.
 *
 * @param {string} elementoId
 * @param {object} restricoesVideo
 * @param {(texto: string) => void} aoLer
 * @param {'isbn' | 'circulacao'} [modo]
 * @returns {Promise<any>}
 */
export async function iniciarLeitorReserva(elementoId, restricoesVideo, aoLer, modo = 'isbn') {
  const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode')
  const formatos = nomesFormatosReserva(modo)
    .map((nome) => Html5QrcodeSupportedFormats[nome])
    .filter((f) => f !== undefined)

  const instancia = new Html5Qrcode(elementoId, { formatsToSupport: formatos })
  await instancia.start(
    { facingMode: restricoesVideo?.facingMode || 'environment' },
    {
      fps: 15,
      qrbox: (w, h) => {
        const largura = Math.floor(Math.min(w * 0.92, h * 2.4 * 0.92))
        return { width: largura, height: Math.floor(largura / 2.4) }
      },
      videoConstraints: restricoesVideo,
      experimentalFeatures: { useBarCodeDetectorIfSupported: false },
      formatsToSupport: formatos,
    },
    (texto) => aoLer(texto),
    () => {}
  )
  const video = document.querySelector(`#${elementoId} video`)
  return { instancia, video }
}

async function decodificarFotoReserva(arquivo) {
  const caixa = document.createElement('div')
  caixa.id = `leitor-foto-${Date.now()}`
  caixa.style.cssText = 'position:fixed;left:-10000px;top:0;width:1px;height:1px'
  document.body.appendChild(caixa)

  const { Html5Qrcode } = await import('html5-qrcode')
  const instancia = new Html5Qrcode(caixa.id)
  try {
    return await instancia.scanFile(arquivo, false)
  } finally {
    try { instancia.clear() } catch {}
    caixa.remove()
  }
}

/**
 * Decodifica o código de barras contido em um arquivo de foto.
 *
 * @param {Blob} arquivo
 * @param {string[] | null} formatos
 * @returns {Promise<string | null>}
 */
export async function decodificarFoto(arquivo, formatos) {
  if (formatos && typeof window !== 'undefined') {
    try {
      const bitmap = await createImageBitmap(arquivo)
      const detector = criarDetectorNativo(formatos)
      const achados = await detector.detect(bitmap)
      bitmap.close?.()
      const escolhido = maiorArea(achados)
      if (escolhido?.rawValue) return escolhido.rawValue
    } catch {
      /* cai para o fallback do html5-qrcode */
    }
  }

  try {
    return await decodificarFotoReserva(arquivo)
  } catch {
    return null
  }
}

/**
 * Orquestra a leitura de código de barras a partir de um arquivo de imagem.
 *
 * @param {object} params
 * @returns {Promise<void>}
 */
export async function executarLeituraFoto({
  arquivo,
  formatos,
  anunciar,
  entregar,
  classificarCodigo,
}) {
  anunciar('Lendo a foto…')
  const texto = await decodificarFoto(arquivo, formatos)
  if (texto && entregar(texto, 'foto')) {
    anunciar(`Lido da foto: ${classificarCodigo(texto).codigo}`, 'ok')
  } else {
    anunciar('Nenhum código detectado na foto', 'erro')
  }
}

