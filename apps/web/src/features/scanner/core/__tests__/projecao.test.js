import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import { enquadrarCover } from '../projecao.js'

describe('core/projecao', () => {
  test('quadro paisagem em visor em pé: corta as laterais e sobra para fora', () => {
    // 1920×1080 num visor de 390×340 (celular): a escala vem da altura.
    const enq = enquadrarCover(1920, 1080, 390, 340)
    assert.ok(Math.abs(enq.escala - 340 / 1080) < 1e-9)
    assert.ok(Math.abs(enq.altura - 340) < 1e-9)
    assert.ok(enq.largura > 390, 'o quadro é mais largo que o visor')
    assert.equal(enq.topo, 0)
    assert.ok(enq.esquerda < 0, 'o excedente sai pelas duas laterais')
    assert.ok(Math.abs(enq.esquerda - (390 - enq.largura) / 2) < 1e-9)
  })

  test('caixa no centro do quadro cai no centro do visor', () => {
    const enq = enquadrarCover(1920, 1080, 390, 340)
    const centroX = enq.esquerda + 0.5 * enq.largura
    const centroY = enq.topo + 0.5 * enq.altura
    assert.ok(Math.abs(centroX - 195) < 1e-9)
    assert.ok(Math.abs(centroY - 170) < 1e-9)
  })

  test('caixa na borda do quadro sai da tela — é o pedaço cortado', () => {
    const enq = enquadrarCover(1920, 1080, 390, 340)
    const bordaEsquerda = enq.esquerda + 0.02 * enq.largura
    assert.ok(bordaEsquerda < 0, 'x=0.02 está na faixa cortada pelo cover')
  })

  test('mesma proporção: nada é cortado', () => {
    const enq = enquadrarCover(1280, 720, 640, 360)
    assert.equal(enq.escala, 0.5)
    assert.equal(enq.esquerda, 0)
    assert.equal(enq.topo, 0)
    assert.equal(enq.largura, 640)
    assert.equal(enq.altura, 360)
  })

  test('quadro em pé em visor deitado: corta topo e base', () => {
    const enq = enquadrarCover(1080, 1920, 800, 400)
    assert.ok(Math.abs(enq.largura - 800) < 1e-9)
    assert.ok(enq.altura > 400)
    assert.equal(enq.esquerda, 0)
    assert.ok(enq.topo < 0)
  })

  test('sem medida de vídeo ou de visor não inventa enquadramento', () => {
    assert.deepEqual(enquadrarCover(0, 0, 390, 340), {
      escala: 1, largura: 390, altura: 340, esquerda: 0, topo: 0,
    })
    assert.deepEqual(enquadrarCover(1920, 1080, 0, 0), {
      escala: 1, largura: 0, altura: 0, esquerda: 0, topo: 0,
    })
    assert.equal(enquadrarCover(undefined, undefined, undefined, undefined).escala, 1)
  })
})
