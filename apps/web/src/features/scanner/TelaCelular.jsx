import { useEffect, useRef, useState } from 'react'
import {
  Botao,
  Cantos,
  IconeLanterna,
  IconeRemover,
  Modal,
  Moldura,
  Selo,
  Stepper,
} from '../../components'
import { normalizarIsbnDigitado } from './isbn'
import { useLote } from './useLote'
import { useScanner } from './useScanner'
import './celular.css'

/**
 * A tela do celular. De pé na estante, uma mão no livro.
 *
 * É um aplicativo diferente do do PC, não o mesmo layout estreito: aqui a tela
 * inteira serve a um gesto só — apontar a câmera e ver que o bipe entrou. Nada
 * de tabela, nada de painel, nada de explicação do fluxo. O que não couber num
 * polegar não entra.
 *
 * Quatro faixas fixas, na ordem do design (quadro `Celular · /`): cabeçalho com
 * o estado do acervo, visor, bandeja e o botão de enviar. Nenhuma delas rola —
 * só a trilha da bandeja rola, na horizontal.
 *
 * É a única tela do aparelho: fila de revisão e conexão com o banco ficaram no
 * PC (ver App.jsx). Por isso ela ocupa a viewport inteira, sem barra de
 * navegação em cima nem embaixo, e não reporta contagem para badge nenhum — o
 * que sai daqui sai pela fila, no envio.
 */
