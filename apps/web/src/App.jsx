import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { Navbar } from './components'
import { ModalBanco } from './features/fila/ModalBanco'
import { ModalExport } from './features/fila/ModalExport'
import { useDispositivo, useEhPc } from './hooks/useDispositivo'

/*
 * Duas posturas, e elas não têm o mesmo tamanho.
 *
 * A rota `/` resolve para telas diferentes conforme o aparelho, e isso é
 * deliberado: no celular ela é a câmera (de pé na estante, uma mão livre); no
 * PC é o balcão de captura, que gerencia os celulares que estão bipando. Não é
 * a mesma tela reflowada — o PC não tem câmera útil apontando para lombada de
 * livro, e oferecer "abrir a câmera" lá só produzia um caminho que não
 * funciona.
 *
 * O celular tem uma tela só: a câmera. Fila de revisão e conexão com o
 * PostgreSQL são gerência — leitura de metadados, decisão de destino, gravação
 * no acervo, senha de banco —, e gerência se faz sentado. Quem está de pé com
 * o livro na mão bipa e envia; quem revisa o que foi bipado está no PC. Por
 * isso `/fila` no celular não abre tela nenhuma e não há barra de navegação:
 * não existe segundo destino para navegar.
 */
const TelaCelular = lazy(() =>
  import('./features/scanner/TelaCelular').then((m) => ({ default: m.TelaCelular }))
)
const TelaBalcao = lazy(() =>
  import('./features/balcao/TelaBalcao').then((m) => ({ default: m.TelaBalcao }))
)
const TelaFila = lazy(() =>
  import('./features/fila/TelaFila').then((m) => ({ default: m.TelaFila }))
)

function rotaAtual() {
  return window.location.pathname.replace(/\/+$/, '') === '/fila' ? 'fila' : 'captura'
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

  const ehPc = useEhPc()

  // Só o celular tem identidade de aparelho: ele é um dos N que bipam. O PC
  // olha todos, e o que ele digitar à mão cai na bandeja do balcão.
  const dispositivo = useDispositivo({ ativo: !ehPc })

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

  // Um link para /fila chega no celular por caminhos legítimos: o endereço
  // colado do PC, um histórico anterior, o QR aberto duas vezes. Sem tela para
  // servir, a URL é corrigida em vez de ficar um endereço que não resolve em
  // nada.
  useEffect(() => {
    if (ehPc || rota !== 'fila') return
    window.history.replaceState({}, '', '/')
    setRota('captura')
  }, [ehPc, rota])

  const recarregarConexao = useCallback(async () => {
    try {
      setDb(await api.db.estado())
    } catch {
      setDb(null)
    }
  }, [])

  const carregarStats = useCallback(async () => {
    try {
      setStats(await api.fila.stats())
    } catch {
      /* a tela mostra o que já tem; o próximo ciclo reconcilia */
    }
  }, [])

  useEffect(() => {
    api.sistema.info().then(setInfo).catch(() => {})
    recarregarConexao()
    carregarStats()
  }, [recarregarConexao, carregarStats])

  // A pílula do acervo tem de refletir o banco caindo no meio do turno, não só
  // o estado de quando a tela abriu.
  useEffect(() => {
    const t = setInterval(recarregarConexao, 20000)
    return () => clearInterval(t)
  }, [recarregarConexao])

  // A contagem do lote vem da tela de captura enquanto ela está aberta. Na
  // fila, quem alimenta o badge é o painel de lotes.
  useEffect(() => {
    if (rota !== 'fila') return
    const puxar = () =>
      api.lotes
        .painel()
        .then((d) => setLoteQtd(d.titulos))
        .catch(() => {})
    puxar()
    const t = setInterval(puxar, 10000)
    return () => clearInterval(t)
  }, [rota])

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
      setItensParaExportar((lista.itens || []).filter((i) => i.status !== 'exportado'))
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
        if (rota !== 'fila') irPara('fila')
        return r
      } finally {
        setExportando(false)
      }
    },
    [itensParaExportar, carregarStats, recarregarConexao, rota, irPara]
  )

  const conexao = descreverConexao(db)
  const naFila = rota === 'fila' && ehPc

  return (
    <div className="app-shell">
      {/*
        A barra do topo é do PC. No celular ela duplicava o cabeçalho da tela
        — "Escanear" já traz o próprio título e o estado do acervo — e eram
        dois cabeçalhos empilhados comendo 104px da viewport onde o visor
        precisa de 340. Lá também não há para onde navegar: a captura é a
        tela única.
      */}
      {ehPc && (
        <Navbar
          rotaAtiva={rota}
          aoNavegar={irPara}
          loteQtd={loteQtd}
          filaQtd={stats?.a_exportar || 0}
          conexao={conexao}
          aoAbrirBanco={() => setModalGlobal('banco')}
          aoAbrirExport={() => abrirExport()}
        />
      )}

      <main className="app-corpo">
        <Suspense fallback={<Carregando />}>
          {naFila ? (
            <TelaFila
              conexao={conexao}
              stats={stats}
              aoIrParaCaptura={() => irPara('captura')}
              aoAtualizarStats={setStats}
              aoAbrirExport={abrirExport}
              aoReconsultar={reconsultarAcervo}
              reconsultando={reconsultando}
            />
          ) : ehPc ? (
            <TelaBalcao
              info={info}
              conexao={conexao}
              aoIrParaFila={() => irPara('fila')}
              aoAtualizarLoteQtd={setLoteQtd}
              aoAtualizarFilaStats={carregarStats}
            />
          ) : (
            <TelaCelular conexao={conexao} dispositivo={dispositivo} />
          )}
        </Suspense>
      </main>

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
    <div className="carregando">
      <span className="microrrotulo">Carregando</span>
    </div>
  )
}

/**
 * O estado do acervo, em texto de tela.
 *
 * `conectado` vem de `db.conectado` — uma sonda de conexão de verdade no
 * servidor (`biblio.biblivre.conexao.sondar`). Antes era inferido de
 * `db.indexados > 0`, o tamanho do índice de ISBN em memória, e isso dava
 * falso negativo sempre que o índice é montado sob demanda: a pílula ficava
 * âmbar ("Acervo indisponível") com o Postgres perfeitamente conectado. O
 * índice diz se a consulta vai ser rápida, não se o banco existe.
 */
function descreverConexao(db) {
  if (!db) {
    return {
      conectado: false,
      tom: undefined,
      rotulo: 'Verificando…',
      detalhe: 'Consultando o estado do PostgreSQL do BibLivre',
      bruto: null,
    }
  }

  if (db.conectado) {
    const obras = db.obras || 0
    const indexados = db.indexados || 0
    return {
      conectado: true,
      tom: 'ok',
      // O número que interessa é o do acervo. Com o índice quente mostramos os
      // ISBNs indexados (é o que de fato responde ao bipe); sem ele, a
      // contagem de obras, que a sonda traz de graça.
      rotulo: indexados
        ? `Acervo: ${indexados.toLocaleString('pt-BR')} ISBNs`
        : `Acervo: ${obras.toLocaleString('pt-BR')} obras`,
      detalhe: `${db.dbname || 'biblivre5'} em ${db.host || 'localhost'}, schema ${db.schema || 'single'}${indexados ? '' : ' · índice de ISBN sob demanda'}`,
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
