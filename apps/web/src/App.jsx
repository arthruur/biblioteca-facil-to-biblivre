import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { BottomNav, Navbar } from './components'
import { ModalBanco } from './features/fila/ModalBanco'
import { ModalExport } from './features/fila/ModalExport'

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
  const [stats, setStats] = useState(null)
  const [loteQtd, setLoteQtd] = useState(0)
  const [modalGlobal, setModalGlobal] = useState(null)
  const [reconsultando, setReconsultando] = useState(false)
  const [exportando, setExportando] = useState(false)
  const [itensParaExportar, setItensParaExportar] = useState([])

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

  const recarregarConexao = useCallback(async () => {
    try {
      const estado = await api.db.estado()
      setDb(estado)
    } catch {
      setDb(null)
    }
  }, [])

  const carregarStats = useCallback(async () => {
    try {
      const s = await api.fila.stats()
      setStats(s)
    } catch {}
  }, [])

  const carregarLoteQtd = useCallback(async () => {
    try {
      const l = await api.lote.listar()
      setLoteQtd(l?.itens?.length || 0)
    } catch {}
  }, [])

  useEffect(() => {
    api.sistema.info().then(setInfo).catch(() => {})
    recarregarConexao()
    carregarStats()
    carregarLoteQtd()
  }, [recarregarConexao, carregarStats, carregarLoteQtd])

  const reconsultarAcervo = useCallback(async () => {
    setReconsultando(true)
    try {
      await api.fila.reconsultar()
      await Promise.all([carregarStats(), recarregarConexao()])
    } catch (e) {
      console.error('Falha ao reconsultar acervo:', e)
    } finally {
      setReconsultando(false)
    }
  }, [carregarStats, recarregarConexao])

  const abrirExport = useCallback(async (itensEspecificos = null) => {
    if (itensEspecificos && itensEspecificos.length > 0) {
      setItensParaExportar(itensEspecificos)
      setModalGlobal('export')
      return
    }
    try {
      const lista = await api.fila.listar({ status: 'pendente,revisado' })
      const alvos = (lista.itens || []).filter((i) => i.status !== 'exportado')
      setItensParaExportar(alvos)
      setModalGlobal('export')
    } catch (e) {
      console.error('Falha ao carregar itens para export:', e)
    }
  }, [])

  const executarExport = useCallback(
    async ({ executar, senha }) => {
      setExportando(true)
      try {
        const ids =
          itensParaExportar.length > 0 ? itensParaExportar.map((i) => i.id) : null
        const r = await api.fila.exportar({
          executar,
          ids,
          db: senha ? { senha } : null,
        })
        setModalGlobal(null)
        await Promise.all([carregarStats(), recarregarConexao()])
        if (rota !== 'fila') {
          irPara('fila')
        }
        return r
      } finally {
        setExportando(false)
      }
    },
    [itensParaExportar, carregarStats, recarregarConexao, rota, irPara]
  )

  const conexao = descreverConexao(db)

  return (
    <div className="app-shell">
      {/* Navbar Desktop Persistente */}
      <Navbar
        rotaAtiva={rota}
        aoNavegar={irPara}
        loteQtd={loteQtd}
        filaQtd={stats?.total || 0}
        conexao={conexao}
        aoAbrirBanco={() => setModalGlobal('banco')}
        aoAbrirExport={() => abrirExport()}
        aoReconsultar={reconsultarAcervo}
        reconsultando={reconsultando}
      />

      {/* Conteúdo da Tela */}
      <main className="app-corpo">
        <Suspense fallback={<Carregando />}>
          {rota === 'fila' ? (
            <TelaFila
              conexao={conexao}
              stats={stats}
              aoIrParaEscanear={() => irPara('escanear')}
              aoRecarregarConexao={recarregarConexao}
              aoAtualizarStats={setStats}
              aoAbrirExport={abrirExport}
              aoAbrirBanco={() => setModalGlobal('banco')}
            />
          ) : (
            <TelaEscanear
              info={info}
              conexao={conexao}
              aoIrParaFila={() => irPara('fila')}
              aoAtualizarLoteQtd={setLoteQtd}
              aoAtualizarFilaStats={carregarStats}
            />
          )}
        </Suspense>
      </main>

      {/* Bottom Navigation Mobile Persistente */}
      <BottomNav
        rotaAtiva={rota}
        aoNavegar={irPara}
        loteQtd={loteQtd}
        filaQtd={stats?.total || 0}
        aoAbrirExport={() => abrirExport()}
        aoAbrirBanco={() => setModalGlobal('banco')}
        conexao={conexao}
      />

      {/* Modais Globais */}
      {modalGlobal === 'banco' && (
        <ModalBanco
          estadoInicial={conexao.bruto}
          aoFechar={() => setModalGlobal(null)}
          aoConectar={() => {
            recarregarConexao()
            carregarStats()
          }}
        />
      )}

      {modalGlobal === 'export' && (
        <ModalExport
          itens={itensParaExportar}
          conectado={conexao.conectado}
          temSelecao={false}
          ocupado={exportando}
          aoFechar={() => setModalGlobal(null)}
          aoConfirmar={executarExport}
        />
      )}
    </div>
  )
}

function Carregando() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60dvh',
        color: 'var(--texto-3)',
        fontSize: 'var(--txt-sm)',
        gap: 12,
      }}
    >
      <div className="animacao-girar" style={{ fontSize: 24 }}>
        ◓
      </div>
      <span>Carregando aplicação…</span>
    </div>
  )
}

function descreverConexao(db) {
  if (!db) {
    return {
      conectado: false,
      tom: undefined,
      rotulo: 'Verificando conexão…',
      detalhe: 'Consultando o estado do PostgreSQL do BibLivre',
      bruto: null,
    }
  }

  const indexados = db.indexados || 0
  if (indexados > 0) {
    return {
      conectado: true,
      tom: 'ok',
      rotulo: `Acervo: ${indexados.toLocaleString('pt-BR')} ISBNs`,
      detalhe: `${db.config?.dbname || 'biblivre4'} em ${db.config?.host || 'localhost'}, schema ${db.config?.schema || 'single'}`,
      bruto: db,
    }
  }

  return {
    conectado: false,
    tom: 'alerta',
    rotulo: db.configurado ? 'Acervo indisponível' : 'Banco desconectado',
    detalhe:
      db.erro ||
      'Sem banco, todo livro escaneado entra como obra nova. Clique para conectar.',
    bruto: db,
  }
}
