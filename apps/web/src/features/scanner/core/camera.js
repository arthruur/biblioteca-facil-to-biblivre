/**
 * @fileoverview Gerenciamento de hardware da câmera, track de vídeo e controles ópticos.
 *
 * PROPOSITO:
 * Isola o ciclo de vida do stream de vídeo (`getUserMedia`), configurações de foco macro
 * contínuo, zoom óptico/digital, lanterna (torch) e liberação segura de hardware.
 *
 * INTERFACE:
 * - RESTRICOES_VIDEO: MediaStreamConstraints
 * - abrirCamera(elementoId: string, restricoes?: object): Promise<{ stream, video, track }>
 * - ajustarCamera(track: MediaStreamTrack): Promise<{ lanterna: boolean, zoom: object | null }>
 * - detectarLanterna(track: MediaStreamTrack): boolean
 * - obterTrackDoVideo(video: HTMLVideoElement | null): MediaStreamTrack | null
 * - alternarLanterna(track: MediaStreamTrack, ligar: boolean): Promise<boolean>
 * - aplicarZoom(track: MediaStreamTrack, valor: number): Promise<void>
 * - dispararPulsoFoco(track: MediaStreamTrack): Promise<void>
 * - fecharCamera(stream: MediaStream | null, video: HTMLVideoElement | null, elementoId?: string): void
 *
 * FLUXO:
 * Invocado por `useScanner.js` na inicialização (`iniciar`), ajuste de controles e desmonte.
 *
 * LIMITACOES:
 * Funciona exclusivamente em contextos seguros (HTTPS ou localhost).
 */

export const RESTRICOES_VIDEO = Object.freeze({
  facingMode: { ideal: 'environment' },
  width: { ideal: 1920 },
  height: { ideal: 1080 },
  frameRate: { ideal: 30 },
})

/**
 * Cria o elemento de vídeo, anexa o stream da câmera traseira e inicia a reprodução.
 *
 * @param {string} elementoId - ID do container HTML do visor
 * @param {object} [restricoes=RESTRICOES_VIDEO]
 * @returns {Promise<{ stream: MediaStream, video: HTMLVideoElement, track: MediaStreamTrack }>}
 */
export async function abrirCamera(elementoId, restricoes = RESTRICOES_VIDEO) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: restricoes })
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
 * Diz se a lanterna (torch) deste aparelho pode ser acionada.
 *
 * Não basta olhar `capabilities.torch === true`: parte dos aparelhos Android
 * anuncia o recurso como lista (`[false, true]`), outros não anunciam nada em
 * `getCapabilities` e só expõem `torch` em `getSettings` — e a lanterna funciona
 * nos dois casos. Reconhecer os três formatos é o que mantém o botão de lanterna
 * na tela em vez de escondê-lo num aparelho que a tem.
 *
 * @param {MediaStreamTrack} track
 * @returns {boolean}
 */
export function detectarLanterna(track) {
  if (!track) return false
  const caps = track.getCapabilities?.() ?? {}
  if (caps.torch === true) return true
  if (Array.isArray(caps.torch) && caps.torch.includes(true)) return true
  const settings = track.getSettings?.() ?? {}
  return 'torch' in settings
}

/**
 * Extrai a faixa de vídeo pendurada num elemento `<video>`.
 *
 * O motor de reserva (html5-qrcode) abre a câmera por conta própria e não
 * devolve a faixa: sem isto, lanterna, zoom e foco não existiriam no caminho
 * ZXing.
 *
 * @param {HTMLVideoElement | null} video
 * @returns {MediaStreamTrack | null}
 */
export function obterTrackDoVideo(video) {
  const stream = video?.srcObject
  return stream?.getVideoTracks?.()[0] || null
}

/**
 * Aplica foco contínuo e extrai recursos da câmera (lanterna e zoom).
 *
 * @param {MediaStreamTrack} track
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
      } catch {}
    }
  }

  const z = caps.zoom
  const zoomDisponivel = z && typeof z === 'object' && z.max > z.min
    ? { min: z.min, max: z.max, passo: z.step || 0.1 } : null

  return { lanterna: detectarLanterna(track), zoom: zoomDisponivel }
}

/**
 * Liga ou desliga a lanterna do aparelho.
 *
 * Confere o resultado em `getSettings`: há aparelhos que aceitam a restrição sem
 * reclamar e deixam a lanterna apagada. Devolver `false` aí é o que faz a tela
 * avisar em vez de acender um botão mentiroso.
 *
 * @param {MediaStreamTrack} track
 * @param {boolean} ligar
 * @returns {Promise<boolean>} `true` quando a lanterna realmente ficou no estado pedido
 */
export async function alternarLanterna(track, ligar) {
  if (!track) return false
  const alvo = Boolean(ligar)
  try {
    await track.applyConstraints({ advanced: [{ torch: alvo }] })
  } catch {
    return false
  }
  const settings = track.getSettings?.() ?? {}
  if ('torch' in settings && settings.torch !== alvo) return false
  return true
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
  } catch {}
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
  } catch {}
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
  if (elementoId) document.getElementById(elementoId)?.replaceChildren()
}
