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

/**
 * Identidade de QUEM opera, que e outra coisa do que em QUAL aparelho.
 *
 * O dispositivo separa bandejas de captura; a sessao diz quem esta no balcao, e
 * e ela que vira `lendings.created_by`. Um mesmo celular troca de operador no
 * meio do turno, e o mesmo operador atende em dois aparelhos — por isso sao
 * dois cabecalhos, nao um.
 *
 * Vive so em memoria, como a senha do Postgres do lado do servidor. Se a tela
 * quiser sobreviver a um F5, quem decide guardar (e onde) e ela.
 */
let _sessao = null

export function definirSessao(token) {
  _sessao = token || null
}

export function temSessao() {
  return !!_sessao
}

function cabecalhosSessao() {
  return _sessao ? { 'X-Sessao': _sessao } : {}
}

async function pedir(caminho, opcoes = {}) {
  let resposta
  try {
    resposta = await fetch(`/api${caminho}`, {
      headers: {
        // FormData define o proprio Content-Type, com o boundary do multipart:
        // declarar 'application/json' aqui faria o upload do .bkp chegar
        // ilegivel do outro lado.
        ...(opcoes.corpo ? { 'Content-Type': 'application/json' } : {}),
        ...(opcoes.comDispositivo ? cabecalhosDispositivo() : {}),
        ...(opcoes.comSessao ? cabecalhosSessao() : {}),
      },
      method: opcoes.metodo || 'GET',
      body: opcoes.formulario || (opcoes.corpo ? JSON.stringify(opcoes.corpo) : undefined),
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

function enviarArquivo(caminho, arquivo, campo = 'arquivo') {
  const formulario = new FormData()
  formulario.append(campo, arquivo)
  return pedir(caminho, { metodo: 'POST', formulario })
}

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

  /**
   * Migracao de acervo legado. Tres passos separados de proposito: enviar o
   * backup, conferir (nao toca no banco) e gravar (uma transacao so).
   *
   * `conferir` e `executar` devolvem na hora — o trabalho corre no servidor, e
   * quem acompanha e o laco de `estado()`.
   */
  migracao: {
    estado: (signal) => json('/migracao', { signal }),
    versao: (signal) => json('/migracao/versao', { signal }),
    enviarBackup: (arquivo) => enviarArquivo('/migracao/backup', arquivo),
    conferir: ({ opcoes = null, db = null } = {}) =>
      post('/migracao/conferir', { opcoes, db }),
    executar: ({ opcoes = null, db = null } = {}) =>
      post('/migracao/executar', { opcoes, db, confirmado: true }),
    descartar: () => del('/migracao'),
    urlArquivo: (nome) => `/api/migracao/arquivos/${encodeURIComponent(nome)}`,
  },

  acervo: {
    status: () => json('/acervo/status'),
    reindexarCache: () => post('/acervo/reindexar-cache'),
  },

  /**
   * Quem esta no balcao. O token volta no corpo e vai em `X-Sessao` daqui para
   * frente — `definirSessao` e quem liga uma coisa na outra.
   */
  sessao: {
    entrar: (usuario, senha) => post('/sessao', { usuario, senha }),
    atual: () => json('/sessao', { comSessao: true }),
    sair: () => del('/sessao', { comSessao: true }),
  },

  /**
   * O balcao: emprestimo, devolucao, renovacao e consulta.
   *
   * Aqui a tela ESPERA a resposta — ao contrario da captura, onde bipe e
   * rascunho e o servidor reconcilia depois. Dizer "levou" antes do commit
   * seria mentir para quem esta na frente do balcao (docs/SPEC_UI.md).
   *
   * `resolver` existe para que ninguem precise escolher "tipo" antes de bipar:
   * manda o codigo cru, o servidor diz se e tombo, ISBN ou leitor.
   */
  circulacao: {
    resolver: (codigo) =>
      json(`/circulacao/resolver?codigo=${encodeURIComponent(codigo)}`, { comSessao: true }),
    leitor: (userId) => json(`/circulacao/leitor/${userId}`, { comSessao: true }),
    leitores: (busca) =>
      json(`/circulacao/leitores?busca=${encodeURIComponent(busca)}`, { comSessao: true }),
    exemplar: (holdingId) =>
      json(`/circulacao/exemplar/${holdingId}`, { comSessao: true }),
    emprestar: ({ holding_id, user_id, forcar_avisos = false }) =>
      post('/circulacao/emprestimos', { holding_id, user_id, forcar_avisos },
           { comSessao: true }),
    devolver: ({ holding_id = null, lending_id = null }) =>
      post('/circulacao/devolucoes', { holding_id, lending_id }, { comSessao: true }),
    renovar: (lendingId) =>
      post('/circulacao/renovacoes', { lending_id: lendingId }, { comSessao: true }),
    pendencias: (tipo = 'atrasados', signal) =>
      json(`/circulacao/pendencias?tipo=${encodeURIComponent(tipo)}`,
           { comSessao: true, signal }),
  },

  /**
   * O que sobrava fora do app depois de gravar: reindexar a base, derrubar os
   * caches estaticos, conferir e gerar o `.b5bz`.
   *
   * Reindex e backup DISPARAM e voltam na hora; quem acompanha e o GET
   * correspondente, num laco — sao minutos de trabalho do lado do Tomcat.
   */
  manutencao: {
    estado: (signal) => json('/manutencao', { signal, comSessao: true }),
    configurarBiblivre: ({ url, usuario, senha }) =>
      post('/manutencao/biblivre', { url, usuario, senha }, { comSessao: true }),
    reindexar: () => post('/manutencao/reindexar', null, { comSessao: true }),
    progressoReindex: (signal) =>
      json('/manutencao/reindexar', { signal, comSessao: true }),
    caches: () => post('/manutencao/caches', null, { comSessao: true }),
    conferencia: () => post('/manutencao/conferencia', null, { comSessao: true }),
    backup: (tipo = 'full') => post('/manutencao/backup', { tipo }, { comSessao: true }),
    estadoBackup: (signal) => json('/manutencao/backup', { signal, comSessao: true }),
  },

  db: {
    estado: () => json('/db'),
    conectar: (credenciais) => post('/db', credenciais),
  },
}

export { ErroApi }
