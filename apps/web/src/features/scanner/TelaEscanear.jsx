import { useEffect, useRef, useState } from 'react'
import {
  Aviso,
  Botao,
  IconeBuscar,
  IconeCheck,
  IconeCopiar,
  IconeFoto,
  IconeLanterna,
  IconeLivro,
  IconeRemover,
  IconeScanner,
  Selo,
  Stepper,
} from '../../components'
import { ModalFicha } from './ModalFicha'
import { normalizarIsbnDigitado } from './isbn'
import { useLote } from './useLote'
import { useScanner } from './useScanner'
import './scanner.css'

export function TelaEscanear({
  info,
  conexao,
  aoIrParaFila,
  aoAtualizarLoteQtd,
  aoAtualizarFilaStats,
}) {
  const [recado, setRecado] = useState('')
  const [tomRecado, setTomRecado] = useState('')
  const [abertoIsbn, setAbertoIsbn] = useState(null)
  const [manual, setManual] = useState('')
  const [gavetaExpandida, setGavetaExpandida] = useState(false)
  const [copiadoUrl, setCopiadoUrl] = useState(false)
  const arquivoRef = useRef(null)
  const trilhaRef = useRef(null)

  const avisar = (texto, tom = '') => {
    setRecado(texto)
    setTomRecado(tom)
  }

  const lote = useLote({ aoAvisar: avisar })
  const scanner = useScanner({
    aoLer: async (isbn) => {
      const r = await lote.adicionar(isbn)
      if (!r) return
      scanner.anunciar(
        r.jaTinha ? `+1 exemplar · ${isbn}` : `Adicionado ao lote · ${isbn}`,
        'ok'
      )
    },
  })

  // Sincroniza a contagem do lote com o App Shell
  useEffect(() => {
    aoAtualizarLoteQtd?.(lote.itens.length)
  }, [lote.itens.length, aoAtualizarLoteQtd])

  useEffect(() => {
    const t = trilhaRef.current
    if (t) t.scrollLeft = t.scrollWidth
  }, [lote.itens.length])

  const aberto = lote.itens.find((i) => i.isbn === abertoIsbn)

  const enviar = async () => {
    try {
      const d = await lote.enviar()
      if (d) {
        avisar(
          `${d.enviados} ${d.enviados === 1 ? 'título enviado' : 'títulos enviados'} para a fila de revisão`,
          'ok'
        )
        aoAtualizarFilaStats?.()
      }
    } catch (e) {
      avisar(`Não deu para enviar: ${e.message}`, 'erro')
    }
  }

  const adicionarManual = () => {
    const isbn = normalizarIsbnDigitado(manual)
    if (!isbn) {
      avisar(
        'ISBN inválido — confira os dígitos. São 10 ou 13, e o último é de verificação.',
        'erro'
      )
      return
    }
    setManual('')
    lote.adicionar(isbn)
    avisar(`Adicionado ${isbn}`, 'ok')
  }

  const copiarUrlServidor = () => {
    if (!info?.server_url) return
    navigator.clipboard?.writeText(info.server_url)
    setCopiadoUrl(true)
    setTimeout(() => setCopiadoUrl(false), 2000)
  }

  const total = lote.totalExemplares
  const temLote = lote.itens.length > 0

  return (
    <div className="escanear">
      {/* Barra superior de status do scanner */}
      <div className="escanear__subtopo">
        <div className="escanear__subtopo-esq">
          <span className="escanear__badge-modo">
            <IconeScanner tamanho={14} /> Balcão de Captura
          </span>
          <span className="escanear__contagem-lote">
            {temLote
              ? `${lote.itens.length} títulos (${total} ex) no lote`
              : 'Lote vazio — aponte para o código'}
          </span>
        </div>

        <div className="escanear__subtopo-dir">
          <Botao
            variante={scanner.escaneando ? 'secundario' : 'primario'}
            tamanho="pequeno"
            onClick={scanner.escaneando ? scanner.parar : scanner.iniciar}
          >
            {scanner.escaneando ? '✕ Fechar câmera' : '📷 Iniciar câmera'}
          </Botao>
          <Botao
            variante="fantasma"
            tamanho="pequeno"
            onClick={() => arquivoRef.current?.click()}
            title="Carregar foto da contracapa"
          >
            <IconeFoto tamanho={15} /> Foto
          </Botao>
        </div>
      </div>

      <div className="escanear__corpo">
        {/* Painel Central / Visor */}
        <div className="escanear__centro">
          <Visor scanner={scanner} onExpandir={() => setGavetaExpandida((v) => !v)} />

          {/* Barra de entrada manual e foto */}
          <div className="escanear__entrada-bar">
            <div className="escanear__manual-wrap">
              <input
                className="escanear__input-isbn"
                value={manual}
                onChange={(e) => setManual(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && adicionarManual()}
                placeholder="Digitar ISBN manualmente (10 ou 13 dígitos)…"
                inputMode="numeric"
                aria-label="ISBN manual"
              />
              <Botao
                variante="secundario"
                onClick={adicionarManual}
                disabled={!manual.trim()}
              >
                + Adicionar
              </Botao>
            </div>

            <input
              ref={arquivoRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) scanner.lerArquivo(f)
                e.target.value = ''
              }}
            />
          </div>

          {recado && (
            <div className="escanear__recado-wrap">
              <Aviso
                tom={tomRecado === 'ok' ? 'existente' : tomRecado === 'erro' ? 'erro' : undefined}
                icone={tomRecado === 'ok' ? <IconeCheck tamanho={16} /> : undefined}
              >
                {recado}
              </Aviso>
            </div>
          )}
        </div>

        {/* Lateral Desktop: QR Code e Acervo */}
        <aside className="escanear__lateral">
          {info?.server_url && (
            <div className="qr-card">
              <p className="qr-card__titulo">📱 Abrir no Celular</p>
              <p className="qr-card__desc">
                Escaneie com a câmera do smartphone para usar o leitor móvel na estante.
              </p>
              <div className="qr-card__caixa">
                <img src="/api/qrcode" alt="QR code para abrir no celular" />
              </div>
              <div className="qr-card__url-wrap">
                <code className="qr-card__url">{info.server_url}</code>
                <button
                  className="qr-card__btn-copiar"
                  onClick={copiarUrlServidor}
                  title="Copiar endereço"
                >
                  <IconeCopiar tamanho={14} />
                  {copiadoUrl ? 'Copiado!' : 'Copiar'}
                </button>
              </div>
            </div>
          )}

          <div className="info-card">
            <h4 className="info-card__titulo">Fluxo da Catalogação</h4>
            <ol className="info-card__passos">
              <li>
                <strong>1. Bipar</strong>: Aponte a câmera para o código de barras ou digite o ISBN.
              </li>
              <li>
                <strong>2. Lote</strong>: Os livros são acumulados instantaneamente nesta tela.
              </li>
              <li>
                <strong>3. Enviar</strong>: Clique em <em>Enviar para a Fila</em> para consolidar.
              </li>
              <li>
                <strong>4. Revisar & Exportar</strong>: Confira os metadados na Fila e grave no BibLivre.
              </li>
            </ol>
          </div>
        </aside>
      </div>

      {/* Gaveta do Lote (Bottom Sheet no Mobile / Faixa no Desktop) */}
      <section className={`gaveta ${gavetaExpandida ? 'gaveta--expandida' : ''}`}>
        <div className="gaveta__cabecalho">
          <div className="gaveta__info">
            <span className="gaveta__titulo">
              Itens no Lote Atual
              <span className="badge-lote">{lote.itens.length}</span>
            </span>
            <span className="gaveta__subtotal">
              {total} {total === 1 ? 'exemplar total' : 'exemplares no total'}
            </span>
          </div>

          <div className="gaveta__acoes-topo">
            {temLote && (
              <Botao
                variante="fantasma"
                tamanho="pequeno"
                onClick={lote.limpar}
                title="Limpar todos os itens do lote atual"
              >
                Limpar lote
              </Botao>
            )}
            <Botao
              variante="primario"
              tamanho="pequeno"
              onClick={enviar}
              disabled={!temLote || lote.enviando}
            >
              {lote.enviando
                ? 'Enviando…'
                : `Enviar para a Fila (${lote.itens.length} tít) →`}
            </Botao>
            <button
              className="gaveta__toggle-expandir"
              onClick={() => setGavetaExpandida((v) => !v)}
              aria-expanded={gavetaExpandida}
            >
              {gavetaExpandida ? 'Recolher ↑' : 'Expandir ↓'}
            </button>
          </div>
        </div>

        {temLote ? (
          <div className="gaveta__trilha" ref={trilhaRef}>
            {lote.itens.map((item) => (
              <CardLote
                key={item.isbn}
                item={item}
                aoAbrir={setAbertoIsbn}
                aoMudarQtd={(q) => lote.mudarQuantidade(item.isbn, q)}
                aoRemover={() => lote.remover(item.isbn)}
              />
            ))}
          </div>
        ) : (
          <div className="gaveta__vazia">
            <IconeLivro tamanho={22} />
            <span>Nenhum livro no lote ainda — aponte a câmera para bipar</span>
          </div>
        )}
      </section>

      {/* Modal de Ficha do Livro no Lote */}
      {aberto && (
        <ModalFicha
          item={aberto}
          aoFechar={() => setAbertoIsbn(null)}
          aoRemover={lote.remover}
          aoSalvar={({ cdd, cutter, quantidade }) => {
            lote.atualizarCampos(aberto.isbn, { cdd, cutter })
            if (quantidade !== aberto.quantidade) {
              lote.mudarQuantidade(aberto.isbn, quantidade)
            }
          }}
        />
      )}
    </div>
  )
}