export function TelaCelular({ conexao, dispositivo }) {
  const [pendente, setPendente] = useState(null)
  const [confirmarCada, setConfirmarCada] = useState(true)
  const [manual, setManual] = useState('')
  const [mostrarManual, setMostrarManual] = useState(false)
  const [ultimoIsbn, setUltimoIsbn] = useState('')
  const [envioFalhou, setEnvioFalhou] = useState('')
  const [enviado, setEnviado] = useState('')
  const [batizando, setBatizando] = useState(false)
  const [loteRecolhido, setLoteRecolhido] = useState(false)
  const trilhaRef = useRef(null)

  const lote = useLote({
    aoAvisar: (texto) => setEnvioFalhou(texto),
  })

  const scanner = useScanner({
    aoLer: async (isbn) => {
      setUltimoIsbn(isbn)
      const r = await lote.adicionar(isbn)
      if (!r) return
      scanner.anunciar(
        r.jaTinha ? `+1 exemplar · ${isbn}` : `No lote · ${isbn}`,
        'ok'
      )
      if (confirmarCada) setPendente(isbn)
    },
  })

  useEffect(() => {
    const t = trilhaRef.current
    if (t) t.scrollLeft = t.scrollWidth
  }, [lote.itens.length])

  const itemPendente = lote.itens.find((i) => i.isbn === pendente)

  // O item pendente saiu do lote (o "descartar" já rodou, ou o servidor
  // reconciliou): o modal não tem mais assunto.
  useEffect(() => {
    if (pendente && !itemPendente) setPendente(null)
  }, [pendente, itemPendente])

  const enviar = async () => {
    setEnvioFalhou('')
    try {
      const d = await lote.enviar()
      if (d) {
        setEnviado(
          `${d.enviados} ${d.enviados === 1 ? 'título foi' : 'títulos foram'} para a fila`
        )
        setTimeout(() => setEnviado(''), 4000)
      }
    } catch (e) {
      setEnvioFalhou(
        `Servidor fora do ar (${e.message}). O lote continua aqui, intacto — tente enviar de novo.`
      )
    }
  }

  const adicionarManual = () => {
    const isbn = normalizarIsbnDigitado(manual)
    if (!isbn) {
      scanner.anunciar('ISBN inválido — são 10 ou 13 dígitos', 'erro')
      return
    }
    setManual('')
    setUltimoIsbn(isbn)
    lote.adicionar(isbn)
    if (confirmarCada) setPendente(isbn)
  }

  const total = lote.totalExemplares
  const temLote = lote.itens.length > 0

  return (
    <div className={`cel ${loteRecolhido ? 'cel--camera-cheia' : ''}`}>
      <header className="cel__topo">
        <h1 className="cel__titulo">Escanear</h1>
        <button
          className={`cel__acervo cel__acervo--${conexao?.conectado ? 'ok' : 'off'}`}
          onClick={() => setBatizando((v) => !v)}
          title={conexao?.detalhe}
        >
          <span className="pilula__ponto" />
          {conexao?.conectado ? conexao.rotulo : 'Sem verificação'}
        </button>
      </header>

      {batizando && (
        <BatizarAparelho
          dispositivo={dispositivo}
          confirmarCada={confirmarCada}
          aoAlternarConfirmar={() => setConfirmarCada((v) => !v)}
          aoFechar={() => setBatizando(false)}
        />
      )}

      <VisorCelular scanner={scanner} ultimoIsbn={ultimoIsbn} />

      {/* Bandeja */}
      <section className="cel__lote">
        <div className="cel__lote-topo">
          <div className="cel__lote-info">
            <span className="microrrotulo">Lote</span>
            <span className="cel__lote-resumo">
              {temLote
                ? `${lote.itens.length} ${lote.itens.length === 1 ? 'título' : 'títulos'} · ${total} ex`
                : 'vazio'}
            </span>
          </div>
          <div className="cel__lote-acoes">
            {loteRecolhido && temLote && (
              <button
                type="button"
                className="cel__btn-enviar-compacto"
                onClick={enviar}
                disabled={lote.enviando}
                title="Enviar lote para a fila"
              >
                {lote.enviando ? '…' : `Enviar (${lote.itens.length})`}
              </button>
            )}
            <button
              type="button"
              className="cel__btn-collapse"
              onClick={() => setLoteRecolhido((v) => !v)}
              title={loteRecolhido ? 'Expandir lote' : 'Recolher lote para tela cheia'}
              aria-expanded={!loteRecolhido}
              aria-label={loteRecolhido ? 'Expandir lote' : 'Recolher lote'}
            >
              {loteRecolhido ? '+' : '−'}
            </button>
          </div>
        </div>

        {temLote ? (
          <div className="cel__trilha" ref={trilhaRef}>
            {lote.itens.map((item) => (
              <CardCelular
                key={item.isbn}
                item={item}
                aoAbrir={() => setPendente(item.isbn)}
                aoRemover={() => lote.remover(item.isbn)}
              />
            ))}
          </div>
        ) : (
          <p className="cel__vazio">
            Nada bipado ainda. O lote é volátil: sai daqui só quando você envia
            para a fila.
          </p>
        )}
      </section>

      {/* Enviar */}
      <footer className="cel__rodape">
        {envioFalhou && <p className="cel__erro">{envioFalhou}</p>}
        {enviado && <p className="cel__ok">{enviado}</p>}

        {!mostrarManual ? (
          <button
            className="cel__link-manual"
            onClick={() => setMostrarManual(true)}
          >
            Digitar o ISBN à mão
          </button>
        ) : (
          <div className="cel__manual">
            <input
              className="cel__manual-campo mono"
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && adicionarManual()}
              placeholder="978…"
              inputMode="numeric"
              autoFocus
              aria-label="ISBN manual"
            />
            <Botao
              variante="secundario"
              onClick={adicionarManual}
              disabled={!manual.trim()}
            >
              Buscar
            </Botao>
          </div>
        )}

        {/*
          O botão só existe quando há lote. Vazio ele era um retângulo
          desabilitado ocupando 52px do rodapé a cada bipe confirmado — e
          "enviar" não é um passo do ritmo de bipar, é o que se faz no fim da
          estante. Sem lote não há o que enviar, e o espaço volta para a
          bandeja.
        */}
        {temLote && (
          <button
            className="btn btn--primario btn--toque moldura cel__enviar"
            onClick={enviar}
            disabled={lote.enviando}
          >
            <Cantos />
            {lote.enviando
              ? 'Enviando…'
              : `Enviar ${lote.itens.length} para a fila →`}
          </button>
        )}
      </footer>

      {/* Modal de confirmação do bipe */}
      {itemPendente && (
        <ModalLeitura
          item={itemPendente}
          conectado={conexao?.conectado}
          aoConfirmar={() => setPendente(null)}
          aoDescartar={() => {
            lote.remover(itemPendente.isbn)
            setPendente(null)
          }}
          aoMudarQtd={(q) => lote.mudarQuantidade(itemPendente.isbn, q)}
        />
      )}
    </div>
  )
}

