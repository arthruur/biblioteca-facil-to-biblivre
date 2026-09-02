/**
 * Validação de ISBN no cliente.
 *
 * Mora aqui, e não no servidor, porque o scanner precisa decidir em tempo de
 * frame se o que ele acabou de ler é um livro. A contracapa costuma ter mais
 * de um código: o EAN-5 do preço colado ao lado do ISBN, e em revista o 977 do
 * periódico. Aceitar "qualquer coisa com 13 dígitos" catalogaria a etiqueta de
 * preço como se fosse a obra — e quem descobre isso é o revisor, três telas
 * depois.
 */

/** Prefixo Bookland: todo ISBN impresso como código de barras começa assim. */
const BOOKLAND = /^97[89]/

export function digitoIsbn13Confere(isbn13) {
  if (!/^\d{13}$/.test(isbn13)) return false
  let s = 0
  for (let i = 0; i < 12; i++) s += Number(isbn13[i]) * (i % 2 === 0 ? 1 : 3)
  return (10 - (s % 10)) % 10 === Number(isbn13[12])
}

export function digitoIsbn10Confere(isbn10) {
  if (!/^\d{9}[\dX]$/.test(isbn10)) return false
  let s = 0
  for (let i = 0; i < 9; i++) s += Number(isbn10[i]) * (10 - i)
  s += isbn10[9] === 'X' ? 10 : Number(isbn10[9])
  return s % 11 === 0
}

function limpar(texto) {
  return String(texto || '')
    .replace(/[\s\-.]/g, '')
    .toUpperCase()
}

/**
 * Classifica o que o decodificador entregou.
 *
 * Devolver `ean` em vez de `null` para um código válido que não é ISBN é
 * deliberado: assim a tela consegue dizer "isto é um código de preço" em vez
 * de ficar muda enquanto a pessoa insiste no mesmo livro.
 */
export function classificarCodigo(texto) {
  const codigo = limpar(texto)

  if (/^\d{13}$/.test(codigo)) {
    if (!digitoIsbn13Confere(codigo)) return { tipo: 'invalido', codigo }
    return BOOKLAND.test(codigo)
      ? { tipo: 'isbn', codigo }
      : { tipo: 'ean', codigo }
  }

  // ISBN-10 aparece em etiqueta de biblioteca impressa em CODE-39/128.
  if (/^\d{9}[\dX]$/.test(codigo)) {
    return digitoIsbn10Confere(codigo)
      ? { tipo: 'isbn', codigo }
      : { tipo: 'invalido', codigo }
  }

  return { tipo: 'desconhecido', codigo }
}

/** Atalho para quem só quer o ISBN ou nada. */
export function ehIsbn(texto) {
  const r = classificarCodigo(texto)
  return r.tipo === 'isbn' ? r.codigo : null
}

/**
 * ISBN digitado à mão.
 *
 * Aqui o dígito verificador vale mais do que no scanner: o decodificador já
 * valida o EAN internamente, o teclado não valida nada. Um dígito trocado sem
 * checagem entra na fila como um livro que não existe.
 */
export function normalizarIsbnDigitado(texto) {
  const d = String(texto || '')
    .replace(/[^0-9Xx]/g, '')
    .toUpperCase()
  if (d.length === 13) return digitoIsbn13Confere(d) ? d : null
  if (d.length === 10) return digitoIsbn10Confere(d) ? d : null
  return null
}

/**
 * Todos os ISBN-13 plausíveis dentro de uma tira de dígitos do OCR.
 *
 * O OCR entrega a linha inteira grudada — ISBN mais o add-on de preço, às
 * vezes um dígito de sujeira na frente. Varremos toda janela de 13 e deixamos
 * o dígito verificador escolher.
 */
export function isbnsEmDigitos(digitos) {
  const achados = []
  for (let i = 0; i + 13 <= digitos.length; i++) {
    const candidato = digitos.slice(i, i + 13)
    if (BOOKLAND.test(candidato) && digitoIsbn13Confere(candidato)) {
      achados.push(candidato)
    }
  }
  return achados
}