function Visor({ scanner }) {
  const showFlash = scanner.tomStatus === 'ok' && scanner.escaneando
  const alvoClasse = [
    'visor__alvo',
    scanner.escaneando && scanner.tomStatus !== 'ok' ? 'visor__alvo--varrendo' : '',
    scanner.tomStatus === 'ok' ? 'visor__alvo--ok' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const statusClasse = [
    'visor__status',
    scanner.tomStatus ? `visor__status--${scanner.tomStatus}` : 'visor__status--info',
    !scanner.status ? 'visor__status--vazio' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      className="visor"
      onClick={() => scanner.escaneando && scanner.dispararFoco?.()}
      title={scanner.escaneando ? 'Toque para focar a câmera' : undefined}
    >
      <div id={scanner.elementoId} className="visor__camera" />

      {!scanner.escaneando && !scanner.erroCamera && (
        <div className="visor__repouso">
          <div className="visor__repouso-icone" aria-hidden="true">
            <IconeScanner tamanho={48} />
          </div>
          <p className="visor__repouso-texto">
            Toque no botão <strong>Iniciar câmera</strong> ou digite o ISBN abaixo para começar.
          </p>
          <Botao
            variante="primario"
            tamanho="toque"
            onClick={scanner.iniciar}
            style={{ marginTop: 8 }}
          >
            📷 Abrir Câmera do Scanner
          </Botao>
        </div>
      )}

      {scanner.escaneando && <div className={alvoClasse} aria-hidden="true" />}
      {showFlash && <div className="visor__flash" aria-hidden="true" />}

      {/* Controles sobrepostos no visor */}
      {scanner.escaneando && (
        <div className="visor__controles">
          {scanner.recursos.lanterna && (
            <button
              type="button"
              className={`visor__botao${scanner.lanternaLigada ? ' visor__botao--ativo' : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                scanner.alternarLanterna()
              }}
              aria-pressed={scanner.lanternaLigada}
              title="Ligar ou desligar lanterna"
            >
              <IconeLanterna tamanho={14} />
              <span>{scanner.lanternaLigada ? 'Lanterna Ligada' : 'Lanterna'}</span>
            </button>
          )}

          {scanner.recursos.zoom && (
            <label className="visor__zoom" onClick={(e) => e.stopPropagation()}>
              <span style={{ fontSize: 12 }}>🔍</span>
              <input
                type="range"
                min={scanner.recursos.zoom.min}
                max={scanner.recursos.zoom.max}
                step={scanner.recursos.zoom.passo}
                value={scanner.zoom ?? scanner.recursos.zoom.min}
                onChange={(e) => scanner.mudarZoom(Number(e.target.value))}
                aria-label="Aproximação da câmera"
              />
            </label>
          )}

          {!scanner.ocrAutoAtivo && (
            <button
              type="button"
              className="visor__botao"
              onClick={(e) => {
                e.stopPropagation()
                scanner.tentarOcr?.()
              }}
              disabled={scanner.ocrAtivo}
              title="Ler os números do ISBN abaixo do código de barras"
            >
              {scanner.ocrAtivo ? 'Lendo números…' : '123 Ler Números'}
            </button>
          )}
        </div>
      )}

      {scanner.erroCamera ? (
        <p className="visor__erro" role="alert">
          {scanner.erroCamera}
        </p>
      ) : (
        <p className={statusClasse} role="status" aria-live="polite">
          {scanner.status || '\u00A0'}
        </p>
      )}
    </div>
  )
}

function CardLote({ item, aoAbrir, aoMudarQtd, aoRemover }) {
  const qtd = Number(item.quantidade) || 1
  const noAcervo = item.acervo?.existe
  const buscando = item.buscando

  return (
    <div
      className={`card-lote ${noAcervo ? 'card-lote--existente' : 'card-lote--nova'} ${
        buscando ? 'card-lote--buscando' : ''
      }`}
    >
      <div className="card-lote__topo" onClick={() => aoAbrir(item.isbn)}>
        <div className="card-lote__info-esq">
          <span className="card-lote__isbn mono">{item.isbn}</span>
          <Selo tom={noAcervo ? 'existente' : 'nova'} className="card-lote__selo-tag">
            {noAcervo ? '+ exemplar' : 'obra nova'}
          </Selo>
        </div>
        <button
          className="card-lote__btn-remover"
          onClick={(e) => {
            e.stopPropagation()
            aoRemover()
          }}
          title="Tirar este livro do lote"
          aria-label="Remover do lote"
        >
          <IconeRemover tamanho={14} />
        </button>
      </div>

      <div className="card-lote__corpo" onClick={() => aoAbrir(item.isbn)}>
        <p className={`card-lote__titulo ${!item.titulo ? 'card-lote__titulo--vazio' : ''}`}>
          {item.titulo || (buscando ? 'Buscando metadados…' : '— sem título informado —')}
        </p>
        <p className="card-lote__autor">{item.autor || 'Autor não informado'}</p>
      </div>

      <div className="card-lote__rodape">
        <span className="card-lote__fonte">{item.offline ? 'offline' : item.fonte || '—'}</span>
        <Stepper
          valor={qtd}
          aoMudar={(novaQtd) => aoMudarQtd(novaQtd)}
          min={1}
          max={99}
        />
      </div>
    </div>
  )
}
