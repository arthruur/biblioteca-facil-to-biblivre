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
        r.jaTinha ? `Mais um exemplar de ${isbn}` : `Adicionado ${isbn}`,
        'ok'
      )
    },
  })

  // A galeria acompanha o último bipe: quem está de pé não deveria precisar
  // rolar para confirmar que o livro entrou.
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

  return (
    <div className="escanear">
      <header className="escanear__topo">
        <div className="escanear__marca">
          <span className="escanear__titulo">Escanear</span>
          <span className="escanear__sub">catalogação por ISBN</span>
        </div>
        <div style={{ display: 'flex', gap: 'var(--e2)', alignItems: 'center' }}>
          <Pilula tom={conexao.tom} title={conexao.detalhe}>
            {conexao.rotulo}
          </Pilula>
          <Botao variante="fantasma" tamanho="pequeno" onClick={aoIrParaFila}>
            Fila →
          </Botao>
        </div>
      </header>

      <div className="escanear__corpo">
        <Visor scanner={scanner} />

        <aside className="escanear__lateral controles__so-desktop">
          {info?.server_url && (
            <div className="qr">
              <p
                className="galeria__rotulo"
                style={{ marginBottom: 'var(--e2)' }}
              >
                Abra no celular
              </p>
              <div className="qr__caixa">
                <img src="/api/qrcode" alt="QR code para abrir no celular" />
              </div>
              <p className="qr__url">{info.server_url}</p>
            </div>
          )}
          <p style={{ fontSize: 'var(--txt-sm)', color: 'var(--texto-2)' }}>
            O scanner precisa de HTTPS para acessar a câmera. Ao abrir no
            celular, aceite o certificado uma vez.
          </p>
        </aside>
      </div>

      <Galeria
        itens={lote.itens}
        total={lote.totalExemplares}
        trilhaRef={trilhaRef}
        aoAbrir={setAbertoIsbn}
      />

      <div className="controles">
        <div className="controles__linha">
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
            className="controles__so-desktop"
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

        <p className={`controles__recado controles__recado--${tomRecado}`} role="status">
          {recado}
        </p>

        {lote.itens.length > 0 && (
          <div className="controles__linha">
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
                : `Enviar para a fila (${lote.itens.length} tít, ${lote.totalExemplares} ex)`}
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
  return (
    <div className="visor">
      <div id={scanner.elementoId} className="visor__camera" />

      {!scanner.escaneando && !scanner.erroCamera && (
        <div className="visor__repouso">
          <span className="visor__repouso-icone" aria-hidden="true">
            📷
          </span>
          <p className="visor__repouso-texto">
            Toque em <strong>Escanear</strong> e aponte para o código de barras
            na contracapa. A câmera fica aberta entre um livro e outro.
          </p>
        </div>
      )}

      {scanner.escaneando && <div className="visor__alvo" aria-hidden="true" />}

      {scanner.escaneando && (scanner.recursos.lanterna || scanner.recursos.zoom) && (
        <div className="visor__controles">
          {scanner.recursos.lanterna && (
            <button
              type="button"
              className={`visor__botao${
                scanner.lanternaLigada ? ' visor__botao--ativo' : ''
              }`}
              onClick={scanner.alternarLanterna}
              aria-pressed={scanner.lanternaLigada}
            >
              <span aria-hidden="true">◉</span> Lanterna
            </button>
          )}
          {scanner.recursos.zoom && (
            <label className="visor__zoom">
              <span aria-hidden="true">🔍</span>
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
        </div>
      )}

      {scanner.erroCamera ? (
        <p className="visor__erro" role="alert">
          {scanner.erroCamera}
        </p>
      ) : (
        <p
          className={`visor__status visor__status--${scanner.tomStatus}`}
          role="status"
          aria-live="polite"
        >
          {scanner.status}
        </p>
      )}
    </div>
  )
}

function Galeria({ itens, total, trilhaRef, aoAbrir }) {
  if (!itens.length) return null

  return (
    <section className="galeria" aria-label="Lote">
      <div className="galeria__cabecalho">
        <span className="galeria__rotulo">No lote</span>
        <span className="galeria__contagem">
          {itens.length} {itens.length === 1 ? 'título' : 'títulos'}
          {total > itens.length && ` · ${total} exemplares`}
        </span>
      </div>
      <div className="galeria__trilha" ref={trilhaRef}>
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
  const classes = [
    'card-lote',
    noAcervo && 'card-lote--existente',
    item.buscando && 'card-lote--buscando',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      className={classes}
      onClick={() => aoAbrir(item.isbn)}
      aria-label={`${item.titulo || item.isbn}, ${qtd} exemplar(es). Abrir ficha.`}
    >
      <div className="card-lote__linha">
        <span className="card-lote__isbn">{item.isbn}</span>
        {qtd > 1 && <span className="card-lote__vezes">×{qtd}</span>}
      </div>
      <p
        className={`card-lote__titulo${
          item.titulo ? '' : ' card-lote__titulo--vazio'
        }`}
      >
        {item.titulo || (item.buscando ? 'buscando…' : 'sem metadados')}
      </p>
      {item.autor && <p className="card-lote__autor">{item.autor}</p>}
      {noAcervo && (
        <p className="card-lote__acervo">
          ✓ já no acervo · {item.acervo.exemplares} ex
        </p>
      )}
      <p className="card-lote__rodape">
        {item.offline ? 'sem conexão' : item.fonte || ''}
      </p>
    </button>
  )
}
