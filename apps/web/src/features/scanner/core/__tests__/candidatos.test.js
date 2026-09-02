import { test, describe, before } from 'node:test'
import assert from 'node:assert/strict'

class MockContext2D {
  constructor(width, height) {
    this.width = width
    this.height = height
    this.data = new Uint8ClampedArray(width * height * 4)
    // Preenche com padrão de barras no centro: y = 60..120, x = 90..230
    for (let y = 60; y < 120; y++) {
      for (let x = 90; x < 230; x++) {
        const val = (x % 4 < 2) ? 15 : 240
        const idx = (y * width + x) * 4
        this.data[idx] = val
        this.data[idx + 1] = val
        this.data[idx + 2] = val
        this.data[idx + 3] = 255
      }
    }
  }
  drawImage() {}
  getImageData() {
    return { data: this.data }
  }
}

class MockCanvas {
  constructor() {
    this.width = 0
    this.height = 0
    this.ctx = null
  }
  getContext() {
    if (!this.ctx || this.ctx.width !== this.width || this.ctx.height !== this.height) {
      this.ctx = new MockContext2D(this.width, this.height)
    }
    return this.ctx
  }
}

before(() => {
  globalThis.document = {
    createElement(tag) {
      if (tag === 'canvas') return new MockCanvas()
      return {}
    },
  }
})

import { encontrarCandidatos, recortarRegiao } from '../candidatos.js'

describe('core/candidatos', () => {
  const videoValido = { videoWidth: 1920, videoHeight: 1080 }
  const alvo = { largura: 0.86, altura: 0.62 }

  test('encontrarCandidatos localiza barras e expande para o quadrado do código', () => {
    const candidatos = encontrarCandidatos(videoValido, alvo)
    assert.ok(candidatos.length > 0, 'Deve detectar o candidato de barras')

    const c = candidatos[0]
    assert.ok(c.largura > c.mioloBarras.largura, 'Quadrado deve ter zonas de silêncio')
    assert.ok(c.altura > c.mioloBarras.altura, 'Quadrado deve ter margem superior e números inferiores')
    assert.ok(c.x <= c.mioloBarras.x, 'Início x deve ser menor ou igual ao miolo')
    assert.ok(c.y <= c.mioloBarras.y, 'Início y deve ser menor ou igual ao miolo')
  })

  test('encontrarCandidatos edge case: entradas vazias ou nulas retornam []', () => {
    assert.deepEqual(encontrarCandidatos(null), [])
    assert.deepEqual(encontrarCandidatos({ videoWidth: 0, videoHeight: 0 }), [])
  })

  test('recortarRegiao gera canvas com coordenadas de origem', () => {
    const candidatos = encontrarCandidatos(videoValido, alvo)
    const recorte = recortarRegiao(videoValido, candidatos[0])
    assert.ok(recorte !== null)
    assert.ok(recorte.width > 0 && recorte.height > 0)
    assert.equal(recorte.origem.videoW, 1920)
    assert.equal(recorte.origem.videoH, 1080)
  })

  test('recortarRegiao edge case: parâmetros nulos', () => {
    assert.equal(recortarRegiao(null, null), null)
    assert.equal(recortarRegiao(videoValido, null), null)
  })
})
