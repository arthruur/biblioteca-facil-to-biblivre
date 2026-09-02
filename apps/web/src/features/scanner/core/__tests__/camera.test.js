import { test, describe, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import {
  RESTRICOES_VIDEO,
  ajustarCamera,
  alternarLanterna,
  aplicarZoom,
  detectarLanterna,
  fecharCamera,
  obterTrackDoVideo,
} from '../camera.js'

describe('core/camera', () => {
  test('RESTRICOES_VIDEO define câmera traseira e 1080p', () => {
    assert.equal(RESTRICOES_VIDEO.facingMode.ideal, 'environment')
    assert.equal(RESTRICOES_VIDEO.width.ideal, 1920)
  })

  test('ajustarCamera extrai capacidades de lanterna e zoom', async () => {
    let constraintsAplicadas = null
    const mockTrack = {
      getCapabilities() {
        return {
          torch: true,
          focusMode: ['continuous', 'manual'],
          zoom: { min: 1, max: 5, step: 0.2 },
        }
      },
      async applyConstraints(c) {
        constraintsAplicadas = c
      },
    }

    const resultado = await ajustarCamera(mockTrack)
    assert.equal(resultado.lanterna, true)
    assert.deepEqual(resultado.zoom, { min: 1, max: 5, passo: 0.2 })
    assert.equal(constraintsAplicadas?.advanced?.[0]?.focusMode, 'continuous')
  })

  test('ajustarCamera edge case: track nulo ou sem capabilities', async () => {
    const resNulo = await ajustarCamera(null)
    assert.deepEqual(resNulo, { lanterna: false, zoom: null })

    const resVazio = await ajustarCamera({})
    assert.deepEqual(resVazio, { lanterna: false, zoom: null })
  })

  test('alternarLanterna aplica restrição de torch', async () => {
    let tochaValor = null
    const mockTrack = {
      async applyConstraints(c) {
        tochaValor = c?.advanced?.[0]?.torch
      },
    }

    const ok = await alternarLanterna(mockTrack, true)
    assert.equal(ok, true)
    assert.equal(tochaValor, true)

    const falha = await alternarLanterna(null, true)
    assert.equal(falha, false)
  })

  test('aplicarZoom aplica restrição de zoom', async () => {
    let zoomValor = null
    const mockTrack = {
      async applyConstraints(c) {
        zoomValor = c?.advanced?.[0]?.zoom
      },
    }

    await aplicarZoom(mockTrack, 2.5)
    assert.equal(zoomValor, 2.5)
  })

  test('fecharCamera encerra todas as faixas do stream e do vídeo', () => {
    let streamParado = false
    let videoTrackParada = false

    const mockStream = {
      getTracks: () => [{ stop: () => { streamParado = true } }],
    }
    const mockVideo = {
      srcObject: {
        getTracks: () => [{ stop: () => { videoTrackParada = true } }],
      },
    }

    fecharCamera(mockStream, mockVideo)
    assert.equal(streamParado, true)
    assert.equal(videoTrackParada, true)
    assert.equal(mockVideo.srcObject, null)
  })

  test('detectarLanterna aceita os três jeitos de anunciar torch', () => {
    assert.equal(detectarLanterna({ getCapabilities: () => ({ torch: true }) }), true)
    assert.equal(
      detectarLanterna({ getCapabilities: () => ({ torch: [false, true] }) }),
      true,
      'Android costuma anunciar torch como lista'
    )
    assert.equal(
      detectarLanterna({ getCapabilities: () => ({}), getSettings: () => ({ torch: false }) }),
      true,
      'sem capabilities, torch em settings já basta'
    )
    assert.equal(detectarLanterna({ getCapabilities: () => ({ torch: false }) }), false)
    assert.equal(detectarLanterna({}), false)
    assert.equal(detectarLanterna(null), false)
  })

  test('alternarLanterna devolve false quando o aparelho aceita e não acende', async () => {
    const mentiroso = {
      async applyConstraints() {},
      getSettings: () => ({ torch: false }),
    }
    assert.equal(await alternarLanterna(mentiroso, true), false)

    const honesto = {
      torch: false,
      async applyConstraints(c) { this.torch = c.advanced[0].torch },
      getSettings() { return { torch: this.torch } },
    }
    assert.equal(await alternarLanterna(honesto, true), true)
    assert.equal(honesto.torch, true)
    assert.equal(await alternarLanterna(honesto, false), true)
    assert.equal(honesto.torch, false)
  })

  test('alternarLanterna devolve false quando a restrição é recusada', async () => {
    const recusa = { async applyConstraints() { throw new Error('OverconstrainedError') } }
    assert.equal(await alternarLanterna(recusa, true), false)
  })

  test('obterTrackDoVideo recupera a faixa que o motor de reserva abriu', () => {
    const faixa = { id: 'traseira' }
    const video = { srcObject: { getVideoTracks: () => [faixa] } }
    assert.equal(obterTrackDoVideo(video), faixa)
    assert.equal(obterTrackDoVideo({ srcObject: { getVideoTracks: () => [] } }), null)
    assert.equal(obterTrackDoVideo({}), null)
    assert.equal(obterTrackDoVideo(null), null)
  })
})
