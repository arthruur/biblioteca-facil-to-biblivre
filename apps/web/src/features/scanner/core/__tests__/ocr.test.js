import { test, describe, before } from 'node:test'
import assert from 'node:assert/strict'

before(() => {
  globalThis.document = {
    createElement(tag) {
      if (tag === 'canvas') {
        return {
          width: 100,
          height: 100,
          getContext() {
            return {
              drawImage() {},
              getImageData: () => ({
                data: new Uint8ClampedArray(100 * 100 * 4).fill(128),
              }),
              putImageData() {},
            }
          },
        }
      }
      return {}
    },
  }
})

import { binarizarOtsu, encerrarWorkerOcr, executarTentativaOcr } from '../ocr.js'

describe('core/ocr', () => {
  test('binarizarOtsu converte canais para preto e branco puros', () => {
    // 4 pixels simulados: 2 escuros e 2 claros
    const imgData = {
      data: new Uint8ClampedArray([
        20, 20, 20, 255,
        30, 30, 30, 255,
        220, 220, 220, 255,
        240, 240, 240, 255,
      ]),
    }
    const binarizado = binarizarOtsu(imgData)
    // Primeiros dois pixels devem ser 0 (fundo preto), últimos dois 255 (frente branca)
    assert.equal(binarizado.data[0], 0)
    assert.equal(binarizado.data[4], 0)
    assert.equal(binarizado.data[8], 255)
    assert.equal(binarizado.data[12], 255)
  })

  test('encerrarWorkerOcr não falha se não houver worker ativo', async () => {
    await assert.doesNotReject(() => encerrarWorkerOcr())
  })

  test('executarTentativaOcr ignora vídeo sem resolução', async () => {
    let anunciado = false
    const mockCtx = {
      video: { videoWidth: 0 },
      regiao: null,
      ocrRodandoRef: { current: false },
      ultimoOcrRef: { current: 0 },
      setOcrAtivo: () => {},
      anunciar: () => { anunciado = true },
      entregar: () => {},
    }

    await executarTentativaOcr(mockCtx)
    assert.equal(anunciado, false)
  })

  test('executarTentativaOcr ignora quando já está rodando', async () => {
    let anunciado = false
    const mockCtx = {
      video: { videoWidth: 1920 },
      regiao: null,
      ocrRodandoRef: { current: true },
      ultimoOcrRef: { current: 0 },
      setOcrAtivo: () => {},
      anunciar: () => { anunciado = true },
      entregar: () => {},
    }

    await executarTentativaOcr(mockCtx)
    assert.equal(anunciado, false)
  })
})
