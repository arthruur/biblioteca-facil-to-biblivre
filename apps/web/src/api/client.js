/**
 * Cliente da API.
 *
 * Uma regra atravessa este arquivo: **a tela do celular nunca bloqueia**
 * (docs/SPEC_UI.md §7). Erro de rede aqui vira exceção que a tela trata como
 * aviso passageiro — nunca modal, nunca espera entre dois bipes.
 */

class ErroApi extends Error {
  constructor(mensagem, status, corpo) {
    super(mensagem)
    this.name = 'ErroApi'
    this.status = status
    this.corpo = corpo
  }
}

async function pedir(caminho, opcoes = {}) {
  let resposta
  try {
    resposta = await fetch(`/api${caminho}`, {
      headers: opcoes.corpo ? { 'Content-Type': 'application/json' } : undefined,
      method: opcoes.metodo || 'GET',
      body: opcoes.corpo ? JSON.stringify(opcoes.corpo) : undefined,
      signal: opcoes.signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ErroApi('Servidor fora de alcance', 0, null)
  }

  const texto = await resposta.text()
  let dados = null
  try {
    dados = texto ? JSON.parse(texto) : null
  } catch {
    dados = { mensagem: texto }
  }

  if (!resposta.ok) {
    // O corpo de erro do backend costuma trazer `mensagem` ou `erro` úteis
    // para a tela; preservar isso é o que permite mostrar a mensagem real do
    // Postgres no modal de conexão em vez de "erro 400".
    const msg = dados?.mensagem || dados?.erro || dados?.detail || resposta.statusText
    throw new ErroApi(msg, resposta.status, dados)
  }
  return dados
}

const json = (caminho) => pedir(caminho)
const post = (caminho, corpo) => pedir(caminho, { metodo: 'POST', corpo })
const put = (caminho, corpo) => pedir(caminho, { metodo: 'PUT', corpo })
const del = (caminho) => pedir(caminho, { metodo: 'DELETE' })

export const api = {
  ErroApi,

  sistema: {
    info: () => json('/sistema/info'),
  },

  lote: {
    listar: () => json('/lote'),
    adicionar: (isbn) => post('/lote', { isbn }),
    quantidade: (isbn, quantidade) =>
      put(`/lote/${encodeURIComponent(isbn)}`, { quantidade }),
    remover: (isbn) => del(`/lote/${encodeURIComponent(isbn)}`),
    limpar: () => del('/lote'),
    enviar: () => post('/lote/enviar'),
  },

  fila: {
    listar: ({ status, busca } = {}) => {
      const q = new URLSearchParams()
      if (status && status !== 'todos') q.set('status', status)
      if (busca) q.set('busca', busca)
      const s = q.toString()
      return json(`/fila${s ? `?${s}` : ''}`)
    },
    stats: () => json('/fila/stats'),
    editar: (id, campos) => put(`/fila/${id}`, campos),
    remover: (id) => del(`/fila/${id}`),
    acoes: (ids, acao) => post('/fila/acoes', { ids, acao }),
    reconsultar: () => post('/fila/reconsultar'),
    exportar: ({ executar = false, ids = null, db = null } = {}) =>
      post('/fila/exportar-biblivre', { executar, ids, db }),
  },

  acervo: {
    status: () => json('/acervo/status'),
    reindexarCache: () => post('/acervo/reindexar-cache'),
  },

  db: {
    estado: () => json('/db'),
    conectar: (credenciais) => post('/db', credenciais),
  },
}

export { ErroApi }