/**
 * O visor, ocupando a faixa alta da tela.
 *
 * A barra de status mora no pé do quadro e não flutua: quem está de pé com o
 * livro na mão não caça mensagem que muda de lugar. Status à esquerda, último
 * ISBN em monoespaçada à direita.
 */
function VisorCelular({ scanner, ultimoIsbn }) {
  const motor = scanner.motor === 'zxing' ? 'ZXING' : 'BARCODEDETECTOR'

  if (scanner.erroCamera) {
    return (
      <div className="cel__visor cel__visor--negado" role="alert">
        <div className="cel__negado-marca" aria-hidden="true">▲</div>
        <p className="cel__negado-titulo">Sem acesso à câmera</p>
        <p className="cel__negado-texto">{scanner.erroCamera}</p>
        <p className="cel__negado-nota">
          <code className="mono">getUserMedia</code> só funciona em contexto
          seguro. Se o aviso de certificado apareceu ao abrir por{' '}
          <code className="mono">https://&lt;IP&gt;:8000</code>, aceite o
          certificado autoassinado.
        </p>
        <Botao variante="primario" tamanho="toque" onClick={scanner.iniciar}>
          Pedir permissão de novo
        </Botao>
      </div>
    )
  }

  return (
    <div
      className="cel__visor"
      onClick={() => scanner.escaneando && scanner.dispararFoco?.()}
    >
      <div id={scanner.elementoId} className="cel__camera" />

      {!scanner.escaneando ? (
        <div className="cel__repouso">
          <Botao variante="primario" tamanho="toque" onClick={scanner.iniciar}>
            Abrir a câmera
          </Botao>
        </div>
      ) : (
        <>
          {/* Bouncing boxes dinâmicas */}
          <div className="cel__overlay" aria-hidden="true">
            {scanner.deteccoes?.length > 0 ? (
              scanner.deteccoes.map((d, i) => (
                <div
                  key={d.id || `${d.raw}-${i}`}
                  className={`cel__frame cel__frame--${d.tipo} ${d.dentroAlvo ? 'cel__frame--central' : ''} ${d.pulsando ? 'cel__frame--pulsando' : ''}`}
                  style={{
                    left: `${d.x * 100}%`,
                    top: `${d.y * 100}%`,
                    width: `${d.w * 100}%`,
                    height: `${d.h * 100}%`,
                  }}
                >
                  <span className="cel__frame-canto cel__frame-canto--se" />
                  <span className="cel__frame-canto cel__frame-canto--sd" />
                  <span className="cel__frame-canto cel__frame-canto--ie" />
                  <span className="cel__frame-canto cel__frame-canto--id" />
                  {d.raw ? (
                    <span className="cel__frame-label mono">
                      {d.raw.slice(-4)}
                    </span>
                  ) : null}
                </div>
              ))
            ) : (
              scanner.escaneando && (
                <span className="cel__hint-discreto">
                  Aponte para o código de barras
                </span>
              )
            )}
          </div>

          <div className="cel__controles">
            {scanner.recursos.lanterna && (
              <button
                type="button"
                className={`cel__botao${scanner.lanternaLigada ? ' cel__botao--ativo' : ''}`}
                onClick={(e) => {
                  e.stopPropagation()
                  scanner.alternarLanterna()
                }}
                aria-pressed={scanner.lanternaLigada}
                title="Ligar/desligar lanterna"
              >
                <IconeLanterna tamanho={13} />
              </button>
            )}
            {!scanner.ocrAutoAtivo && (
              <button
                type="button"
                className="cel__botao"
                onClick={(e) => {
                  e.stopPropagation()
                  scanner.tentarOcr?.()
                }}
                disabled={scanner.ocrAtivo}
                title="Ler os números do ISBN abaixo das barras"
              >
                {scanner.ocrAtivo ? '…' : '123'}
              </button>
            )}
            <button
              type="button"
              className="cel__botao"
              onClick={(e) => {
                e.stopPropagation()
                scanner.parar()
              }}
              title="Fechar a câmera"
            >
              ✕
            </button>
          </div>
        </>
      )}

      <div
        className={`cel__barra cel__barra--${scanner.tomStatus || 'info'}`}
        role="status"
        aria-live="polite"
      >
        <span className="cel__barra-status">
          {scanner.escaneando
            ? scanner.status || 'Aponte para o código de barras'
            : 'Câmera fechada'}
        </span>
        <span className="cel__barra-isbn mono">{ultimoIsbn || '—'}</span>
      </div>
    </div>
  )
}

