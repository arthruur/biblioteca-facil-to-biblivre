import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import { Aviso, Botao, EstadoVazio, Pilula } from '../../components'
import { LinhaItem } from './LinhaItem'
import { ModalBanco } from './ModalBanco'
import { ModalExport } from './ModalExport'
import './fila.css'

const ABAS = [
  ['pendente,revisado', 'A exportar'],
  ['todos', 'Todos'],
  ['pendente', 'Pendentes'],
  ['revisado', 'Revisados'],
  ['exportado', 'Exportados'],
  ['ignorado', 'Ignorados'],
]

/** Grava a quantidade só depois que o usuário para de clicar no stepper. */
const DEBOUNCE_QUANTIDADE = 400

export function TelaFila({ conexao, aoIrParaEscanear, aoRecarregarConexao }) {
  const [itens, setItens] = useState([])
  const [stats, setStats] = useState(null)
  const [aba, setAba] = useState('pendente,revisado')
  const [busca, setBusca] = useState('')
  const [soAcervo, setSoAcervo] = useState(false)
  const [selecao, setSelecao] = useState(() => new Set())
  const [editando, setEditando] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [resultado, setResultado] = useState(null)
  const [modal, setModal] = useState(null)
  const [exportando, setExportando] = useState(false)

  const buscaRef = useRef(null)
  const timersQtd = useRef(new Map())

  const carregar = useCallback(async () => {
    try {
      const [lista, s] = await Promise.all([
        api.fila.listar({ status: aba, busca }),
        api.fila.stats(),
      ])
      setItens(lista.itens || [])
      setStats(s)
      setErro('')
    } catch (e) {
      setErro(e.message)
    } finally {
      setCarregando(false)
    }
  }, [aba, busca])

  useEffect(() => {
    carregar()
  }, [carregar])

  // Atalhos: "/" foca a busca, Esc limpa seleção/editor, Ctrl+A seleciona o
  // que está visível (docs/SPEC_UI.md §4).
  useEffect(() => {
    const aoTeclar = (e) => {
      const digitando = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)
      if (e.key === '/' && !digitando) {
        e.preventDefault()
        buscaRef.current?.focus()
      } else if (e.key === 'Escape' && !modal) {
        setEditando(null)
        setSelecao(new Set())
      } else if (e.key === 'a' && (e.ctrlKey || e.metaKey) && !digitando) {
        e.preventDefault()
        setSelecao(new Set(visiveis.map((i) => i.id)))
      }
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  })

  const visiveis = useMemo(
    () => (soAcervo ? itens.filter((i) => i.acervo?.existe) : itens),
    [itens, soAcervo]
  )

  const selecionados = useMemo(
    () => visiveis.filter((i) => selecao.has(i.id)),
    [visiveis, selecao]
  )

  /** O que o export vai levar: a seleção, se houver; senão, o que dá para exportar. */
  const alvoExport = useMemo(() => {
    const base = selecionados.length
      ? selecionados
      : itens.filter((i) => i.status === 'pendente' || i.status === 'revisado')
    return base.filter((i) => i.status !== 'exportado')
  }, [selecionados, itens])

  const exemplaresAlvo = alvoExport.reduce(
    (s, i) => s + (Number(i.quantidade) || 1),
    0
  )
  const novasAlvo = alvoExport.filter((i) => !i.acervo?.existe).length

  const alternarSelecao = (id) =>
    setSelecao((s) => {
      const novo = new Set(s)
      novo.has(id) ? novo.delete(id) : novo.add(id)
      return novo
    })

  const salvarCampos = async (id, campos) => {
    try {
      await api.fila.editar(id, campos)
      await carregar()
    } catch (e) {
      setErro(`Não deu para salvar: ${e.message}`)
    }
  }

  const mudarQuantidade = (id, quantidade) => {
    setItens((atuais) =>
      atuais.map((i) =>
        i.id === id ? { ...i, quantidade, exemplares: quantidade } : i
      )
    )
    clearTimeout(timersQtd.current.get(id))
    timersQtd.current.set(
      id,
      setTimeout(() => {
        api.fila.editar(id, { quantidade }).then(
          () => api.fila.stats().then(setStats),
          (e) => setErro(`Não deu para salvar a quantidade: ${e.message}`)
        )
      }, DEBOUNCE_QUANTIDADE)
    )
  }

  const acaoEmLote = async (acao, ids = [...selecao]) => {
    if (!ids.length) return
    if (acao === 'remover') {
      const quantos = ids.length
      if (
        !window.confirm(
          quantos === 1
            ? 'Remover este item da fila? O arquivo dele é apagado.'
            : `Remover ${quantos} itens da fila? Os arquivos deles são apagados.`
        )
      )
        return
    }
    try {
      await api.fila.acoes(ids, acao)
      setSelecao(new Set())
      await carregar()
    } catch (e) {
      setErro(e.message)
    }
  }

  const exportar = async ({ executar, senha }) => {
    setExportando(true)
    setErro('')
    try {
      const r = await api.fila.exportar({
        executar,
        ids: selecionados.length ? selecionados.map((i) => i.id) : null,
        db: senha ? { senha } : null,
      })
      setResultado(r)
      setModal(null)
      setSelecao(new Set())
      await carregar()
      if (executar) aoRecarregarConexao?.()
    } catch (e) {
      setErro(`Export falhou: ${e.message}`)
    } finally {
      setExportando(false)
    }
  }

  return (
    <div className="fila">
      <header className="fila__topo">
        <div className="fila__marca">
          <span className="fila__titulo">Fila de revisão</span>
          <span className="fila__sub">
            {stats ? `${stats.total} na fila` : '…'}
          </span>
        </div>
        <div className="fila__acoes-topo">
          <Botao variante="fantasma" tamanho="pequeno" onClick={aoIrParaEscanear}>
            ← Escanear
          </Botao>
          <Pilula
            tom={conexao.tom}
            onClick={() => setModal('banco')}
            title="Configurar a conexão com o BibLivre"
          >
            {conexao.rotulo}
          </Pilula>
          {conexao.conectado && (
            <Botao
              variante="fantasma"
              className="btn--icone"
              title="Revarrer o acervo e reavaliar a fila"
              aria-label="Revarrer o acervo"
              onClick={async () => {
                await api.fila.reconsultar()
                await carregar()
                aoRecarregarConexao?.()
              }}
            >
              ↻
            </Botao>
          )}
        </div>
      </header>

      <div className="fila__conteudo">
        {erro && (
          <div style={{ marginBottom: 'var(--e4)' }}>
            <Aviso tom="erro" icone="⚠" titulo="Algo deu errado">
              {erro}
            </Aviso>
          </div>
        )}

        {resultado && (
          <div style={{ marginBottom: 'var(--e4)' }}>
            <ResultadoExport
              resultado={resultado}
              aoFechar={() => setResultado(null)}
            />
          </div>
        )}

        {stats && <Indicadores stats={stats} aba={aba} aoTrocarAba={setAba} />}

        <div className="filtros">
          <input
            ref={buscaRef}
            className="filtros__busca"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por título, autor, editora, ISBN ou CDD    ( / )"
            aria-label="Buscar na fila"
          />
          <div className="filtros__grupo" role="tablist">
            {ABAS.map(([valor, rotulo]) => (
              <button
                key={valor}
                role="tab"
                className="filtros__aba"
                aria-selected={aba === valor}
                onClick={() => setAba(valor)}
              >
                {rotulo}
              </button>
            ))}
          </div>
          <label className="filtros__caixa">
            <input
              type="checkbox"
              checked={soAcervo}
              onChange={(e) => setSoAcervo(e.target.checked)}
            />
            só já no acervo
          </label>
        </div>

        {carregando ? (
          <EstadoVazio icone="⏳" titulo="Carregando a fila…" />
        ) : !itens.length ? (
          <div className="tabela-wrap">
            <EstadoVazio
              icone="📥"
              titulo="Nada na fila"
              acao={
                <Botao variante="primario" onClick={aoIrParaEscanear}>
                  Ir para o scanner
                </Botao>
              }
            >
              Escaneie os livros no celular e toque em “Enviar para a fila”. O
              que chegar aqui espera revisão e sobrevive a reinício do servidor.
            </EstadoVazio>
          </div>
        ) : !visiveis.length ? (
          <div className="tabela-wrap">
            <EstadoVazio
              icone="🔍"
              titulo="Nenhum item com esse filtro"
              acao={
                <Botao
                  onClick={() => {
                    setBusca('')
                    setSoAcervo(false)
                    setAba('todos')
                  }}
                >
                  Limpar filtros
                </Botao>
              }
            >
              A fila tem {itens.length}{' '}
              {itens.length === 1 ? 'item' : 'itens'}, mas nenhum casa com a
              busca e os filtros atuais.
            </EstadoVazio>
          </div>
        ) : (
          <div className="tabela-wrap">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="col-check">
                    <input
                      type="checkbox"
                      checked={
                        visiveis.length > 0 &&
                        selecionados.length === visiveis.length
                      }
                      onChange={(e) =>
                        setSelecao(
                          e.target.checked
                            ? new Set(visiveis.map((i) => i.id))
                            : new Set()
                        )
                      }
                      aria-label="Selecionar todos os visíveis"
                    />
                  </th>
                  <th className="col-capa" />
                  <th>Obra</th>
                  <th>ISBN</th>
                  <th>Destino no BibLivre</th>
                  <th className="col-ex">Exemplares</th>
                  <th className="col-situacao">Situação</th>
                  <th className="col-acoes" />
                </tr>
              </thead>
              <tbody>
                {visiveis.map((item) => (
                  <LinhaItem
                    key={item.id}
                    item={item}
                    conectado={conexao.conectado}
                    selecionado={selecao.has(item.id)}
                    editando={editando === item.id}
                    aoSelecionar={alternarSelecao}
                    aoEditar={setEditando}
                    aoSalvar={salvarCampos}
                    aoMudarQuantidade={mudarQuantidade}
                    aoAlternarRevisado={(i) =>
                      acaoEmLote(
                        i.status === 'revisado' ? 'pendente' : 'revisado',
                        [i.id]
                      )
                    }
                    aoRemover={(i) => acaoEmLote('remover', [i.id])}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selecionados.length > 0 && (
        <div className="barra-selecao">
          <span className="barra-selecao__contagem">
            {selecionados.length} selecionado
            {selecionados.length > 1 ? 's' : ''}
          </span>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('revisado')}>
            ✓ Revisado
          </Botao>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('pendente')}>
            ↺ Pendente
          </Botao>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('ignorado')}>
            ⊘ Ignorar
          </Botao>
          <Botao
            tamanho="pequeno"
            variante="perigo"
            onClick={() => acaoEmLote('remover')}
          >
            🗑 Remover
          </Botao>
          <Botao
            tamanho="pequeno"
            variante="fantasma"
            onClick={() => setSelecao(new Set())}
          >
            Limpar
          </Botao>
        </div>
      )}

      <footer className="rodape">
        <div className="rodape__resumo">
          <span className="rodape__forte">
            {alvoExport.length}{' '}
            {selecionados.length ? 'itens (seleção)' : 'itens a exportar'}
          </span>
          {alvoExport.length > 0 && (
            <>
              <span>→</span>
              <span style={{ color: 'var(--nova)' }}>
                {novasAlvo} {novasAlvo === 1 ? 'obra nova' : 'obras novas'}
              </span>
              <span>·</span>
              <span style={{ color: 'var(--existente)' }}>
                {alvoExport.length - novasAlvo} já no acervo
              </span>
              <span>·</span>
              <span>{exemplaresAlvo} exemplares</span>
            </>
          )}
        </div>
        <Botao
          variante="primario"
          onClick={() => setModal('export')}
          disabled={!alvoExport.length}
        >
          Exportar →
        </Botao>
      </footer>

      {modal === 'banco' && (
        <ModalBanco
          estadoInicial={conexao.bruto}
          aoFechar={() => setModal(null)}
          aoConectar={() => {
            aoRecarregarConexao?.()
            carregar()
          }}
        />
      )}

      {modal === 'export' && (
        <ModalExport
          itens={alvoExport}
          conectado={conexao.conectado}
          temSelecao={selecionados.length > 0}
          ocupado={exportando}
          aoFechar={() => setModal(null)}
          aoConfirmar={exportar}
        />
      )}
    </div>
  )
}

function Indicadores({ stats, aba, aoTrocarAba }) {
  const s = stats
  const atencao = (s.sem_metadados || 0) + (s.isbn_repetido || 0)

  const cartoes = [
    { n: s.a_exportar, r: 'A exportar', filtro: 'pendente,revisado' },
    { n: s.por_status.pendente, r: 'Pendentes', filtro: 'pendente' },
    { n: s.por_status.revisado, r: 'Revisados', filtro: 'revisado' },
    { n: s.obras_novas, r: 'Obras novas', tom: 'nova' },
    { n: s.ja_no_acervo, r: 'Já no acervo', tom: 'existente' },
    { n: atencao, r: 'Precisam de atenção', tom: atencao ? 'alerta' : undefined },
    { n: s.por_status.exportado, r: 'Exportados', filtro: 'exportado' },
  ]

  return (
    <div className="indicadores">
      {cartoes.map((c) => {
        const classe = `indicador${c.tom ? ` indicador--${c.tom}` : ''}`
        if (!c.filtro) {
          return (
            <div key={c.r} className={classe}>
              <p className="indicador__numero">{c.n}</p>
              <p className="indicador__rotulo">{c.r}</p>
            </div>
          )
        }
        return (
          <button
            key={c.r}
            className={classe}
            aria-pressed={aba === c.filtro}
            onClick={() => aoTrocarAba(c.filtro)}
          >
            <p className="indicador__numero">{c.n}</p>
            <p className="indicador__rotulo">{c.r}</p>
          </button>
        )
      })}
    </div>
  )
}

function ResultadoExport({ resultado, aoFechar }) {
  const r = resultado
  const falhou = r.status === 'gerado_sem_inserir' || r.status === 'senha_requerida'
  const gravou = r.status === 'ok' && r.inseridos !== undefined

  return (
    <Aviso
      tom={falhou ? 'alerta' : gravou ? 'existente' : undefined}
      icone={falhou ? '⚠' : gravou ? '✓' : '📄'}
      titulo={
        falhou
          ? 'Arquivos gerados, mas nada foi gravado'
          : gravou
            ? 'Gravado no BibLivre'
            : 'Arquivos gerados'
      }
    >
      <p>{r.mensagem}</p>
      {r.erro_insercao && <p style={{ marginTop: 4 }}>{r.erro_insercao}</p>}
      {(r.mrc || r.csv) && (
        <p className="mono" style={{ fontSize: 'var(--txt-xs)', marginTop: 6 }}>
          {r.mrc}
          {r.csv && (
            <>
              <br />
              {r.csv}
            </>
          )}
        </p>
      )}
      {r.reindex_necessario === false && (
        <p style={{ marginTop: 6 }}>
          Só entraram exemplares — <strong>não</strong> é preciso reindexar.
        </p>
      )}
      <div style={{ marginTop: 'var(--e2)' }}>
        <Botao tamanho="pequeno" variante="fantasma" onClick={aoFechar}>
          Dispensar
        </Botao>
      </div>
    </Aviso>
  )
}
