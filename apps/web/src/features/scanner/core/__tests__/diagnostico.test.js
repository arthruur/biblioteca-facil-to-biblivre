import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import {
  MAX_HISTORICO,
  acumular,
  calcularFps,
  diagnosticarEtapa,
  estadoInicial,
} from '../diagnostico.js'

const passo = (extra = {}) => ({
  t: 1000,
  fase: 'candidatos',
  videoW: 1920,
  videoH: 1080,
  readyState: 4,
  candidatos: 2,
  densidade: 40,
  tentativas: 1,
  achados: 1,
  bruto: null,
  aceito: false,
  ms: 12,
  ...extra,
})

describe('core/diagnostico', () => {
  test('estadoInicial devolve estado novo a cada chamada', () => {
    const a = estadoInicial()
    const b = estadoInicial()
    a.historico.push({ bruto: '1' })
    assert.equal(b.historico.length, 0)
    assert.equal(b.passos, 0)
    assert.equal(b.fase, 'parado')
  })

  test('acumula por etapa: candidatos, salvaguarda e quadro cru', () => {
    let e = estadoInicial()
    e = acumular(e, passo({ t: 1000 }))
    e = acumular(e, passo({ t: 1050, fase: 'salvaguarda', candidatos: 0 }))
    e = acumular(e, passo({ t: 1100, fase: 'espera', candidatos: 0, tentativas: 0, achados: 0 }))

    assert.equal(e.passos, 3)
    assert.equal(e.comCandidatos, 1)
    assert.equal(e.salvaguardas, 1)
    assert.equal(e.quadrosCrus, 1)
    // 'espera' é quadro cru, não conta como etapa 2 que rodou e não achou.
    assert.equal(e.semCandidatos, 1)
    assert.equal(e.tentativas, 2)
    assert.equal(e.achados, 2)
  })

  test('separa código lido e recusado do código aceito', () => {
    let e = estadoInicial()
    e = acumular(e, passo({ bruto: '7891000315507', tipo: 'ean', aceito: false }))
    e = acumular(e, passo({ t: 1100, bruto: '9788535902778', tipo: 'isbn', aceito: true }))

    assert.equal(e.decodificados, 2)
    assert.equal(e.aceitos, 1)
    assert.equal(e.rejeitados, 1)
    assert.equal(e.ultimoBruto, '9788535902778')
    assert.equal(e.historico.length, 2)
    assert.equal(e.historico[0].bruto, '9788535902778', 'o mais recente vem primeiro')
    assert.equal(e.historico[1].aceito, false)
  })

  test('histórico não cresce sem limite', () => {
    let e = estadoInicial()
    for (let i = 0; i < MAX_HISTORICO + 5; i++) {
      e = acumular(e, passo({ t: 1000 + i, bruto: `codigo-${i}` }))
    }
    assert.equal(e.historico.length, MAX_HISTORICO)
    assert.equal(e.historico[0].bruto, `codigo-${MAX_HISTORICO + 4}`)
  })

  test('passos sem código não mexem no histórico já acumulado', () => {
    let e = acumular(estadoInicial(), passo({ bruto: '9788535902778', aceito: true }))
    const antes = e.historico
    e = acumular(e, passo({ t: 1200 }))
    assert.equal(e.historico, antes)
    assert.equal(e.ultimoBruto, '9788535902778')
  })

  test('calcularFps mede pela janela dos carimbos', () => {
    assert.equal(calcularFps([]), 0)
    assert.equal(calcularFps([1000]), 0)
    assert.equal(calcularFps([1000, 1000]), 0)
    assert.equal(calcularFps([0, 100, 200, 300]), 10)
  })

  test('evento nulo não derruba nem altera o estado', () => {
    const e = acumular(estadoInicial(), passo())
    assert.equal(acumular(e, null), e)
  })

  test('diagnosticarEtapa aponta a primeira etapa que travou', () => {
    assert.match(diagnosticarEtapa(estadoInicial()), /nenhum passo/)

    let semQuadro = acumular(estadoInicial(), passo({ videoW: 0, videoH: 0, fase: 'espera' }))
    assert.match(diagnosticarEtapa(semQuadro), /não entrega quadro/)

    let semCandidato = estadoInicial()
    semCandidato = acumular(semCandidato, passo({ fase: 'salvaguarda', candidatos: 0 }))
    assert.match(diagnosticarEtapa(semCandidato), /etapa 2/)

    let semLeitura = acumular(estadoInicial(), passo())
    assert.match(diagnosticarEtapa(semLeitura), /não lê nada/)

    let soRecusado = acumular(estadoInicial(), passo({ bruto: '789100', tipo: 'ean' }))
    assert.match(diagnosticarEtapa(soRecusado), /recusados/)

    const completo = acumular(estadoInicial(), passo({ bruto: '9788535902778', aceito: true }))
    assert.match(diagnosticarEtapa(completo), /fecharam/)
  })
})