/**
 * O modal que sobe depois do bipe.
 *
 * Não é um portão: o livro já está no lote quando ele aparece — o bipe nunca
 * espera decisão (docs/SPEC_UI.md §7). Ele existe para responder, ainda com o
 * livro na mão, a única pergunta que não se responde olhando a capa: isto vai
 * nascer como ficha nova ou virar exemplar de algo que a biblioteca já tem.
 *
 * Duas saídas, e só duas: "Confirmar e continuar" mantém o item e devolve a
 * câmera; "Descartar leitura" é que o remove. Fechar por Esc, pelo ✕ ou pelo
 * fundo vale como confirmar — sair sem decidir nunca apaga trabalho.
 *
 * Antes isto era um painel colado no meio da tela, entre o visor e a bandeja:
 * cobria as duas faixas de baixo e obrigava o resto do layout a existir em
 * função dele (o `top` da folha seguia a altura do visor em três media
 * queries). Como modal, a tela volta a ser quatro faixas simples e a decisão
 * ganha o fundo escurecido que diz que ela é a única coisa acontecendo.
 */
function ModalLeitura({ item, conectado, aoConfirmar, aoDescartar, aoMudarQtd }) {
  const qtd = Number(item.quantidade) || 1
  const noAcervo = item.acervo?.existe
  const linha2 =
    [item.autor, item.editora, item.ano].filter(Boolean).join(' · ') ||
    (item.buscando ? 'buscando metadados…' : 'sem metadados')

  return (
    <Modal
      titulo="Confirmar leitura"
      aoFechar={aoConfirmar}
      rodape={
        <div className="leitura__acoes">
          <Botao
            variante="secundario"
            tamanho="toque"
            onClick={aoDescartar}
            className="leitura__descartar"
          >
            Descartar leitura
          </Botao>
          <button
            className="btn btn--primario btn--toque moldura leitura__confirmar"
            onClick={aoConfirmar}
          >
            <Cantos />
            Confirmar e continuar
          </button>
        </div>
      }
    >
      <div className="leitura__cabecalho">
        <div className="leitura__identidade">
          <span className="leitura__isbn mono">{item.isbn}</span>
          <p className="leitura__titulo">
            {item.titulo || (item.buscando ? 'Buscando…' : 'sem título')}
          </p>
          <p className="leitura__linha2">{linha2}</p>
        </div>
        {item.capa ? (
          <img className="leitura__capa" src={item.capa} alt="" />
        ) : (
          <div className="leitura__capa leitura__capa--vazia hachura" aria-hidden="true" />
        )}
      </div>

      {noAcervo ? (
        <div className="leitura__destino leitura__destino--existente">
          <p className="leitura__destino-titulo">Já está no acervo</p>
          <p>
            Obra #{item.acervo.record_id} · {item.acervo.exemplares}{' '}
            {item.acervo.exemplares === 1 ? 'exemplar' : 'exemplares'} hoje.
          </p>
          <p>
            Não vira ficha nova — {qtd}{' '}
            {qtd === 1 ? 'exemplar entra' : 'exemplares entram'} nessa obra.
          </p>
        </div>
      ) : conectado ? (
        <div className="leitura__destino leitura__destino--nova">
          <p className="leitura__destino-titulo">Obra nova</p>
          <p>
            Nasce uma ficha com {qtd}{' '}
            {qtd === 1 ? 'exemplar' : 'exemplares'}. Exige reindexar no BibLivre
            depois de gravar.
          </p>
        </div>
      ) : (
        <div className="leitura__destino leitura__destino--alerta">
          <p className="leitura__destino-titulo">Não verificado</p>
          <p>
            Banco desconectado: este ISBN não foi confrontado com o acervo. Na
            gravação ele entra como obra nova.
          </p>
        </div>
      )}

      <div className="leitura__exemplares">
        <span>Exemplares</span>
        <Stepper valor={qtd} aoMudar={aoMudarQtd} min={1} max={99} grande />
      </div>
    </Modal>
  )
}

