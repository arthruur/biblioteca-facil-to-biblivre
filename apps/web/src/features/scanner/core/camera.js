/**
 * @fileoverview Gerenciamento de hardware da câmera, track de vídeo e controles ópticos.
 *
 * PROPOSITO:
 * Isola o ciclo de vida do stream de vídeo (`getUserMedia`), configurações de foco macro
 * contínuo, zoom óptico/digital, lanterna (torch) e liberação segura de hardware.
 *
 * INTERFACE:
 * - RESTRICOES_VIDEO: MediaStreamConstraints
 * - abrirCamera(elementoId: string, restricoes?: object): Promise<{ stream: MediaStream, video: HTMLVideoElement, track: MediaStreamTrack }>
 * - ajustarCamera(track: MediaStreamTrack): Promise<{ lanterna: boolean, zoom: object | null }>
 * - alternarLanterna(track: MediaStreamTrack, ligar: boolean): Promise<boolean>
 * - aplicarZoom(track: MediaStreamTrack, valor: number): Promise<void>
 * - dispararPulsoFoco(track: MediaStreamTrack): Promise<void>
 * - fecharCamera(stream: MediaStream | null, video: HTMLVideoElement | null, elementoId?: string): void
 *
 * FLUXO:
 * Invocado por `useScanner.js` na inicialização (`iniciar`), ajuste de controles
 * (lanterna/zoom) e no desmonte (`parar`).
 *
 * LIMITACOES:
 * Funciona exclusivamente em contextos seguros (HTTPS ou localhost).
 * A disponibilidade de foco macro, lanterna e zoom depende das capacidades do hardware.
 */

export const RESTRICOES_VIDEO = Object.freeze({
  facingMode: { exact: 'environment' },
  width: { ideal: 1920 },
  height: { ideal: 1080 },
  frameRate: { ideal: 30 },
})

/**
 * Cria o elemento de vídeo, anexa o stream da câmera e inicia a reprodução.
 *
 * @param {string} elementoId - ID do container HTML do visor
 * @param {string | object} [modoCamera='environment']
 * @returns {Promise<{ stream: MediaStream, video: HTMLVideoElement, track: MediaStreamTrack }>}
 */
export async function abrirCamera(elementoId, modoCamera = 'environment') {
  const base = { width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 } }
  let stream = null

  try {
    const videoConstraint = typeof modoCamera === 'string'
      ? { facingMode: { exact: modoCamera }, ...base }
      : (modoCamera || RESTRICOES_VIDEO)
    stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: videoConstraint })
  } catch {
    const videoConstraint = typeof modoCamera === 'string'
      ? { facingMode: { ideal: modoCamera }, ...base }
      : RESTRICOES_VIDEO
    stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: videoConstraint })
  }

  const video = document.createElement('video')
  video.autoplay = true
  video.muted = true
  video.playsInline = true
  video.setAttribute('playsinline', 'true')
  video.setAttribute('muted', 'true')
  video.srcObject = stream

  const container = document.getElementById(elementoId)
  if (container) container.replaceChildren(video)

  await video.play()
  const track = stream.getVideoTracks()[0]
  return { stream, video, track }
}

/**
 * Aplica foco contínuo e extrai recursos da câmera (lanterna e zoom).
 *
 * @param {MediaStreamTrack} track
 * @returns {Promise<{ lanterna: boolean, zoom: { min: number, max: number, passo: number } | null }>}
 */
export async function ajustarCamera(track) {
  if (!track) return { lanterna: false, zoom: null }
  const caps = track.getCapabilities?.() ?? {}

  const advanced = []
  if (caps.focusMode?.includes('continuous')) advanced.push({ focusMode: 'continuous' })
  if (caps.exposureMode?.includes('continuous')) advanced.push({ exposureMode: 'continuous' })
  if (caps.whiteBalanceMode?.includes('continuous')) advanced.push({ whiteBalanceMode: 'continuous' })

  if (advanced.length) {
    try {
      await track.applyConstraints({ advanced })
    } catch {
      try {
        if (caps.focusMode?.includes('continuous')) {
          await track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] })
        }
      } catch { /* segue com padrão */ }
    }
  }

  const z = caps.zoom
  const zoomDisponivel = z && typeof z === 'object' && z.max > z.min
    ? { min: z.min, max: z.max, passo: z.step || 0.1 }
    : null

  return {
    lanterna: caps.torch === true,
    zoom: zoomDisponivel,
  }
}

/**
 * Liga ou desliga a lanterna do aparelho.
 *
 * @param {MediaStreamTrack} track
 * @param {boolean} ligar
 * @returns {Promise<boolean>} Sucesso da operação
 */
export async function alternarLanterna(track, ligar) {
  if (!track) return false
  try {
    await track.applyConstraints({ advanced: [{ torch: Boolean(ligar) }] })
    return true
  } catch {
    return false
  }
}

/**
 * Define o nível de zoom óptico/digital da câmera.
 *
 * @param {MediaStreamTrack} track
 * @param {number} valor
 */
export async function aplicarZoom(track, valor) {
  if (!track) return
  try {
    await track.applyConstraints({ advanced: [{ zoom: valor }] })
  } catch {
    /* fora de faixa */
  }
}

/**
 * Força um pulso momentâneo de foco para desbloquear foco travado.
 *
 * @param {MediaStreamTrack} track
 */
export async function dispararPulsoFoco(track) {
  const caps = track?.getCapabilities?.()
  if (!track || !caps?.focusMode) return

  try {
    if (caps.focusMode.includes('single-shot')) {
      await track.applyConstraints({ advanced: [{ focusMode: 'single-shot' }] })
      setTimeout(() => track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(() => {}), 900)
    } else if (caps.focusMode.includes('manual') && caps.focusDistance?.min) {
      const meio = (caps.focusDistance.min + caps.focusDistance.max) / 2
      await track.applyConstraints({ advanced: [{ focusMode: 'manual', focusDistance: meio }] }).catch(() => {})
      setTimeout(() => track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(() => {}), 600)
    }
  } catch {
    /* ignora suporte ausente */
  }
}

/**
 * Libera os trilhos da câmera e remove elementos para evitar consumo de bateria.
 *
 * @param {MediaStream | null} stream
 * @param {HTMLVideoElement | null} video
 * @param {string} [elementoId]
 */
export function fecharCamera(stream, video, elementoId) {
  stream?.getTracks().forEach((t) => t.stop())
  if (video?.srcObject) {
    video.srcObject.getTracks().forEach((t) => t.stop())
    video.srcObject = null
  }
  if (elementoId) {
    document.getElementById(elementoId)?.replaceChildren()
  }
}
