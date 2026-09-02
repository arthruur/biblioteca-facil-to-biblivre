import { useEffect, useRef, useState } from 'react'
import { Botao, Pilula } from '../../components'
import { ModalFicha } from './ModalFicha'
import { useLote } from './useLote'
import { normalizarIsbnDigitado } from './isbn'
import { useScanner } from './useScanner'
import './scanner.css'

export function TelaEscanear({ info, conexao, aoIrParaFila }) {
  const [recado, setRecado] = useState('')
  const [tomRecado, setTomRecado] = useState('')
  const [abertoIsbn, setAbertoIsbn] = useState(null)
  const [manual, setManual] = useState('')
  const [gavetaExpandida, setGavetaExpandida] = useState(false)
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
        r.jaTinha ? `+1 exemplar · ${isbn}` : `Adicionado · ${isbn}`,
        'ok'
      )
    },
  })

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
          `${d.enviados} ${d.enviados === 1 ? 'título enviado' : 'títulos enviados'} para a fila`,
          'ok'
        )
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

  const total = lote.totalExemplares
  const temLote = lote.itens.length > 0

  return (
    <div className="escanear">
      <header className="escanear__topo">
        <div className="escanear__marca">
          <span className="escanear__titulo">Escanear</span>
          <span className="escanear__sub">Balcão · ISBN</span>
        </div>
        <div style={{ display: 'flex', gap: 'var(--e2)', alignItems: 'center' }}>
          <Pilula tom={conexao.tom} title={conexao.detalhe}>
            {conexao.rotulo}
          </Pilula>
          <Botao
            variante="fantasma"
            tamanho="pequeno"
            onClick={aoIrParaFila}
            className="controles__so-desktop"
          >
            Fila →
          </Botao>
          {/* mobile badge */}
          <button
            onClick={aoIrParaFila}
            className="gaveta__badge"
            style={{ display: temLote ? 'inline-flex' : 'none' }}
            aria-label={`Ir para fila com ${lote.itens.length} títulos`}
          >
            {lote.itens.length} na fila
          </button>
        </div>
      </header>

      <div className="escanear__corpo">
        <Visor scanner={scanner} onExpandir={() => setGavetaExpandida((v) => !v)} />

        <aside className="escanear__lateral controles__so-desktop">
          {info?.server_url && (
            <div className="qr">
              <p className="galeria__rotulo" style={{ marginBottom: 'var(--e2)' }}>
                Abra no celular
              </p>
              <div className="qr__caixa">
                <img src="/api/qrcode" alt="QR code para abrir no celular" />
              </div>
              <p className="qr__url">{info.server_url}</p>
            </div>
          )}
          <p style={{ fontSize: 'var(--txt-sm)', color: 'var(--texto-2)' }}>
            O scanner precisa de HTTPS. Ao abrir no celular, aceite o certificado uma vez.
          </p>
          {temLote && (
            <div style={{ marginTop: 'var(--e4)' }}>
              <p className="galeria__rotulo">No lote</p>
              <p style={{ fontSize: 'var(--txt-sm)', color: 'var(--texto-2)' }}>
                {lote.itens.length} títulos · {total} exemplares
              </p>
            </div>
          )}
        </aside>
      </div>

      {/* Gaveta: bottom sheet no mobile, galeria no desktop */}
      {temLote ? (
        <Gaveta
          itens={lote.itens}
          total={total}
          trilhaRef={trilhaRef}
          aoAbrir={setAbertoIsbn}
          expandida={gavetaExpandida}
          aoToggle={() => setGavetaExpandida((v) => !v)}
        />
      ) : (
        <div
          className="gaveta"
          style={{ padding: '14px var(--e4)', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8, color: 'var(--texto-3)', fontSize: 'var(--txt-sm)' }}
        >
          <span aria-hidden>📚</span> Nenhum livro no lote — bipar enche aqui
        </div>
      )}

      <div className="controles">
        {/* FAB bar — só mobile (escondida via CSS no desktop) */}
        <div className="fab-bar">
          {scanner.escaneando ? (
            <button className="fab fab--parar" onClick={scanner.parar} aria-label="Fechar câmera">
              ✕
            </button>
          ) : (
            <button className="fab" onClick={scanner.iniciar} aria-label="Abrir câmera">
              ◎
            </button>
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: '11px', color: 'var(--texto-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {temLote ? `${lote.itens.length} títulos · ${total} ex` : 'Lote vazio'}
            </div>
            <div style={{ fontSize: 'var(--txt-xs)', color: 'var(--texto-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {recado || (scanner.escaneando ? 'Aponte para as barras' : 'Toque no botão para escanear')}
            </div>
          </div>
          <button
            className={`fab-acao ${!temLote ? 'fab-acao--sec' : ''}`}
            onClick={enviar}
            disabled={!temLote || lote.enviando}
            style={{ flex: '0 0 auto', minWidth: 124 }}
          >
            {lote.enviando ? 'Enviando…' : `Enviar →`}
          </button>
        </div>

        {/* Desktop controls */}
        <div className="controles__linha controles__so-desktop">
          {scanner.escaneando ? (
            <Botao variante="secundario" tamanho="toque" onClick={scanner.parar}>
              Fechar câmera
            </Botao>
          ) : (
            <Botao variante="primario" tamanho="toque" onClick={scanner.iniciar}>
              Escanear
            </Botao>
          )}
          <Botao
            variante="secundario"
            tamanho="toque"
            onClick={() => arquivoRef.current?.click()}
          >
            Usar foto
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

        <div className="controles__manual">
          <input
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && adicionarManual()}
            placeholder="Digitar ISBN (10 ou 13 dígitos)"
            inputMode="numeric"
            aria-label="ISBN manual"
          />
          <Botao onClick={adicionarManual} disabled={!manual.trim()}>
            Adicionar
          </Botao>
        </div>

        <p className={`controles__recado controles__recado--${tomRecado} controles__so-desktop`} role="status">
          {recado}
        </p>

        {temLote && (
          <div className="controles__linha controles__so-desktop">
            <Botao variante="fantasma" onClick={lote.limpar} style={{ flex: '0 0 auto' }}>
              Limpar
            </Botao>
            <Botao
              variante="primario"
              tamanho="toque"
              onClick={enviar}
              disabled={lote.enviando}
            >
              {lote.enviando
                ? 'Enviando…'
                : `Enviar para a fila (${lote.itens.length} tít, ${total} ex)`}
            </Botao>
          </div>
        )}
      </div>

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
      title={scanner.escaneando ? 'Toque para focar' : undefined}
    >
      <div id={scanner.elementoId} className="visor__camera" />

      {!scanner.escaneando && !scanner.erroCamera && (
        <div className="visor__repouso">
          <span className="visor__repouso-icone" aria-hidden="true">
            📷
          </span>
          <p className="visor__repouso-texto">
            Toque no botão circular e aponte para o código de barras da contracapa.
          </p>
          <p style={{ fontSize: 'var(--txt-xs)', opacity: 0.8, marginTop: 8 }}>
            Toque no visor para focar
          </p>
        </div>
      )}

      {scanner.escaneando && <div className={alvoClasse} aria-hidden="true" />}
      {showFlash && <div className="visor__flash" aria-hidden="true" />}

      {scanner.escaneando && (
        <div className="visor__controles">
          {(scanner.recursos.lanterna || scanner.recursos.zoom) && (
            <>
              {scanner.recursos.lanterna && (
                <button
                  type="button"
                  className={`visor__botao${scanner.lanternaLigada ? ' visor__botao--ativo' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    scanner.alternarLanterna()
                  }}
                  aria-pressed={scanner.lanternaLigada}
                >
                  ◉ Lanterna
                </button>
              )}
              {scanner.recursos.zoom && (
                <label className="visor__zoom" onClick={(e) => e.stopPropagation()}>
                  🔍
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
            </>
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
            >
              {scanner.ocrAtivo ? 'Lendo…' : 'Tentar números'}
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

function Gaveta({ itens, total, trilhaRef, aoAbrir, expandida, aoToggle }) {
  return (
    <section className={`gaveta ${expandida ? 'gaveta--expandida' : ''}`} aria-label="Lote">
      <div className="gaveta__puxador" aria-hidden />
      <div className="gaveta__cabecalho">
        <span className="gaveta__titulo">
          No lote <span className="gaveta__badge">{itens.length}</span>
          <span style={{ fontWeight: 400, color: 'var(--texto-2)', fontSize: 'var(--txt-xs)' }}>
            {total > itens.length ? `· ${total} ex` : ''}
          </span>
        </span>
        <button className="gaveta__acao" onClick={aoToggle} aria-expanded={expandida}>
          {expandida ? 'Recolher ↑' : 'Ver todos →'}
        </button>
      </div>
      <div className="gaveta__trilha" ref={trilhaRef}>
        {itens.map((item) => (
          <CardLote key={item.isbn} item={item} aoAbrir={aoAbrir} />
        ))}
      </div>
    </section>
  )
}

function CardLote({ item, aoAbrir }) {
  const qtd = Number(item.quantidade) || 1
  const noAcervo = item.acervo?.existe
  const buscando = item.buscando
  const classes = ['card-lote', noAcervo && 'card-lote--existente', buscando && 'card-lote--buscando']
    .filter(Boolean)
    .join(' ')
  const selo = noAcervo ? (
    <span className="card-lote__selo card-lote__selo--ex">+ exemplar</span>
  ) : item.titulo ? (
    <span className="card-lote__selo card-lote__selo--nova">nova</span>
  ) : null

  return (
    <button className={classes} onClick={() => aoAbrir(item.isbn)} aria-label={`${item.titulo || item.isbn}, ${qtd} exemplar(es).`}>
      <div className="card-lote__linha">
        <span className="card-lote__isbn">{item.isbn}</span>
        {qtd > 1 && <span className="card-lote__vezes">×{qtd}</span>}
      </div>
      <p className={`card-lote__titulo${item.titulo ? '' : ' card-lote__titulo--vazio'}`}>
        {item.titulo || (buscando ? 'buscando…' : 'sem metadados')}
      </p>
      {item.autor && <p className="card-lote__autor">{item.autor}</p>}
      <p className="card-lote__rodape">
        {selo}
        <span>{item.offline ? 'offline' : item.fonte || '—'}</span>
      </p>
    </button>
  )
}
