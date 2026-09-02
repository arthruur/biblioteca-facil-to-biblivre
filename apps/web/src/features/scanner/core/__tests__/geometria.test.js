import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import {
  ALVO,
  calcularArea,
  maiorArea,
  estaDentroDoAlvo,
  maiorDentroDoAlvo,
  normalizarCaixa,
} from '../geometria.js'

describe('core/geometria', () => {
  describe('calcularArea', () => {
    test('calcula área correta de retângulo', () => {
      assert.equal(calcularArea({ width: 100, height: 50 }), 5000)
    })

    test('edge case: retorna 0 para entradas nulas ou vazias', () => {
      assert.equal(calcularArea(null), 0)
      assert.equal(calcularArea({}), 0)
      assert.equal(calcularArea({ width: 'abc' }), 0)
    })
  })

  describe('maiorArea', () => {
    test('encontra o código com maior área', () => {
      const codigos = [
        { rawValue: 'menor', boundingBox: { width: 10, height: 10 } },
        { rawValue: 'maior', boundingBox: { width: 100, height: 50 } },
        { rawValue: 'medio', boundingBox: { width: 20, height: 20 } },
      ]
      const escolhido = maiorArea(codigos)
      assert.equal(escolhido?.rawValue, 'maior')
    })

    test('edge case: lista vazia ou nula retorna null', () => {
      assert.equal(maiorArea([]), null)
      assert.equal(maiorArea(null), null)
    })
  })

  describe('estaDentroDoAlvo', () => {
    test('retorna true para caixa centralizada', () => {
      // Centro em 960, 540 (cx = 0.5, cy = 0.5)
      const caixa = { x: 910, y: 515, width: 100, height: 50 }
      assert.equal(estaDentroDoAlvo(caixa, 1920, 1080, ALVO), true)
    })

    test('retorna false para caixa no canto externo', () => {
      // Centro em 50, 50 (cx = 0.026, cy = 0.046)
      const caixa = { x: 0, y: 0, width: 100, height: 100 }
      assert.equal(estaDentroDoAlvo(caixa, 1920, 1080, ALVO), false)
    })

    test('edge case: dimensões zeradas ou nulas', () => {
      assert.equal(estaDentroDoAlvo(null, 1920, 1080), false)
      assert.equal(estaDentroDoAlvo({ x: 0, y: 0, width: 10, height: 10 }, 0, 0), false)
    })
  })

  describe('maiorDentroDoAlvo', () => {
    test('ignora caixas maiores fora do alvo e escolhe a maior de dentro', () => {
      // Caixa no canto extremo esquerdo (cx = 25/1920 = 0.013, fora da margem de 0.07)
      const fora = { rawValue: 'fora', boundingBox: { x: 0, y: 0, width: 50, height: 50 } }
      const dentro = { rawValue: 'certo-dentro', boundingBox: { x: 900, y: 500, width: 150, height: 80 } }
      assert.equal(maiorDentroDoAlvo([fora, dentro], 1920, 1080)?.rawValue, 'certo-dentro')
    })

    test('edge case: lista vazia retorna null', () => {
      assert.equal(maiorDentroDoAlvo([], 1920, 1080), null)
    })
  })

  describe('normalizarCaixa', () => {
    test('converte coordenadas absolutas para fração 0..1', () => {
      const b = { x: 192, y: 108, width: 384, height: 216 }
      const res = normalizarCaixa(b, 1920, 1080, 'isbn', '9788535902778', true)
      assert.equal(res.x, 0.1)
      assert.equal(res.y, 0.1)
      assert.equal(res.w, 0.2)
      assert.equal(res.h, 0.2)
      assert.equal(res.tipo, 'isbn')
      assert.equal(res.dentroAlvo, true)
    })
  })
})