/** Painel de ajustes: o nome com que este aparelho aparece no PC. */
function BatizarAparelho({ dispositivo, confirmarCada, aoAlternarConfirmar, aoFechar }) {
  const [rascunho, setRascunho] = useState(dispositivo?.nome || '')

  return (
    <Moldura className="ajustes">
      <span className="microrrotulo">Este aparelho</span>
      <p className="ajustes__desc">
        O nome aparece no painel do PC, ao lado do que você bipou. Sem nome, o
        PC mostra <code className="mono">{`Aparelho ${(dispositivo?.id || '').slice(0, 6)}`}</code>.
      </p>
      <div className="ajustes__linha">
        <input
          className="ajustes__campo"
          value={rascunho}
          onChange={(e) => setRascunho(e.target.value)}
          placeholder="Celular da Ana"
          aria-label="Nome deste aparelho"
        />
        <Botao
          variante="secundario"
          onClick={() => {
            dispositivo?.batizar(rascunho)
            aoFechar()
          }}
        >
          Salvar
        </Botao>
      </div>

      <label className="ajustes__caixa">
        <input type="checkbox" checked={confirmarCada} onChange={aoAlternarConfirmar} />
        <span>
          Confirmar cada bipe
          <em>
            {confirmarCada
              ? 'a ficha sobe a cada leitura — bom para conferir na hora'
              : 'bipe direto no lote — bom para lote grande e rápido'}
          </em>
        </span>
      </label>
    </Moldura>
  )
}

function CardCelular({ item, aoAbrir, aoRemover }) {
  const qtd = Number(item.quantidade) || 1
  const noAcervo = item.acervo?.existe

  return (
    <div
      className={`cel-card ${noAcervo ? 'cel-card--existente' : 'cel-card--nova'}`}
      onClick={aoAbrir}
    >
      <div className="cel-card__topo">
        <span className="cel-card__isbn mono">…{item.isbn.slice(-6)}</span>
        <span className="cel-card__mult numero">×{qtd}</span>
      </div>
      <p className="cel-card__titulo">
        {item.titulo || (item.buscando ? 'buscando…' : 'sem título')}
      </p>
      <p className="cel-card__autor">{item.autor || '—'}</p>
      {noAcervo && (
        <Selo tom="existente" className="cel-card__selo">
          já no acervo
        </Selo>
      )}
      <button
        className="cel-card__remover"
        onClick={(e) => {
          e.stopPropagation()
          aoRemover()
        }}
        aria-label="Tirar do lote"
      >
        <IconeRemover tamanho={12} />
      </button>
    </div>
  )
}
