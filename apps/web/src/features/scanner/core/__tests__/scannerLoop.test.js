import { test, describe, before } from 'node:test'
import assert from 'node:assert/strict'

before(() => {
  globalThis.document = {
    createElement(tag) {
      if (tag === 'canvas') {
        return {
          width: 0,
          height: 0,
          getContext: () => ({
            drawImage() {},
            getImageData: () => ({ data: new Uint8ClampedArray(320 * 180 * 4) }),
          }),
        }
      }
      return {}
    },
  }
})

import {
  INTERVALO_ATIVO,
  INTERVALO_OCIOSO,
  INTERVALO_PAUSA,
  executarPassoLeitura,
} from '../scannerLoop.js'

describe('core/scannerLoop', () => {
  test('constantes de temporização estão configuradas corretamente', () => {
    assert.equal(INTERVALO_ATIVO, 45)
    assert.equal(INTERVALO_OCIOSO, 90)
    assert.equal(INTERVALO_PAUSA, 450)
  })

  test('executarPassoLeitura retorna INTERVALO_OCIOSO quando vídeo não está pronto', async () => {
    const ctx = {
      video: { videoWidth: 0, readyState: 1 },
      detector: {},
      alvo: {},
    }
    const res = await executarPassoLeitura(ctx)
    assert.equal(res.proxima, INTERVALO_OCIOSO)
    assert.equal(res.leu, false)
  })

  test('executarPassoLeitura limpa deteccoes e desacelera quando não há candidatos', async () => {
    let limpou = false
    const mockDetector = {
      detect: async () => [],
    }

    const ctx = {
      video: { videoWidth: 1920, videoHeight: 1080, readyState: 4 },
      detector: mockDetector,
      alvo: { largura: 0.86, altura: 0.62 },
      ultimoCandidatoRef: { current: { x: 0.2 } },
      candidatoEstavelInicioRef: { current: 123 },
      ultimoFullScanRef: { current: Date.now() },
      aoAtualizarDeteccoes: () => {},
      aoLimparDeteccoesDebounced: () => { limpou = true },
      aoLerCodigo: () => true,
    }

    const res = await executarPassoLeitura(ctx)
    assert.equal(res.proxima, INTERVALO_OCIOSO)
    assert.equal(res.leu, false)
    assert.equal(limpou, true)
    assert.equal(ctx.ultimoCandidatoRef.current, null)
  })

  test('executarPassoLeitura aciona salvaguarda quando tempo ocioso expira', async () => {
    let salvaguardaExecutada = false
    const mockDetector = {
      detect: async () => {
        salvaguardaExecutada = true
        return [{ rawValue: '9788535902778', boundingBox: { x: 900, y: 500, width: 100, height: 50 } }]
      },
    }

    let codigoLido = null
    const ctx = {
      video: { videoWidth: 1920, videoHeight: 1080, readyState: 4 },
      detector: mockDetector,
      alvo: { largura: 0.86, altura: 0.62 },
      ultimoCandidatoRef: { current: null },
      candidatoEstavelInicioRef: { current: 0 },
      ultimoFullScanRef: { current: 0 }, // força expiração da salvaguarda
      aoAtualizarDeteccoes: () => {},
      aoLimparDeteccoesDebounced: () => {},
      aoLerCodigo: (cod) => { codigoLido = cod; return true },
    }

    const res = await executarPassoLeitura(ctx)
    assert.equal(salvaguardaExecutada, true)
    assert.equal(codigoLido, '9788535902778')
    assert.equal(res.proxima, INTERVALO_PAUSA)
    assert.equal(res.leu, true)
  })
})
