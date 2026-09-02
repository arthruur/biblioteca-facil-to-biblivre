import { test, describe, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { tocarBeepSucesso, vibrar } from '../audio.js'

describe('core/audio', () => {
  let osciladorCriado = false
  let vibracaoRecebida = null

  beforeEach(() => {
    osciladorCriado = false
    vibracaoRecebida = null

    // Mock de window e AudioContext
    Object.defineProperty(globalThis, 'window', {
      value: {
        AudioContext: class MockAudioContext {
          constructor() {
            this.currentTime = 0
            this.destination = {}
          }
          createOscillator() {
            osciladorCriado = true
            return {
              type: '',
              frequency: { value: 0 },
              connect() { return this },
              start() {},
              stop() {},
            }
          }
          createGain() {
            return {
              gain: {
                value: 0,
                exponentialRampToValueAtTime() {},
              },
              connect() { return this },
            }
          }
        },
      },
      configurable: true,
      writable: true,
    })

    // Mock de vibrate no navigator existente
    if (typeof globalThis.navigator !== 'undefined') {
      Object.defineProperty(globalThis.navigator, 'vibrate', {
        value: (padrao) => { vibracaoRecebida = padrao },
        configurable: true,
        writable: true,
      })
    }
  })

  test('tocarBeepSucesso cria oscilador e configura som', () => {
    tocarBeepSucesso()
    assert.equal(osciladorCriado, true)
  })

  test('tocarBeepSucesso não lança erro quando AudioContext não existe', () => {
    delete globalThis.window.AudioContext
    delete globalThis.window.webkitAudioContext
    assert.doesNotThrow(() => tocarBeepSucesso())
  })

  test('vibrar aciona o motor com o padrão fornecido', () => {
    vibrar([50, 50, 50])
    assert.deepEqual(vibracaoRecebida, [50, 50, 50])
  })

  test('vibrar não quebra quando navigator não tem suporte', () => {
    delete globalThis.navigator.vibrate
    assert.doesNotThrow(() => vibrar([40, 40]))
  })
})
