import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import {
  Botao,
  Cantos,
  IconeCopiar,
  IconeEditar,
  IconeRemover,
  Moldura,
  Selo,
  Stepper,
} from '../../components'
import { normalizarIsbnDigitado } from '../scanner/isbn'
import './balcao.css'

/**
 * Balcão de captura: a tela do PC na fase de captura.
 *
 * O PC não bipa. Quem bipa está de pé na estante com um celular, e podem ser
 * vários ao mesmo tempo — cada um com a sua bandeja (ver
 * packages/catalogacao/.../lotes.py). Esta tela é o posto de controle desses
 * aparelhos: mostra quem está pareado, o que cada um acabou de ler, e manda
 * uma bandeja (ou todas) para a fila de revisão.
 *
 * Por isso aqui não existe visor nem "abrir a câmera": num PC de balcão a
 * webcam aponta para o rosto do bibliotecário, não para a lombada do livro, e
 * oferecer o botão só produzia um caminho que não funciona. O que o PC ganha em
 * troca é o campo de ISBN à mão — o livro que chegou sem código de barras, com
 * o bibliotecário já sentado.
 *
 * ATUALIZAÇÃO
 * -----------
 * O painel busca `/api/lotes` a cada `INTERVALO`. A resposta traz `versao`, que
 * sobe a cada mutação em qualquer bandeja; quando ela não muda, o estado não é
 * substituído e o React não re-renderiza. É polling de propósito: ver o
 * docstring de `lotes.py` sobre por que contador e não SSE.
 */
const INTERVALO = 2000

