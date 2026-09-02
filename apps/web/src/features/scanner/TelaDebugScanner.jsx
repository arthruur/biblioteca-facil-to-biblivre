import { useCallback, useEffect, useRef, useState } from 'react'
import { Botao, IconeLanterna } from '../../components'
import { OverlayDeteccoes } from './OverlayDeteccoes'
import {
  acumular,
  diagnosticarEtapa,
  estadoInicial,
} from './core/diagnostico.js'
import { classificarCodigo } from './isbn.js'
import { useScanner } from './useScanner'
import './celular.css'
import './debug.css'

/**
 * A bancada do scanner: a mesma câmera da tela de bipar, sem lote e sem envio.
 *
 * Existe porque "o scanner não lê" não é um sintoma acionável — o laço tem
 * quatro etapas em sequência e cada uma falha por motivo próprio:
 *
 *   1. Quadro     — o `<video>` entrega pixels? (`videoWidth`, `readyState`)
 *   2. Candidatos — a heurística de ROI acha o quadrado das barras num canvas
 *                   de 400px (`core/candidatos.js`)
 *   3. Decodifica — o `BarcodeDetector` lê o recorte em alta resolução, ou o
 *                   quadro inteiro na salvaguarda
 *   4. Classifica — o texto lido é ISBN, EAN de preço ou lixo (`isbn.js`)
 *
 * Aqui as etapas 2 e 3 podem ser desligadas em separado (é o teste que responde
 * "a ROI está atrapalhando ou salvando?"), o laço congela e anda de passo em
 * passo, e o recorte que vai para o decodificador aparece do lado — se o
 * quadradinho pousa certo e o recorte sai borrado, o problema é foco, não
 * detecção.
 *
 * Nada daqui grava: o que é lido só é anunciado na lista.
 */
