/**
 * @fileoverview Motores de decodificação de código de barras (Nativo e Reserva ZXing).
 *
 * PROPOSITO:
 * Centraliza os dois motores de decodificação: o nativo (`BarcodeDetector`), que lê em
 * resolução nativa sem intermediários, e o motor de reserva (`html5-qrcode` / ZXing)
 * para navegadores sem suporte nativo (iOS Safari, desktop).
 *
 * INTERFACE:
 * - FORMATOS_NATIVOS: string[]
 * - formatosNativos(): Promise<string[] | null>
 * - criarDetectorNativo(formatos: string[]): BarcodeDetector
 * - iniciarLeitorReserva(elementoId: string, restricoes: object, aoLer: Function): Promise<any>
 * - decodificarFoto(arquivo: Blob, formatos: string[] | null): Promise<string | null>
 *
 * FLUXO:
 * Invocado por `useScanner.js` na inicialização para decidir qual motor usar e para
 * decodificar fotos do rolo da câmera.
 *
 * LIMITACOES:
 * Chrome desktop expõe a classe `BarcodeDetector`, mas `getSupportedFormats` pode não
 * ter `ean_13` caso a biblioteca do sistema operacional não esteja presente.
 */

import { maiorArea } from './geometria.js'

export const FORMATOS_NATIVOS = Object.freeze([
  'ean_13',
  'ean_8',
  'upc_a',
  'upc_e',
  'code_128',
  'code_39',
])

let suporteNativoPromessa = null

/**
 * Consulta os formatos realmente suportados pelo BarcodeDetector deste sistema.
 *
 * @returns {Promise<string[] | null>}
 */
export function formatosNativos() {
  if (!suporteNativoPromessa) {
    suporteNativoPromessa = (async () => {
      if (typeof window === 'undefined' || !('BarcodeDetector' in window)) return null
      try {
        const disponiveis = await window.BarcodeDetector.getSupportedFormats()
        const uteis = FORMATOS_NATIVOS.filter((f) => disponiveis.includes(f))
        return uteis.includes('ean_13') ? uteis : null
      } catch {
        return null
      }
    })()
  }
  return suporteNativoPromessa
}

/**
 * Cria uma nova instância de BarcodeDetector configurada.
 *
 * @param {string[]} formatos
 * @returns {any}
 */
export function criarDetectorNativo(formatos) {
  return new window.BarcodeDetector({ formats: formatos })
}

/**
 * Inicializa o motor de reserva ZXing via html5-qrcode.
 *
 * @param {string} elementoId
 * @param {object} restricoesVideo
 * @param {(texto: string) => void} aoLer
 * @returns {Promise<any>}
 */
export async function iniciarLeitorReserva(elementoId, restricoesVideo, aoLer) {
  const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode')
  const formatos = [
    Html5QrcodeSupportedFormats.EAN_13,
    Html5QrcodeSupportedFormats.EAN_8,
    Html5QrcodeSupportedFormats.UPC_A,
    Html5QrcodeSupportedFormats.UPC_E,
    Html5QrcodeSupportedFormats.CODE_128,
    Html5QrcodeSupportedFormats.CODE_39,
  ]

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
  if (formatos && typeof window !== 'undefined' && 'BarcodeDetector' in window) {
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