export function TelaBalcao({ info, conexao, aoIrParaFila, aoAtualizarLoteQtd, aoAtualizarFilaStats }) {
  const [painel, setPainel] = useState(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState('')
  const [manual, setManual] = useState('')
  const [copiado, setCopiado] = useState(false)
  const [recado, setRecado] = useState('')
  const versaoRef = useRef(-1)

  const buscar = useCallback(async (signal) => {
    try {
      const d = await api.lotes.painel(signal)
      setErro('')
      if (d.versao === versaoRef.current) return
      versaoRef.current = d.versao
      setPainel(d)
      aoAtualizarLoteQtd?.(d.titulos)
    } catch (e) {
      if (e.name === 'AbortError') return
      setErro(e.message)
    }
  }, [aoAtualizarLoteQtd])

  useEffect(() => {
    const ctrl = new AbortController()
    buscar(ctrl.signal)
    const t = setInterval(() => buscar(ctrl.signal), INTERVALO)
    return () => {
      ctrl.abort()
      clearInterval(t)
    }
  }, [buscar])

  /** Roda a ação, força uma releitura e devolve o painel atualizado. */
  const agir = async (chave, acao) => {
    setOcupado(chave)
    try {
      const r = await acao()
      versaoRef.current = -1
      await buscar()
      return r
    } catch (e) {
      setErro(e.message)
      return null
    } finally {
      setOcupado('')
    }
  }

  const enviarAparelho = async (aparelho) => {
    const r = await agir(`enviar:${aparelho.id}`, () =>
      api.lotes.enviar(aparelho.id)
    )
    if (r?.enviados) {
      setRecado(
        `${r.enviados} ${r.enviados === 1 ? 'título' : 'títulos'} de ${aparelho.nome} ${r.enviados === 1 ? 'foi' : 'foram'} para a fila`
      )
      setTimeout(() => setRecado(''), 5000)
      aoAtualizarFilaStats?.()
    }
  }

  const enviarTudo = async () => {
    const r = await agir('enviar-tudo', () => api.lotes.enviarTudo())
    if (r?.enviados) {
      setRecado(
        `${r.enviados} ${r.enviados === 1 ? 'título' : 'títulos'} ${r.enviados === 1 ? 'foi' : 'foram'} para a fila de revisão`
      )
      setTimeout(() => setRecado(''), 5000)
      aoAtualizarFilaStats?.()
    }
  }

  const adicionarManual = async () => {
    const isbn = normalizarIsbnDigitado(manual)
    if (!isbn) {
      setErro('ISBN inválido — são 10 ou 13 dígitos, e o último é de verificação.')
      return
    }
    setManual('')
    setErro('')
    await agir('manual', () => api.lote.adicionar(isbn))
  }

  const copiarUrl = () => {
    if (!info?.server_url) return
    navigator.clipboard?.writeText(info.server_url)
    setCopiado(true)
    setTimeout(() => setCopiado(false), 2000)
  }

  const aparelhos = painel?.dispositivos || []
  const comItens = aparelhos.filter((a) => a.titulos > 0)
  const total = painel?.titulos || 0

  return (
    <div className="balcao">
      <header className="balcao__topo">
        <div className="balcao__topo-esq">
          <h1 className="balcao__titulo">Balcão de captura</h1>
          <span className="balcao__sub">
            {aparelhos.length === 0
              ? 'nenhum aparelho pareado'
              : `${aparelhos.length} ${aparelhos.length === 1 ? 'aparelho' : 'aparelhos'} · ${total} ${total === 1 ? 'título' : 'títulos'} no total`}
          </span>
        </div>
        <Botao variante="secundario" tamanho="pequeno" onClick={aoIrParaFila}>
          Fila de revisão →
        </Botao>
      </header>

      <div className="balcao__corpo">
        {/* Coluna dos aparelhos */}
        <main className="balcao__aparelhos">
          {erro && <p className="balcao__erro">{erro}</p>}
          {recado && <p className="balcao__recado">{recado}</p>}

          {!painel ? (
            <p className="microrrotulo">Carregando…</p>
          ) : aparelhos.length === 0 ? (
            <SemAparelho info={info} />
          ) : (
            aparelhos.map((aparelho) => (
              <Aparelho
                key={aparelho.id}
                aparelho={aparelho}
                conectado={conexao?.conectado}
                ocupado={ocupado}
                aoEnviar={() => enviarAparelho(aparelho)}
                aoLimpar={() =>
                  agir(`limpar:${aparelho.id}`, () => api.lotes.limpar(aparelho.id))
                }
                aoEsquecer={() =>
                  agir(`esquecer:${aparelho.id}`, () =>
                    api.lotes.esquecer(aparelho.id)
                  )
                }
                aoRenomear={(nome) =>
                  agir(`nome:${aparelho.id}`, () =>
                    api.lotes.renomear(aparelho.id, nome)
                  )
                }
                aoMudarQtd={(isbn, q) =>
                  agir(`qtd:${isbn}`, () => api.lote.quantidade(isbn, q))
                }
                aoRemoverItem={(isbn) =>
                  agir(`item:${isbn}`, () => api.lote.remover(isbn))
                }
              />
            ))
          )}
        </main>

        {/* Coluna do pareamento */}
        <aside className="balcao__lateral">
          {info?.server_url && (
            <Moldura className="parear">
              <span className="microrrotulo">Parear um celular</span>
              <p className="parear__desc">
                Aponte a câmera do celular para o QR. Cada aparelho que abrir
                este endereço ganha a própria bandeja e aparece aqui.
              </p>
              <div className="parear__qr">
                <img src="/api/qrcode" alt="QR code para abrir no celular" />
              </div>
              <div className="parear__url-linha">
                <code className="parear__url mono">{info.server_url}</code>
                <button className="parear__copiar" onClick={copiarUrl} title="Copiar">
                  <IconeCopiar tamanho={13} />
                  {copiado ? 'Copiado' : 'Copiar'}
                </button>
              </div>
            </Moldura>
          )}

          <Moldura className="parear">
            <span className="microrrotulo">Digitar aqui no PC</span>
            <p className="parear__desc">
              Livro sem código de barras, ou código riscado. Entra na bandeja do
              balcão — a deste PC.
            </p>
            <div className="parear__manual">
              <input
                className="parear__campo mono"
                value={manual}
                onChange={(e) => setManual(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && adicionarManual()}
                placeholder="978…"
                inputMode="numeric"
                aria-label="ISBN manual"
              />
              <Botao
                variante="secundario"
                onClick={adicionarManual}
                disabled={!manual.trim() || ocupado === 'manual'}
              >
                {ocupado === 'manual' ? '…' : 'Buscar'}
              </Botao>
            </div>
          </Moldura>

          {!conexao?.conectado && (
            <div className="balcao__aviso-banco">
              <p className="balcao__aviso-titulo">Banco desconectado</p>
              <p>
                Nenhum ISBN que chegar agora é confrontado com o acervo. Na
                gravação todos entram como obra nova — inclusive os que a
                biblioteca já tem.
              </p>
            </div>
          )}
        </aside>
      </div>

      <footer className="balcao__rodape">
        <div className="balcao__rodape-resumo">
          <span className="balcao__rodape-numero numero">{total}</span>
          <span className="balcao__rodape-rotulo">
            {total === 1 ? 'título nas bandejas' : 'títulos nas bandejas'}
            {comItens.length > 1 && ` · ${comItens.length} aparelhos`}
          </span>
        </div>
        <button
          className="btn btn--primario moldura balcao__enviar"
          onClick={enviarTudo}
          disabled={!total || ocupado === 'enviar-tudo'}
        >
          <Cantos />
          {ocupado === 'enviar-tudo'
            ? 'Enviando…'
            : `Enviar tudo (${total}) para a fila →`}
        </button>
      </footer>
    </div>
  )
}

/** Um aparelho e a bandeja dele. */
function Aparelho({
  aparelho,
  conectado,
  ocupado,
  aoEnviar,
  aoLimpar,
  aoEsquecer,
  aoRenomear,
  aoMudarQtd,
  aoRemoverItem,
}) {
  const [editandoNome, setEditandoNome] = useState(false)
  const [rascunho, setRascunho] = useState(aparelho.nome)

  const parado = idadeSegundos(aparelho.ultimo_bipe_em || aparelho.visto_em) > 120
  const vazio = aparelho.titulos === 0

  return (
    <Moldura className={`aparelho ${parado ? 'aparelho--parado' : ''}`}>
      <div className="aparelho__cabecalho">
        <span
          className={`aparelho__ponto ${parado ? 'aparelho__ponto--parado' : ''}`}
          aria-hidden="true"
        />

        {editandoNome ? (
          <div className="aparelho__nome-edicao">
            <input
              className="aparelho__nome-campo"
              value={rascunho}
              onChange={(e) => setRascunho(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  aoRenomear(rascunho)
                  setEditandoNome(false)
                }
                if (e.key === 'Escape') setEditandoNome(false)
              }}
              placeholder="Celular da Ana"
              autoFocus
              aria-label="Nome do aparelho"
            />
            <Botao
              variante="secundario"
              tamanho="pequeno"
              onClick={() => {
                aoRenomear(rascunho)
                setEditandoNome(false)
              }}
            >
              Salvar
            </Botao>
          </div>
        ) : (
          <button
            className="aparelho__nome"
            onClick={() => {
              setRascunho(aparelho.nomeado ? aparelho.nome : '')
              setEditandoNome(true)
            }}
            title="Renomear este aparelho"
          >
            {aparelho.nome}
            <IconeEditar tamanho={12} />
          </button>
        )}

        <span className="aparelho__contagem">
          {aparelho.titulos} {aparelho.titulos === 1 ? 'tít' : 'tít'} ·{' '}
          {aparelho.exemplares} ex
        </span>

        <span className="aparelho__quando">
          {aparelho.ultimo_bipe_em
            ? `último bipe ${desde(aparelho.ultimo_bipe_em)}`
            : `pareado ${desde(aparelho.visto_em)}, sem bipar`}
        </span>

        <div className="aparelho__acoes">
          {!vazio && (
            <Botao
              variante="fantasma"
              tamanho="pequeno"
              onClick={aoLimpar}
              disabled={!!ocupado}
              title="Descartar a bandeja deste aparelho sem enviar"
            >
              Limpar
            </Botao>
          )}
          {vazio && (
            <Botao
              variante="fantasma"
              tamanho="pequeno"
              onClick={aoEsquecer}
              disabled={!!ocupado}
              title="Tirar este aparelho do painel"
            >
              Tirar do painel
            </Botao>
          )}
          <Botao
            variante="primario"
            tamanho="pequeno"
            onClick={aoEnviar}
            disabled={vazio || ocupado === `enviar:${aparelho.id}`}
          >
            {ocupado === `enviar:${aparelho.id}`
              ? 'Enviando…'
              : `Enviar ${aparelho.titulos} →`}
          </Botao>
        </div>
      </div>

      {vazio ? (
        <p className="aparelho__vazio">
          Bandeja vazia. O que este aparelho bipar aparece aqui na hora.
        </p>
      ) : (
        <div className="aparelho__trilha">
          {aparelho.itens.map((item) => (
            <CardBalcao
              key={item.isbn}
              item={item}
              conectado={conectado}
              aoMudarQtd={(q) => aoMudarQtd(item.isbn, q)}
              aoRemover={() => aoRemoverItem(item.isbn)}
            />
          ))}
        </div>
      )}
    </Moldura>
  )
}

function CardBalcao({ item, conectado, aoMudarQtd, aoRemover }) {
  const qtd = Number(item.quantidade) || 1
  const noAcervo = item.acervo?.existe
  const tom = noAcervo ? 'existente' : conectado ? 'nova' : 'alerta'

  return (
    <div className={`bcard bcard--${tom}`}>
      <div className="bcard__topo">
        <span className="bcard__isbn mono">{item.isbn}</span>
        <button
          className="bcard__remover"
          onClick={aoRemover}
          title="Tirar da bandeja"
          aria-label="Tirar da bandeja"
        >
          <IconeRemover tamanho={12} />
        </button>
      </div>

      <p className={`bcard__titulo ${!item.titulo ? 'bcard__titulo--vazio' : ''}`}>
        {item.titulo || 'sem título'}
      </p>
      <p className="bcard__autor">{item.autor || 'autor não informado'}</p>

      <Selo tom={tom} className="bcard__selo">
        {noAcervo
          ? `já no acervo · #${item.acervo.record_id}`
          : conectado
            ? 'obra nova'
            : 'não verificado'}
      </Selo>

      <div className="bcard__rodape">
        <span className="microrrotulo bcard__fonte">{item.fonte || '—'}</span>
        <Stepper valor={qtd} aoMudar={aoMudarQtd} min={1} max={99} />
      </div>
    </div>
  )
}

function SemAparelho({ info }) {
  return (
    <div className="sem-aparelho">
      <p className="sem-aparelho__titulo">Nenhum aparelho pareado</p>
      <p className="sem-aparelho__texto">
        Escaneie o QR ao lado com a câmera de um celular. Vários aparelhos podem
        bipar ao mesmo tempo — cada um ganha a própria bandeja aqui, e você
        decide qual manda para a fila.
      </p>
      {info?.server_url && (
        <code className="sem-aparelho__url mono">{info.server_url}</code>
      )}
    </div>
  )
}

function idadeSegundos(marca) {
  if (!marca) return Infinity
  const t = Date.parse(marca)
  if (Number.isNaN(t)) return Infinity
  return (Date.now() - t) / 1000
}

/** "há 4s", "há 3min", "há 2h" — o suficiente para saber se ainda está vivo. */
function desde(marca) {
  const s = idadeSegundos(marca)
  if (!Number.isFinite(s)) return 'agora'
  if (s < 10) return 'agora'
  if (s < 60) return `há ${Math.round(s)}s`
  if (s < 3600) return `há ${Math.round(s / 60)}min`
  return `há ${Math.round(s / 3600)}h`
}