export function TelaDebugScanner() {
  const [diag, setDiag] = useState(estadoInicial)
  const [lidos, setLidos] = useState([])
  const [mostrarRecorte, setMostrarRecorte] = useState(true)

  const acumuladoRef = useRef(estadoInicial())
  const ultimoRenderRef = useRef(0)
  const recorteRef = useRef(null)

  /*
    O laço roda a até ~22 passos por segundo: repintar o painel a cada passo
    derruba o próprio scanner que estamos medindo. Os contadores são somados num
    ref (custo zero) e o React só é acordado a cada 200ms.
  */
  const aoDepurar = useCallback((registro) => {
    acumuladoRef.current = acumular(acumuladoRef.current, registro)

    if (mostrarRecorte && registro.recorte) {
      const destino = recorteRef.current
      const ctx = destino?.getContext('2d')
      if (ctx) {
        const fonte = registro.recorte
        const escala = Math.min(destino.width / fonte.width, 1)
        const alturaAlvo = Math.round(fonte.height * escala) || destino.height
        ctx.clearRect(0, 0, destino.width, destino.height)
        ctx.drawImage(fonte, 0, 0, destino.width, alturaAlvo)
      }
    }

    const agora = Date.now()
    if (agora - ultimoRenderRef.current > 200) {
      ultimoRenderRef.current = agora
      setDiag(acumuladoRef.current)
    }
  }, [mostrarRecorte])

  const scanner = useScanner({
    aoDepurar,
    aoLer: (isbn) => {
      setLidos((atual) => [
        { isbn, hora: new Date().toLocaleTimeString('pt-BR') },
        ...atual.slice(0, 9),
      ])
      scanner.anunciar(`ISBN aceito · ${isbn}`, 'ok')
    },
  })

  // Abre a câmera sozinha: a tela só existe para olhar o laço rodando.
  useEffect(() => {
    scanner.iniciar()
    return () => scanner.parar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const zerar = () => {
    acumuladoRef.current = estadoInicial()
    setDiag(acumuladoRef.current)
    setLidos([])
  }

  const etapas = scanner.etapas || {}

  return (
    <div className="dbg">
      <header className="dbg__topo">
        <div>
          <h1 className="dbg__titulo">Depurar o scanner</h1>
          <p className="dbg__sub">
            Motor: <strong>{scanner.motor || '—'}</strong> · lanterna:{' '}
            {scanner.recursos.lanterna ? 'anunciada' : 'não anunciada'}
          </p>
        </div>
        <a className="dbg__voltar" href="/">
          ← Voltar
        </a>
      </header>

      <div className="dbg__visor cel__visor">
        <div id={scanner.elementoId} className="cel__camera" />

        {scanner.erroCamera ? (
          <div className="dbg__erro" role="alert">
            <p>{scanner.erroCamera}</p>
            <Botao variante="primario" tamanho="toque" onClick={scanner.iniciar}>
              Pedir permissão de novo
            </Botao>
          </div>
        ) : (
          <OverlayDeteccoes
            deteccoes={scanner.deteccoes}
            quadro={scanner.quadro}
            alvo={scanner.alvo}
            depurando
          />
        )}

        <div className="cel__controles">
          <button
            type="button"
            className={`cel__botao${scanner.lanternaLigada ? ' cel__botao--ativo' : ''}`}
            onClick={scanner.alternarLanterna}
            aria-pressed={scanner.lanternaLigada}
            title="Lanterna"
          >
            <IconeLanterna tamanho={16} />
          </button>
          <button
            type="button"
            className="cel__botao"
            onClick={scanner.dispararFoco}
            title="Forçar um pulso de foco"
          >
            ◎
          </button>
        </div>

        <div className={`cel__barra cel__barra--${scanner.tomStatus || 'info'}`} role="status">
          <span className="cel__barra-status">{scanner.status || '—'}</span>
          <span className="cel__barra-isbn mono">
            {diag.fps ? `${diag.fps.toFixed(1)}/s` : '—'}
          </span>
        </div>
      </div>

      <div className="dbg__painel">
        <div className="dbg__acoes">
          {!scanner.escaneando ? (
            <button className="dbg__btn dbg__btn--forte" onClick={scanner.iniciar}>
              Abrir a câmera
            </button>
          ) : (
            <button className="dbg__btn" onClick={scanner.parar}>
              Fechar a câmera
            </button>
          )}
          <button
            className={`dbg__btn${scanner.pausado ? ' dbg__btn--forte' : ''}`}
            onClick={scanner.alternarPausa}
            disabled={!scanner.escaneando}
          >
            {scanner.pausado ? 'Descongelar' : 'Congelar'}
          </button>
          <button
            className="dbg__btn"
            onClick={scanner.passoUnico}
            disabled={!scanner.pausado}
            title="Roda um passo do laço e congela de novo"
          >
            1 passo
          </button>
          <button className="dbg__btn" onClick={zerar}>
            Zerar
          </button>
        </div>

        <p className="dbg__veredito">{diagnosticarEtapa(diag)}</p>

        <ol className="dbg__etapas">
          <Etapa
            n={1}
            nome="Quadro do vídeo"
            ok={diag.videoW > 0 && diag.readyState >= 2}
            detalhe={`${diag.videoW}×${diag.videoH} · readyState ${diag.readyState} · ${diag.ms.toFixed(1)}ms/passo`}
            contadores={[
              ['passos', diag.passos],
              ['sem quadro', diag.quadrosCrus],
            ]}
          />
          <Etapa
            n={2}
            nome="Candidatos (ROI 400px)"
            ok={diag.comCandidatos > 0}
            desligada={!etapas.candidatos}
            detalhe={
              etapas.candidatos
                ? `agora: ${diag.candidatos} candidato(s) · densidade ${Math.round(diag.densidade)}`
                : 'desligada — só a salvaguarda de quadro cheio roda'
            }
            contadores={[
              ['passos com', diag.comCandidatos],
              ['passos sem', diag.semCandidatos],
            ]}
            aoAlternar={() => scanner.definirEtapas({ candidatos: !etapas.candidatos })}
          />
          <Etapa
            n={3}
            nome="Decodificação do recorte"
            ok={diag.decodificados > 0}
            detalhe={`${diag.tentativas} recorte(s) enviados · ${diag.achados} achado(s) do detector`}
            contadores={[
              ['lidos', diag.decodificados],
              ['salvaguardas', diag.salvaguardas],
            ]}
            aoAlternar={() => scanner.definirEtapas({ salvaguarda: !etapas.salvaguarda })}
            rotuloAlternar={
              etapas.salvaguarda ? 'desligar salvaguarda' : 'ligar salvaguarda'
            }
          />
          <Etapa
            n={4}
            nome="Classificação (ISBN?)"
            ok={diag.aceitos > 0}
            detalhe={
              diag.ultimoBruto
                ? `último bruto: ${diag.ultimoBruto} → ${classificarCodigo(diag.ultimoBruto).tipo}`
                : 'nada lido ainda'
            }
            contadores={[
              ['aceitos', diag.aceitos],
              ['recusados', diag.rejeitados],
            ]}
          />
        </ol>

        <div className="dbg__colunas">
          <section className="dbg__bloco">
            <h2 className="microrrotulo">Recorte que o decodificador vê</h2>
            <label className="dbg__caixa">
              <input
                type="checkbox"
                checked={mostrarRecorte}
                onChange={() => setMostrarRecorte((v) => !v)}
              />
              <span>espelhar o recorte</span>
            </label>
            <canvas ref={recorteRef} className="dbg__recorte" width={320} height={200} />
            <p className="dbg__nota">
              Recorte borrado com quadradinho no lugar certo = foco. Recorte
              nítido e nada lido = o código não é EAN-13/ISBN ou está torto.
            </p>
          </section>

          <section className="dbg__bloco">
            <h2 className="microrrotulo">Códigos brutos</h2>
            {diag.historico.length === 0 ? (
              <p className="dbg__nota">Nenhum código bruto saiu do detector ainda.</p>
            ) : (
              <ul className="dbg__lista">
                {diag.historico.map((h, i) => (
                  <li key={`${h.t}-${i}`} className={`dbg__item dbg__item--${h.tipo}`}>
                    <span className="mono">{h.bruto}</span>
                    <span className="dbg__tag">{h.tipo}</span>
                    <span className="dbg__tag">{h.fase}</span>
                    <span className="dbg__tag">{h.aceito ? 'aceito' : 'recusado'}</span>
                  </li>
                ))}
              </ul>
            )}

            <h2 className="microrrotulo dbg__titulo-2">ISBN entregues</h2>
            {lidos.length === 0 ? (
              <p className="dbg__nota">Nenhum ISBN entregue nesta sessão.</p>
            ) : (
              <ul className="dbg__lista">
                {lidos.map((l) => (
                  <li key={`${l.isbn}-${l.hora}`} className="dbg__item dbg__item--isbn">
                    <span className="mono">{l.isbn}</span>
                    <span className="dbg__tag">{l.hora}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

/** Uma etapa do laço, com o sinal de que ela fechou ao menos uma vez. */
function Etapa({ n, nome, ok, desligada, detalhe, contadores, aoAlternar, rotuloAlternar }) {
  return (
    <li
      className={`dbg__etapa${ok ? ' dbg__etapa--ok' : ''}${desligada ? ' dbg__etapa--off' : ''}`}
    >
      <span className="dbg__etapa-n numero">{n}</span>
      <div className="dbg__etapa-corpo">
        <p className="dbg__etapa-nome">
          {nome}
          {aoAlternar && (
            <button type="button" className="dbg__mini" onClick={aoAlternar}>
              {rotuloAlternar || (desligada ? 'ligar' : 'desligar')}
            </button>
          )}
        </p>
        <p className="dbg__etapa-detalhe mono">{detalhe}</p>
        <p className="dbg__etapa-contadores">
          {contadores.map(([rotulo, valor]) => (
            <span key={rotulo}>
              {rotulo} <strong className="numero">{valor}</strong>
            </span>
          ))}
        </p>
      </div>
    </li>
  )
}
