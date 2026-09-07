/**
 * Classificação local do modo circulação.
 *
 * O que estes testes protegem: a dica que o visor mostra entre o bipe e a resposta
 * de `GET /api/circulacao/resolver`. Nenhum deles afirma o que o código É — só o que
 * a interface arrisca dizer enquanto espera o servidor.
 */

import { test, describe } from 'node:test'
import assert from 'node:assert/strict'

import { classificarCirculacao, normalizarCodigo } from '../../codigos.js'
import { classificarCodigo } from '../../isbn.js'
import {
  FORMATOS_CIRCULACAO,
  FORMATOS_ISBN,
  nomesFormatosReserva,
} from '../decodificador.js'

describe('codigos/normalizarCodigo', () => {
  test('remove os delimitadores * do Code 39', () => {
    assert.equal(normalizarCodigo('*0000000842*'), '0000000842')
  })

  test('remove espaço em volta e colapsa espaço interno', () => {
    assert.equal(normalizarCodigo('  Bib.2019.842  '), 'Bib.2019.842')
    assert.equal(normalizarCodigo(' Bib   2019  842 '), 'Bib 2019 842')
  })

  test('tolera nulo e indefinido', () => {
    assert.equal(normalizarCodigo(null), '')
    assert.equal(normalizarCodigo(undefined), '')
  })
})

describe('codigos/classificarCirculacao — tombo', () => {
  test('reconhece o tombo com o prefixo padrão do instalador', () => {
    assert.deepEqual(classificarCirculacao('Bib.2019.842'), {
      tipo: 'tombo',
      valor: 'Bib.2019.842',
    })
  })

  test('o prefixo não é fixo: vem da configuração do BibLivre', () => {
    for (const bruto of ['UEFS.2024.1', 'ACERVO2.2001.99999', '7.1998.12']) {
      const r = classificarCirculacao(bruto)
      assert.equal(r.tipo, 'tombo', `${bruto} deveria ser tombo`)
      assert.equal(r.valor, bruto)
    }
  })

  test('aceita espaço, hífen e barra como separador, normalizando para ponto', () => {
    for (const bruto of ['Bib 2019 842', 'Bib-2019-842', 'Bib/2019/842', ' bib . 2019 . 842 ']) {
      assert.equal(classificarCirculacao(bruto).valor, bruto.trim().startsWith('bib')
        ? 'bib.2019.842'
        : 'Bib.2019.842')
    }
  })

  test('preserva a caixa do prefixo — o banco compara com "=" em getByAccessionNumber', () => {
    assert.equal(classificarCirculacao('bib.2019.842').valor, 'bib.2019.842')
    assert.equal(classificarCirculacao('BIB.2019.842').valor, 'BIB.2019.842')
  })

  test('tombo dentro dos delimitadores do Code 39', () => {
    assert.deepEqual(classificarCirculacao('*Bib.2019.842*'), {
      tipo: 'tombo',
      valor: 'Bib.2019.842',
    })
  })

  test('ISBN com hífen não vira tombo', () => {
    assert.equal(classificarCirculacao('978-85-359-0277-8').tipo, 'isbn')
  })
})

describe('codigos/classificarCirculacao — ISBN', () => {
  test('ISBN-13 válido é isbn', () => {
    assert.deepEqual(classificarCirculacao('9788535902778'), {
      tipo: 'isbn',
      valor: '9788535902778',
    })
  })

  test('ISBN-10 válido sem zero à esquerda é isbn', () => {
    assert.deepEqual(classificarCirculacao('8535902775'), {
      tipo: 'isbn',
      valor: '8535902775',
    })
  })

  test('EAN-13 de preço não é ISBN e não identifica nada na circulação', () => {
    // Dígito verificador correto, mas fora do prefixo Bookland (978/979).
    assert.equal(classificarCodigo('7891234567895').tipo, 'ean')
    assert.deepEqual(classificarCirculacao('7891234567895'), {
      tipo: 'desconhecido',
      valor: '7891234567895',
    })
  })

  test('13 dígitos com verificador errado não vira número de leitor', () => {
    assert.equal(classificarCirculacao('9788535902779').tipo, 'desconhecido')
  })
})

describe('codigos/classificarCirculacao — número', () => {
  test('id de exemplar como o BibLivre imprime: 10 dígitos com zeros à esquerda', () => {
    assert.deepEqual(classificarCirculacao('*0000000842*'), {
      tipo: 'numero',
      valor: '0000000842',
    })
  })

  test('a carteirinha do leitor tem exatamente a mesma forma — quem separa é o servidor', () => {
    assert.equal(classificarCirculacao('0000000015').tipo, 'numero')
  })

  test('colisão documentada: ISBN-10 começado em zero é lido como número', () => {
    // 0306406152 é ISBN-10 válido E é a cara de um id preenchido com zeros.
    assert.equal(classificarCodigo('0306406152').tipo, 'isbn')
    assert.equal(classificarCirculacao('0306406152').tipo, 'numero')
  })

  test('matrícula digitada solta é número', () => {
    assert.deepEqual(classificarCirculacao('842'), { tipo: 'numero', valor: '842' })
    assert.equal(classificarCirculacao(' 15 ').tipo, 'numero')
  })
})

describe('codigos/classificarCirculacao — lixo', () => {
  test('vazio, nulo e espaço em branco', () => {
    for (const bruto of ['', '   ', null, undefined]) {
      assert.deepEqual(classificarCirculacao(bruto), { tipo: 'desconhecido', valor: '' })
    }
  })

  test('texto sem forma de tombo, ISBN ou número', () => {
    for (const bruto of ['ABC-XYZ', 'http://biblivre.org.br', 'Bib.19.842', '..']) {
      assert.equal(classificarCirculacao(bruto).tipo, 'desconhecido', bruto)
    }
  })

  test('número grande demais para ser id do Postgres', () => {
    assert.equal(classificarCirculacao('12345678901234').tipo, 'desconhecido')
  })
})

describe('codigos/formatos por modo', () => {
  test('o modo isbn continua com a lista de sempre', () => {
    assert.deepEqual([...FORMATOS_ISBN], ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39'])
  })

  test('o modo circulação lê etiqueta linear além do EAN-13', () => {
    assert.ok(FORMATOS_CIRCULACAO.includes('code_39'))
    assert.ok(FORMATOS_CIRCULACAO.includes('code_128'))
    assert.ok(FORMATOS_CIRCULACAO.includes('ean_13'))
  })

  test('o motor de reserva recebe os mesmos formatos, no vocabulário do html5-qrcode', () => {
    assert.deepEqual(nomesFormatosReserva('circulacao'), ['EAN_13', 'CODE_128', 'CODE_39'])
    assert.deepEqual(nomesFormatosReserva(), ['EAN_13', 'EAN_8', 'UPC_A', 'UPC_E', 'CODE_128', 'CODE_39'])
    assert.deepEqual(nomesFormatosReserva('modo-inexistente'), nomesFormatosReserva('isbn'))
  })
})
