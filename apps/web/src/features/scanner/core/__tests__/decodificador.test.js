import { test, describe, before } from 'node:test'
import assert from 'node:assert/strict'

before(() => {
  globalThis.window = {
    BarcodeDetector: class MockBarcodeDetector {
      constructor(opts) {
        this.formats = opts?.formats || []
      }
      static async getSupportedFormats() {
        return ['ean_13', 'ean_8', 'code_128']
      }
      async detect() {
        return [{ rawValue: '9788535902778', boundingBox: { width: 200, height: 100 } }]
      }
    },
  }
})

import {
  FORMATOS_NATIVOS,
  formatosNativos,
  criarDetectorNativo,
  decodificarFoto,
  executarLeituraFoto,
} from '../decodificador.js'

describe('core/decodificador', () => {
  test('FORMATOS_NATIVOS inclui ean_13', () => {
    assert.ok(FORMATOS_NATIVOS.includes('ean_13'))
  })

  test('formatosNativos devolve formatos disponíveis contendo ean_13', async () => {
    const formatos = await formatosNativos()
    assert.ok(Array.isArray(formatos))
    assert.ok(formatos.includes('ean_13'))
  })

  test('criarDetectorNativo instancia BarcodeDetector', () => {
    const detector = criarDetectorNativo(['ean_13'])
    assert.ok(detector !== null)
    assert.deepEqual(detector.formats, ['ean_13'])
  })

  test('executarLeituraFoto avisa e entrega código quando foto é válida', async () => {
    let entregue = null
    let status = null
    globalThis.createImageBitmap = async () => ({ close: () => {} })

    const mockArquivo = new Blob(['fake-img'], { type: 'image/jpeg' })
    await executarLeituraFoto({
      arquivo: mockArquivo,
      formatos: ['ean_13'],
      anunciar: (s) => { status = s },
      entregar: (t) => { entregue = t; return true },
      classificarCodigo: (t) => ({ codigo: t }),
    })

    assert.equal(entregue, '9788535902778')
    assert.ok(status.includes('9788535902778'))
  })

  test('decodificarFoto edge case: retorna null para entrada vazia ou inválida', async () => {
    const res = await decodificarFoto(null, null)
    assert.equal(res, null)
  })
})
