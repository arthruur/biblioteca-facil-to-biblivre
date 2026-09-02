/**
 * @fileoverview Retorno sonoro e tátil imediato no momento da decodificação.
 *
 * PROPOSITO:
 * Fornece feedback sensorial (bipe agradável em 880Hz e vibração háptica)
 * para o operador da biblioteca saber na hora que o livro foi lido sem olhar pra tela.
 *
 * INTERFACE:
 * - tocarBeepSucesso(): void
 * - vibrar(padrao?: number | number[]): void
 *
 * FLUXO:
 * Chamado pelo hook `useScanner.js` (na função `entregar`) assim que um código
 * do tipo 'isbn' é validado.
 *
 * LIMITACOES:
 * - Em iOS/Safari e navegadores em modo silencioso, o `AudioContext` pode exigir
 *   interação prévia do usuário ou ser bloqueado pelo sistema.
 * - `navigator.vibrate` não é suportado no iOS Safari nem em navegadores desktop.
 */

/**
 * Emite um bipe curto e suave de confirmação (senoidal, 880Hz).
 */
export function tocarBeepSucesso() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.value = 0.12

    osc.connect(gain).connect(ctx.destination)
    osc.start()
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18)
    osc.stop(ctx.currentTime + 0.19)
  } catch {
    // Falha silenciosa caso o áudio esteja desabilitado
  }
}

/**
 * Aciona o motor de vibração do aparelho caso disponível.
 *
 * @param {number | number[]} [padrao=[40, 30, 40]] Duração ou sequência em milissegundos
 */
export function vibrar(padrao = [40, 30, 40]) {
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      navigator.vibrate(padrao)
    }
  } catch {
    // Ignora restrições do sistema
  }
}
