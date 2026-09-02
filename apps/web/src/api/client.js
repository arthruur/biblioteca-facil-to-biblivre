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

/**
 * Identidade do aparelho.
 *
 * Vai em `X-Dispositivo` nas rotas do lote, e e o que separa a bandeja deste
 * celular da do celular ao lado (ver packages/catalogacao/.../lotes.py). Quem
 * define e `useDispositivo`, na subida da tela; enquanto ninguem definir, as
 * chamadas saem sem cabecalho e caem no lote do balcao.
 */
let _dispositivo = null

export function definirDispositivo(id) {
  _dispositivo = id ? { id } : null
}

function cabecalhosDispositivo() {
  if (!_dispositivo) return {}
  // So o id, que e um uuid — ASCII e seguro num cabecalho. O nome ("Celular da
  // Ana") tem acento e espaco, e viaja pelo corpo de `lotes.renomear`, nao
  // aqui: cabecalho HTTP obrigaria a percent-encode e o painel receberia
  // "Celular%20da%20Ana".
  return { 'X-Dispositivo': _dispositivo.id }
}

async function pedir(caminho, opcoes = {}) {
  let resposta
  try {
    resposta = await fetch(`/api${caminho}`, {
      headers: {
        ...(opcoes.corpo ? { 'Content-Type': 'application/json' } : {}),
        ...(opcoes.comDispositivo ? cabecalhosDispositivo() : {}),
      },
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

const json = (caminho, opcoes) => pedir(caminho, opcoes)
const post = (caminho, corpo, opcoes) =>
  pedir(caminho, { ...opcoes, metodo: 'POST', corpo })
const put = (caminho, corpo, opcoes) =>
  pedir(caminho, { ...opcoes, metodo: 'PUT', corpo })
const del = (caminho, opcoes) => pedir(caminho, { ...opcoes, metodo: 'DELETE' })

// O lote e sempre "o meu lote": estas chamadas levam a identidade do aparelho.
const meu = { comDispositivo: true }

export const api = {
  ErroApi,

  sistema: {
    info: () => json('/sistema/info'),
  },

  lote: {
    listar: () => json('/lote', meu),
    adicionar: (isbn) => post('/lote', { isbn }, meu),
    quantidade: (isbn, quantidade) =>
      put(`/lote/${encodeURIComponent(isbn)}`, { quantidade }, meu),
    remover: (isbn) => del(`/lote/${encodeURIComponent(isbn)}`, meu),
    limpar: () => del('/lote', meu),
    enviar: () => post('/lote/enviar', null, meu),
  },

  /**
   * O painel do PC: as N bandejas.
   *
   * Sem cabecalho de dispositivo de proposito — o PC nao e um dos aparelhos
   * bipando, ele olha todos.
   */
  lotes: {
    painel: (signal) => json('/lotes', { signal }),
    versao: (signal) => json('/lotes/versao', { signal }),
    renomear: (id, nome) => put(`/lotes/${encodeURIComponent(id)}`, { nome }),
    esquecer: (id) => del(`/lotes/${encodeURIComponent(id)}`),
    limpar: (id) => del(`/lotes/${encodeURIComponent(id)}/itens`),
    enviar: (id) => post(`/lotes/${encodeURIComponent(id)}/enviar`),
    enviarTudo: () => post('/lotes/enviar-tudo'),
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
