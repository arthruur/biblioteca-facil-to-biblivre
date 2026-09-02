import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { api } from './api/client'

/**
 * Duas telas, duas posturas (docs/SPEC_UI.md §1).
 *
 * O roteamento é a coisa mais simples que resolve: só existem `/` e `/fila`, e
 * a navegação entre elas é rara — quem está bipando não fica trocando de tela.
 * Uma dependência de router aqui seria peso sem uso.
 *
 * Cada tela entra por `lazy` porque o custo delas é bem diferente: a de
 * escanear carrega o decodificador de código de barras (~350 kB) que a tela de
 * revisão nunca usa. Como o PC abre direto em `/fila` e o celular em `/`, cada
 * um baixa só o que vai rodar.
 */
const TelaEscanear = lazy(() =>
  import('./features/scanner/TelaEscanear').then((m) => ({ default: m.TelaEscanear }))
)
const TelaFila = lazy(() =>
  import('./features/fila/TelaFila').then((m) => ({ default: m.TelaFila }))
)

function rotaAtual() {
  return window.location.pathname.replace(/\/+$/, '') === '/fila' ? 'fila' : 'escanear'
}

export default function App() {
  const [rota, setRota] = useState(rotaAtual)
  const [info, setInfo] = useState(null)
  const [db, setDb] = useState(null)

  const irPara = useCallback((destino) => {
    const caminho = destino === 'fila' ? '/fila' : '/'
    window.history.pushState({}, '', caminho)
    setRota(destino)
  }, [])

  useEffect(() => {
    const aoVoltar = () => setRota(rotaAtual())
    window.addEventListener('popstate', aoVoltar)
    return () => window.removeEventListener('popstate', aoVoltar)
  }, [])

  const recarregarConexao = useCallback(() => {
    api.db.estado().then(setDb).catch(() => setDb(null))
  }, [])

  useEffect(() => {
    api.sistema.info().then(setInfo).catch(() => {})
    recarregarConexao()
  }, [recarregarConexao])

  const conexao = descreverConexao(db)

  return (
    <Suspense fallback={<Carregando />}>
      {rota === 'fila' ? (
        <TelaFila
          conexao={conexao}
          aoIrParaEscanear={() => irPara('escanear')}
          aoRecarregarConexao={recarregarConexao}
        />
      ) : (
        <TelaEscanear
          info={info}
          conexao={conexao}
          aoIrParaFila={() => irPara('fila')}
        />
      )}
    </Suspense>
  )
}

function Carregando() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100dvh',
        color: 'var(--texto-3)',
        fontSize: 'var(--txt-sm)',
      }}
    >
      carregando…
    </div>
  )
}

/**
 * Traduz o diagnóstico do servidor no que a pílula mostra.
 *
 * A regra que não pode ser quebrada: banco desconectado é sempre visível
 * (§7.3). Sem ele todo livro vira obra nova, e o dano é duplicata no acervo —
 * então o estado degradado nunca pode parecer normal.
 */
function descreverConexao(db) {
  if (!db) {
    return {
      conectado: false,
      tom: undefined,
      rotulo: 'verificando…',
      detalhe: 'Consultando o estado da conexão',
      bruto: null,
    }
  }

  const indexados = db.indexados || 0
  if (indexados > 0) {
    return {
      conectado: true,
      tom: 'ok',
      rotulo: `Acervo: ${indexados.toLocaleString('pt-BR')} ISBNs`,
      detalhe: `${db.config?.dbname} em ${db.config?.host}, schema ${db.config?.schema}`,
      bruto: db,
    }
  }

  return {
    conectado: false,
    tom: 'alerta',
    rotulo: db.configurado ? 'Acervo indisponível' : 'Sem conexão',
    detalhe:
      db.erro ||
      'Sem banco, todo livro escaneado entra como obra nova. Clique para conectar.',
    bruto: db,
  }
}
