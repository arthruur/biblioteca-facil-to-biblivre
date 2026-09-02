import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import {
  Aviso,
  Botao,
  EstadoVazio,
  IconeBuscar,
  IconeCheck,
  IconeEditar,
  IconeExportar,
  IconeFila,
  IconeLivro,
  IconePendente,
  IconeRemover,
  IconeScanner,
  Selo,
  Stepper,
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
  aoIrParaEscanear,
  aoRecarregarConexao,
  aoAtualizarStats,
  aoAbrirExport,
  aoAbrirBanco,
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
  })

  const visiveis = useMemo(
    () => (soAcervo ? itens.filter((i) => i.acervo?.existe) : itens),
    [itens, soAcervo]
  )

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
      <div className="fila__conteudo">
        {erro && (
          <div style={{ marginBottom: 'var(--e4)' }}>
            <Aviso tom="erro" icone="⚠" titulo="Ocorreu um erro">
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

        {/* Dashboard de Indicadores do Acervo e Fila */}
        {stats && (
          <DashboardOverview
            stats={stats}
            abaAtiva={aba}
            aoTrocarAba={(novaAba) => setAba(novaAba)}
            soAcervo={soAcervo}
            aoToggleSoAcervo={() => setSoAcervo((v) => !v)}
            conexao={conexao}
            aoAbrirBanco={aoAbrirBanco}
          />
        )}

        {/* Barra de Filtros e Busca */}
        <div className="filtros">
          <div className="filtros__busca-wrap">
            <IconeBuscar tamanho={16} className="filtros__icone-busca" />
            <input
              ref={buscaRef}
              className="filtros__busca"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por título, autor, editora, ISBN ou CDD… ( digite / )"
              aria-label="Buscar na fila"
            />
            {busca && (
              <button
                className="filtros__btn-limpar-busca"
                onClick={() => setBusca('')}
                title="Limpar busca"
              >
                ✕
              </button>
            )}
          </div>

          <div className="filtros__grupo" role="tablist">
            {ABAS.map(([valor, rotulo]) => (
              <button
                key={valor}
                role="tab"
                className={`filtros__aba ${aba === valor ? 'filtros__aba--ativa' : ''}`}
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
            <span>Só já no acervo</span>
          </label>
        </div>

        {/* Tabela Desktop / Cards Mobile */}
        {carregando ? (
          <EstadoVazio icone="⏳" titulo="Carregando a fila de revisão…" />
        ) : !itens.length ? (
          <div className="tabela-wrap">
            <EstadoVazio
              icone={<IconeLivro tamanho={40} />}
              titulo="Nenhum livro na fila"
              acao={
                <Botao variante="primario" onClick={aoIrParaEscanear}>
                  <IconeScanner tamanho={16} /> Ir para o scanner
                </Botao>
              }
            >
              Escaneie os livros no balcão e clique em “Enviar para a Fila”. Tudo o que
              chegar aqui fica salvo com segurança em disco para revisão.
            </EstadoVazio>
          </div>
        ) : !visiveis.length ? (
          <div className="tabela-wrap">
            <EstadoVazio
              icone={<IconeBuscar tamanho={40} />}
              titulo="Nenhum item encontrado com esses filtros"
              acao={
                <Botao
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
              A fila possui {itens.length}{' '}
              {itens.length === 1 ? 'item cadastrado' : 'itens cadastrados'}, mas nenhum
              combina com os critérios da busca atual.
            </EstadoVazio>
          </div>
        ) : (
          <>
            {/* Tabela para Desktop */}
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
                    <th className="col-capa">Capa</th>
                    <th>Obra / Título / Autor</th>
                    <th>ISBN / Fonte</th>
                    <th>Destino no BibLivre</th>
                    <th className="col-ex">Exemplares</th>
                    <th className="col-situacao">Situação</th>
                    <th className="col-acoes">Ações</th>
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

            {/* Cards para Mobile */}
            <div className="fila-cards">
              {visiveis.map((item) => (
                <FilaCardMobile
                  key={item.id}
                  item={item}
                  selecionado={selecao.has(item.id)}
                  aoSelecionar={() => alternarSelecao(item.id)}
                  aoEditar={() => setEditando(item.id)}
                  aoMudarQuantidade={(q) => mudarQuantidade(item.id, q)}
                  aoRemover={() => acaoEmLote('remover', [item.id])}
                  aoAlternarRevisado={() =>
                    acaoEmLote(
                      item.status === 'revisado' ? 'pendente' : 'revisado',
                      [item.id]
                    )
                  }
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Barra Flutuante de Seleção em Lote */}
      {selecionados.length > 0 && (
        <div className="barra-selecao">
          <span className="barra-selecao__contagem">
            {selecionados.length} selecionado{selecionados.length > 1 ? 's' : ''}
          </span>
          <Botao
            tamanho="pequeno"
            variante="primario"
            onClick={() => acaoEmLote('revisado')}
          >
            <IconeCheck tamanho={13} /> Revisado
          </Botao>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('pendente')}>
            <IconePendente tamanho={13} /> Pendente
          </Botao>
          <Botao tamanho="pequeno" onClick={() => acaoEmLote('ignorado')}>
            ⊘ Ignorar
          </Botao>
          <Botao
            tamanho="pequeno"
            variante="perigo"
            onClick={() => acaoEmLote('remover')}
          >
            <IconeRemover tamanho={13} /> Remover
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

      {/* Rodapé Fixo de Resumo e Exportação */}
      <footer className="rodape">
        <div className="rodape__resumo">
          <span className="rodape__forte">
            {alvoExport.length}{' '}
            {selecionados.length ? 'itens selecionados para exportar' : 'itens a exportar'}
          </span>
          {alvoExport.length > 0 && (
            <div className="rodape__badges">
              <span className="rodape__badge rodape__badge--nova">
                {novasAlvo} {novasAlvo === 1 ? 'obra nova' : 'obras novas'}
              </span>
              <span className="rodape__badge rodape__badge--existente">
                {alvoExport.length - novasAlvo} já no acervo
              </span>
              <span className="rodape__badge">
                {exemplaresAlvo} {exemplaresAlvo === 1 ? 'exemplar' : 'exemplares'}
              </span>
            </div>
          )}
        </div>

        <Botao
          variante="primario"
          onClick={dispararExport}
          disabled={!alvoExport.length}
        >
          <IconeExportar tamanho={16} /> Exportar para o BibLivre →
        </Botao>
      </footer>
    </div>
  )
}

function DashboardOverview({
  stats,
  abaAtiva,
  aoTrocarAba,
  soAcervo,
  aoToggleSoAcervo,
  conexao,
  aoAbrirBanco,
}) {
  const s = stats
  const atencao = (s.sem_metadados || 0) + (s.isbn_repetido || 0)

  const cartoes = [
    {
      n: s.a_exportar,
      r: 'A exportar',
      desc: 'Pendentes + Revisados',
      filtro: 'pendente,revisado',
      destaque: true,
    },
    {
      n: s.por_status.pendente,
      r: 'Pendentes',
      desc: 'Aguardando revisão',
      filtro: 'pendente',
      tom: 'alerta',
    },
    {
      n: s.por_status.revisado,
      r: 'Revisados',
      desc: 'Prontos para gravar',
      filtro: 'revisado',
      tom: 'sucesso',
    },
    {
      n: s.obras_novas,
      r: 'Obras novas',
      desc: 'Virarão novos registros',
      tom: 'nova',
    },
    {
      n: s.ja_no_acervo,
      r: 'Já no acervo',
      desc: 'Adicionarão exemplares',
      tom: 'existente',
      cliqueExtra: aoToggleSoAcervo,
      ativoExtra: soAcervo,
    },
    {
      n: atencao,
      r: 'Precisam de atenção',
      desc: 'Sem título ou repetidos',
      tom: atencao ? 'erro' : undefined,
    },
    {
      n: s.por_status.exportado,
      r: 'Exportados',
      desc: 'Já gravados',
      filtro: 'exportado',
      tom: 'neutro',
    },
  ]

  return (
    <div className="dashboard">
      <div className="dashboard__topo">
        <div className="dashboard__titulos">
          <h2 className="dashboard__titulo">Visão Geral da Fila</h2>
          <span className="dashboard__sub">
            Total de {s.total} {s.total === 1 ? 'título catalogado' : 'títulos catalogados'} em espera
          </span>
        </div>

        <div className="dashboard__status-db">
          <span
            className={`dashboard__db-pill ${
              conexao.conectado ? 'dashboard__db-pill--ok' : 'dashboard__db-pill--off'
            }`}
            onClick={aoAbrirBanco}
            title="Configurar PostgreSQL do BibLivre"
          >
            <span className="pilula__ponto" />
            {conexao.conectado ? 'PostgreSQL Conectado' : 'PostgreSQL Desconectado'}
          </span>
        </div>
      </div>

      <div className="dashboard__grid">
        {cartoes.map((c) => {
          const classes = [
            'dashboard__card',
            c.destaque && 'dashboard__card--destaque',
            c.tom && `dashboard__card--${c.tom}`,
            (abaAtiva === c.filtro || c.ativoExtra) && 'dashboard__card--ativo',
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <button
              key={c.r}
              className={classes}
              onClick={() => {
                if (c.filtro) aoTrocarAba(c.filtro)
                else if (c.cliqueExtra) c.cliqueExtra()
              }}
              title={c.desc}
            >
              <span className="dashboard__card-numero mono">{c.n}</span>
              <span className="dashboard__card-rotulo">{c.r}</span>
              <span className="dashboard__card-desc">{c.desc}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function FilaCardMobile({
  item,
  selecionado,
  aoSelecionar,
  aoEditar,
  aoMudarQuantidade,
  aoRemover,
  aoAlternarRevisado,
}) {
  const destinoTom = !item.acervo ? 'alerta' : item.acervo.existe ? 'existente' : 'nova'
  const destinoLabel = !item.acervo
    ? 'não verificado'
    : item.acervo.existe
      ? `+${item.quantidade} ex · #${item.acervo.record_id}`
      : 'obra nova'

  return (
    <div
      className={`fila-card ${selecionado ? 'fila-card--selecionado' : ''} ${
        item.status === 'exportado' ? 'fila-card--exportado' : ''
      }`}
    >
      <div className="fila-card__capa-wrap">
        {item.capa ? (
          <img src={item.capa} alt="" className="fila-card__capa" loading="lazy" />
        ) : (
          <div className="fila-card__capa fila-card__capa--vazia">
            <IconeLivro tamanho={20} />
          </div>
        )}
        <input
          type="checkbox"
          checked={selecionado}
          onChange={aoSelecionar}
          aria-label="Selecionar este item"
          className="fila-card__checkbox"
        />
      </div>

      <div className="fila-card__conteudo">
        <div className="fila-card__topo">
          <Selo tom={destinoTom} style={{ fontSize: 10 }}>
            {destinoLabel}
          </Selo>
          <span className="fila-card__status-tag">{item.status}</span>
        </div>

        <p className={`fila-card__titulo ${!item.titulo ? 'fila-card__titulo--vazio' : ''}`}>
          {item.titulo || '— sem título informado —'}
        </p>

        <p className="fila-card__meta">
          {[item.autor, item.ano, item.editora].filter(Boolean).join(' · ') || '—'}
        </p>

        <p className="fila-card__isbn mono">
          {item.isbn} {item.fonte ? `· ${item.fonte}` : ''}
        </p>

        <div className="fila-card__rodape">
          <div className="fila-card__stepper">
            <Stepper
              valor={item.quantidade}
              aoMudar={(q) => aoMudarQuantidade(q)}
              min={1}
              max={99}
            />
          </div>

          <div className="fila-card__acoes">
            <button
              className="fila-card__acao"
              onClick={aoEditar}
              title="Editar metadados"
              aria-label="Editar"
            >
              <IconeEditar tamanho={14} />
            </button>
            <button
              className="fila-card__acao"
              onClick={aoAlternarRevisado}
              title={item.status === 'revisado' ? 'Voltar para pendente' : 'Marcar como revisado'}
              aria-label="Alternar revisado"
            >
              {item.status === 'revisado' ? <IconePendente tamanho={14} /> : <IconeCheck tamanho={14} />}
            </button>
            <button
              className="fila-card__acao"
              onClick={aoRemover}
              title="Remover da fila"
              aria-label="Remover"
            >
              <IconeRemover tamanho={14} />
            </button>
          </div>
        </div>
      </div>
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
      icone={falhou ? '⚠' : gravou ? <IconeCheck tamanho={18} /> : <IconeLivro tamanho={18} />}
      titulo={
        falhou
          ? 'Arquivos gerados, mas gravação não concluída'
          : gravou
            ? 'Gravado com sucesso no BibLivre'
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
          Só entraram exemplares adicionais — <strong>não</strong> é necessário reindexar.
        </p>
      )}
      <div style={{ marginTop: 'var(--e2)' }}>
        <Botao tamanho="pequeno" variante="fantasma" onClick={aoFechar}>
          Dispensar aviso
        </Botao>
      </div>
    </Aviso>
  )
}
