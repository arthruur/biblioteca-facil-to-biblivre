import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import {
  Aviso,
  Botao,
  EstadoVazio,
  FaixaIndicadores,
  IconeBuscar,
  IconeCheck,
  IconeLivro,
  IconePendente,
  IconeRecarregar,
  IconeRemover,
  IconeScanner,
  Moldura,
  Segmentado,
  Selo,
} from '../../components'
import { LinhaItem } from './LinhaItem'
import './fila.css'

const ABAS = [
  ['pendente,revisado', 'A exportar'],
  ['todos', 'Todos'],
  ['pendente', 'Pendentes'],
  ['revisado', 'Revisados'],
  ['exportado', 'Exportados'],
  ['ignorado', 'Ignorados'],
]

const DEBOUNCE_QUANTIDADE = 400

export function TelaFila({
  conexao,
  stats: statsProp,
  aoIrParaCaptura,
  aoAtualizarStats,
  aoAbrirExport,
  aoReconsultar,
  reconsultando = false,
}) {
  const [itens, setItens] = useState([])
  const [stats, setStats] = useState(statsProp || null)
  const [aba, setAba] = useState('pendente,revisado')
  const [busca, setBusca] = useState('')
  const [soAcervo, setSoAcervo] = useState(false)
  const [selecao, setSelecao] = useState(() => new Set())
  const [editando, setEditando] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [resultado, setResultado] = useState(null)

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
      aoAtualizarStats?.(s)
      setErro('')
    } catch (e) {
      setErro(e.message)
    } finally {
      setCarregando(false)
    }
  }, [aba, busca, aoAtualizarStats])

  useEffect(() => {
    carregar()
  }, [carregar])

  useEffect(() => {
    if (statsProp) setStats(statsProp)
  }, [statsProp])

  const visiveis = useMemo(
    () => (soAcervo ? itens.filter((i) => i.acervo?.existe) : itens),
    [itens, soAcervo]
  )

  // Atalhos de teclado
  useEffect(() => {
    const aoTeclar = (e) => {
      const digitando = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)
      if (e.key === '/' && !digitando) {
        e.preventDefault()
        buscaRef.current?.focus()
      } else if (e.key === 'Escape') {
        setEditando(null)
        setSelecao(new Set())
      } else if (e.key === 'a' && (e.ctrlKey || e.metaKey) && !digitando) {
        e.preventDefault()
        setSelecao(new Set(visiveis.map((i) => i.id)))
      }
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [visiveis])

  const selecionados = useMemo(
    () => visiveis.filter((i) => selecao.has(i.id)),
    [visiveis, selecao]
  )

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
          () => {
            api.fila.stats().then((s) => {
              setStats(s)
              aoAtualizarStats?.(s)
            })
          },
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
            ? 'Remover este item da fila? O arquivo dele será excluído.'
            : `Remover ${quantos} itens da fila? Os arquivos deles serão excluídos.`
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

  const dispararExport = () => {
    aoAbrirExport?.(selecionados.length > 0 ? selecionados : null)
  }

  return (
    <div className="fila">
      {/* Cabeçalho da tela */}
      <div className="fila__topo">
        <div className="fila__topo-esq">
          <h1 className="fila__titulo">Fila de revisão</h1>
          <span className="fila__sub">
            {stats
              ? `${stats.total} ${stats.total === 1 ? 'título em espera' : 'títulos em espera'} · em disco, sobrevive a reinício`
              : 'carregando…'}
          </span>
        </div>

        <div className="fila__topo-dir">
          <Botao variante="secundario" tamanho="pequeno" onClick={aoIrParaCaptura}>
            ← Balcão de captura
          </Botao>
          {conexao?.conectado && (
            <Botao
              variante="secundario"
              tamanho="pequeno"
              onClick={aoReconsultar}
              disabled={reconsultando}
              title="Revarrer o acervo e reavaliar o destino de cada item da fila"
            >
              <IconeRecarregar
                tamanho={13}
                className={reconsultando ? 'animacao-girar' : ''}
              />
              {reconsultando ? 'Reconsultando…' : 'Reconsultar acervo'}
            </Botao>
          )}
        </div>
      </div>

      {/* Faixa de indicadores */}
      {stats && (
        <Indicadores
          stats={stats}
          abaAtiva={aba}
          aoTrocarAba={setAba}
          soAcervo={soAcervo}
          aoToggleSoAcervo={() => setSoAcervo((v) => !v)}
        />
      )}

      {/* Filtros e busca */}
      <div className="filtros">
        <div className="filtros__busca-wrap">
          <IconeBuscar tamanho={15} className="filtros__icone" />
          <input
            ref={buscaRef}
            className="filtros__busca"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="buscar por título, autor ou ISBN   ( / )"
            aria-label="Buscar na fila"
          />
          {busca && (
            <button
              className="filtros__limpar"
              onClick={() => setBusca('')}
              title="Limpar busca"
              aria-label="Limpar busca"
            >
              ✕
            </button>
          )}
        </div>

        <Segmentado
          opcoes={ABAS}
          valor={aba}
          aoMudar={setAba}
          rotulo="Filtrar por situação"
        />

        <label className="filtros__caixa">
          <input
            type="checkbox"
            checked={soAcervo}
            onChange={(e) => setSoAcervo(e.target.checked)}
          />
          <span>só já no acervo</span>
        </label>

        <span className="filtros__contagem">
          {visiveis.length === itens.length
            ? `${itens.length} ${itens.length === 1 ? 'item' : 'itens'}`
            : `${visiveis.length} de ${itens.length}`}
        </span>
      </div>

      <div className="fila__conteudo">
        {erro && (
          <Aviso tom="erro" icone="⚠" titulo="Ocorreu um erro">
            {erro}
          </Aviso>
        )}

        {resultado && (
          <ResultadoExport resultado={resultado} aoFechar={() => setResultado(null)} />
        )}

        {carregando ? (
          <EstadoVazio titulo="Carregando a fila…" />
        ) : !itens.length ? (
          <FilaVazia aoIrParaCaptura={aoIrParaCaptura} />
        ) : !visiveis.length ? (
          <EstadoVazio
            icone={<IconeBuscar tamanho={34} />}
            titulo="Nenhum item com esse filtro"
            acao={
              <Botao
                variante="secundario"
                onClick={() => {
                  setBusca('')
                  setSoAcervo(false)
                  setAba('todos')
                }}
              >
                Limpar todos os filtros
              </Botao>
            }
          >
            A fila tem {itens.length}{' '}
            {itens.length === 1 ? 'item' : 'itens'} — só nenhum que atenda à busca e
            ao filtro atuais.
          </EstadoVazio>
        ) : (
          <div className="tabela-wrap">
            <table className="tabela">
              <colgroup>
                <col style={{ width: 40 }} />
                <col style={{ width: 44 }} />
                <col />
                <col style={{ width: 160 }} />
                <col style={{ width: 200 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 108 }} />
              </colgroup>
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
                  <th />
                  <th>Obra</th>
                  <th>ISBN</th>
                  <th>Destino no BibLivre</th>
                  <th>Exemplares</th>
                  <th>Situação</th>
                  <th />
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

      {/* Barra flutuante de seleção */}
      {selecionados.length > 0 && (
        <Moldura className="barra-selecao">
          <span className="barra-selecao__contagem">
            {selecionados.length}{' '}
            {selecionados.length === 1 ? 'selecionado' : 'selecionados'}
          </span>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('revisado')}>
            <IconeCheck tamanho={12} /> Marcar revisado
          </Botao>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('pendente')}>
            <IconePendente tamanho={12} /> Voltar a pendente
          </Botao>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('ignorado')}>
            Ignorar
          </Botao>
          <Botao
            tamanho="pequeno"
            variante="perigo"
            onClick={() => acaoEmLote('remover')}
          >
            <IconeRemover tamanho={12} /> Remover
          </Botao>
          <Botao
            tamanho="pequeno"
            variante="fantasma"
            onClick={() => setSelecao(new Set())}
          >
            limpar seleção
          </Botao>
        </Moldura>
      )}

      {/* Rodapé de resumo e exportação */}
      <footer className="rodape">
        <div className="rodape__resumo">
          <span className="rodape__forte numero">{alvoExport.length}</span>
          <span className="rodape__rotulo">
            {selecionados.length
              ? alvoExport.length === 1
                ? 'item selecionado a exportar'
                : 'itens selecionados a exportar'
              : alvoExport.length === 1
                ? 'item a exportar'
                : 'itens a exportar'}
          </span>
          {alvoExport.length > 0 && (
            <span className="rodape__decomposicao">
              <Selo tom="nova">
                {novasAlvo} {novasAlvo === 1 ? 'obra nova' : 'obras novas'}
              </Selo>
              <Selo tom="existente">{alvoExport.length - novasAlvo} já no acervo</Selo>
              <Selo tom="neutro">
                {exemplaresAlvo} {exemplaresAlvo === 1 ? 'exemplar' : 'exemplares'}
              </Selo>
            </span>
          )}
        </div>

        <div className="rodape__acoes">
          <Botao
            variante="secundario"
            onClick={dispararExport}
            disabled={!alvoExport.length}
          >
            Gerar arquivos
          </Botao>
          <Botao
            variante="primario"
            onClick={dispararExport}
            disabled={!alvoExport.length}
          >
            Exportar →
          </Botao>
        </div>
      </footer>
    </div>
  )
}

/**
 * A faixa de sete números que abre a tela.
 *
 * Cada célula que corresponde a um filtro é um botão: clicar nela é a forma
 * mais curta de chegar ao subconjunto que ela conta. As cores são as do
 * destino no BibLivre — roxo, verde, âmbar — e não decorativas.
 */
function Indicadores({ stats, abaAtiva, aoTrocarAba, soAcervo, aoToggleSoAcervo }) {
  const s = stats
  const atencao = (s.sem_metadados || 0) + (s.isbn_repetido || 0)

  return (
    <FaixaIndicadores
      itens={[
        {
          n: s.a_exportar,
          rotulo: 'A exportar',
          nota: 'pendentes + revisados',
          tom: 'acento',
          ativo: abaAtiva === 'pendente,revisado',
          aoClicar: () => aoTrocarAba('pendente,revisado'),
        },
        {
          n: s.por_status.pendente,
          rotulo: 'Pendentes',
          nota: 'aguardando revisão',
          tom: 'alerta',
          ativo: abaAtiva === 'pendente',
          aoClicar: () => aoTrocarAba('pendente'),
        },
        {
          n: s.por_status.revisado,
          rotulo: 'Revisados',
          nota: 'prontos para gravar',
          tom: 'existente',
          ativo: abaAtiva === 'revisado',
          aoClicar: () => aoTrocarAba('revisado'),
        },
        {
          n: s.obras_novas,
          rotulo: 'Obras novas',
          nota: 'nascem ficha · exigem reindex',
          tom: 'nova',
        },
        {
          n: s.ja_no_acervo,
          rotulo: 'Já no acervo',
          nota: 'só acrescentam exemplares',
          tom: 'existente',
          ativo: soAcervo,
          aoClicar: aoToggleSoAcervo,
        },
        {
          n: atencao,
          rotulo: 'Atenção',
          nota: 'sem título ou ISBN repetido',
          tom: atencao ? 'erro' : undefined,
        },
        {
          n: s.por_status.exportado,
          rotulo: 'Exportados',
          nota: 'já gravados',
          ativo: abaAtiva === 'exportado',
          aoClicar: () => aoTrocarAba('exportado'),
        },
      ]}
    />
  )
}

/** Fila vazia (spec: estado E5). */
function FilaVazia({ aoIrParaCaptura }) {
  return (
    <div className="fila-vazia">
      <Moldura className="fila-vazia__qr">
        <img src="/api/qrcode" alt="QR code para abrir no celular" />
      </Moldura>
      <div>
        <p className="fila-vazia__titulo">Nada na fila</p>
        <p className="fila-vazia__texto">
          Escaneie na estante pelo celular e envie o lote. O que chegar aqui fica em
          disco e sobrevive a reinício do servidor.
        </p>
      </div>
      <Botao variante="primario" onClick={aoIrParaCaptura}>
        <IconeScanner tamanho={15} /> Ir para o scanner
      </Botao>
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
      icone={falhou ? '⚠' : gravou ? <IconeCheck tamanho={16} /> : <IconeLivro tamanho={16} />}
      titulo={
        falhou
          ? 'Arquivos gerados, mas a gravação não concluiu'
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
          Só entraram exemplares adicionais — <strong>não</strong> é necessário
          reindexar.
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
