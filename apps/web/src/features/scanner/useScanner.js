/**
 * @fileoverview Hook React orquestrador do leitor de código de barras.
 *
 * PROPOSITO:
 * Centraliza o estado reativo da interface (status, erros, motor, recursos)
 * e conecta o ciclo de vida da câmera (`core/camera.js`), o laço nativo
 * (`core/scannerLoop.js`) e o fallback para OCR (`core/ocr.js`).
 *
 * INTERFACE:
 * - useScanner({ aoLer, aoDepurar?, janelaRepeticao?, modo? }): object
 *
 * MODOS:
 * - 'isbn' (padrão) — catalogação. Lê o EAN-13 da capa e só entrega ISBN válido.
 *   Comportamento idêntico ao de sempre; nada aqui muda para quem não passa `modo`.
 * - 'circulacao' — balcão. Lê também a etiqueta do exemplar (Code 39 / Code 128) e
 *   entrega tombo, ISBN ou número solto, deixando a decisão final para
 *   `GET /api/circulacao/resolver`. Veja `./codigos.js`.
 *
 * FLUXO:
 * Consumido por `TelaCelular.jsx` (uso real) e por `TelaDebugScanner.jsx`
 * (depuração etapa por etapa). Orquestra módulos de `core/` e `utils/`.
 *
 * LIMITACOES:
 * Exige ambiente de navegador com suporte a getUserMedia e Canvas.
 * O `modo` é lido na abertura da câmera: trocar de modo com a câmera aberta exige
 * `parar()` e `iniciar()` de novo, porque o conjunto de formatos é fixado no detector.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { tocarBeepSucesso, vibrar } from './core/audio.js'
import { abrirCamera, ajustarCamera, alternarLanterna, aplicarZoom, dispararPulsoFoco, fecharCamera, obterTrackDoVideo, RESTRICOES_VIDEO } from './core/camera.js'
import { criarDetectorNativo, executarLeituraFoto, formatosNativos, iniciarLeitorReserva, tipoMotor } from './core/decodificador.js'
import { ALVO } from './core/geometria.js'
import { encerrarWorkerOcr, executarTentativaOcr } from './core/ocr.js'
import { ETAPAS_PADRAO, iniciarLacoNativo } from './core/scannerLoop.js'
import { classificarCirculacao } from './codigos.js'
import { classificarCodigo } from './isbn.js'
import { formatarErroCamera } from './utils/erros.js'

const ELEMENTO = 'visor-camera'

/**
 * O que cada modo aceita entregar à tela. No modo isbn continua sendo só ISBN — um
 * EAN de preço nunca virou leitura e não pode virar agora. No modo circulação passa
 * tudo que pode identificar exemplar ou leitor, porque quem separa é o servidor.
 */
const TIPOS_ACEITOS = Object.freeze({
  isbn: Object.freeze(['isbn']),
  circulacao: Object.freeze(['tombo', 'isbn', 'numero']),
})

export function useScanner({ aoLer, aoDepurar, janelaRepeticao = 2500, modo = 'isbn' } = {}) {
  const [escaneando, setEscaneando] = useState(false)
  const [status, setStatus] = useState(''); const [tomStatus, setTomStatus] = useState('')
  const [erroCamera, setErroCamera] = useState(''); const [motor, setMotor] = useState('')
  const [recursos, setRecursos] = useState({ lanterna: false, zoom: null })
  const [lanternaLigada, setLanternaLigada] = useState(false); const [zoom, setZoom] = useState(null)
  const [deteccoes, setDeteccoes] = useState([]); const [ocrAtivo, setOcrAtivo] = useState(false)
  // Dimensões nativas do quadro: sem elas as caixas de detecção (normalizadas
  // sobre o quadro) não podem ser projetadas no visor, que corta o vídeo.
  const [quadro, setQuadro] = useState({ largura: 0, altura: 0 })
  const [pausado, setPausado] = useState(false)
  const [etapas, setEtapas] = useState(ETAPAS_PADRAO)

  const videoRef = useRef(null); const trackRef = useRef(null); const streamRef = useRef(null)
  const leitorRef = useRef(null); const lacoRef = useRef(null); const ativoRef = useRef(false)
  const ultimaLeitura = useRef(0); const ultimoOcr = useRef(0); const ocrRodando = useRef(false)
  const ultimoCandidatoRef = useRef(null); const candidatoEstavelInicioRef = useRef(0); const ultimoFullScanRef = useRef(0)
  const pausadoRef = useRef(false); const passoPedidoRef = useRef(false)
  const caixasEstaveisRef = useRef([]); const ultimoRenderCaixasRef = useRef(0)
  // A janela anti-repetição vale para QUALQUER código entregue, não só ISBN: no
  // balcão o mesmo tombo fica parado na frente da câmera enquanto o operador
  // confere a tela, e sem isso ele seria emprestado dez vezes por segundo.
  const ultimoCodigoEntregue = useRef({ codigo: '', t: 0 })
  // Cada abertura de câmera tem sua geração: `abrirCamera` é assíncrono e a tela
  // pode desmontar (ou o StrictMode remontar) no meio. Sem isso, a abertura que
  // chega atrasada instala a si mesma sobre a atual e deixa um stream aceso.
  const geracaoRef = useRef(0)
  const etapasRef = useRef(ETAPAS_PADRAO); const maxCaixasRef = useRef(3)
  const desmonitorarQuadroRef = useRef(null)
  const aoLerRef = useRef(aoLer); aoLerRef.current = aoLer
  const aoDepurarRef = useRef(aoDepurar); aoDepurarRef.current = aoDepurar

  const anunciar = useCallback((texto, tom = '') => { setStatus(texto); setTomStatus(tom) }, [])

  // O quadro só tem tamanho depois que os metadados chegam, e ele muda quando o
  // aparelho gira ou a faixa renegocia resolução.
  const monitorarQuadro = useCallback((video) => {
    desmonitorarQuadroRef.current?.()
    if (!video) return
    const ler = () => setQuadro({ largura: video.videoWidth || 0, altura: video.videoHeight || 0 })
    ler()
    video.addEventListener('loadedmetadata', ler)
    video.addEventListener('resize', ler)
    desmonitorarQuadroRef.current = () => {
      video.removeEventListener('loadedmetadata', ler)
      video.removeEventListener('resize', ler)
      desmonitorarQuadroRef.current = null
    }
  }, [])

  // Um classificador só, com a forma que `scannerLoop` e `executarLeituraFoto` já
  // esperam (`{ tipo, codigo }`). No modo circulação ele é um adaptador de
  // `classificarCirculacao`, que devolve `{ tipo, valor }` — a assinatura combinada
  // no contrato do plano.
  const classificar = useMemo(() => {
    if (modo !== 'circulacao') return classificarCodigo
    return (texto) => {
      const { tipo, valor } = classificarCirculacao(texto)
      return { tipo, codigo: valor, valor }
    }
  }, [modo])

  const entregar = useCallback((texto, via) => {
    const { tipo, codigo } = classificar(texto)
    const aceitos = TIPOS_ACEITOS[modo] || TIPOS_ACEITOS.isbn
    if (aceitos.includes(tipo)) {
      ultimaLeitura.current = Date.now()
      const agora = Date.now()
      const ehRepetido =
        janelaRepeticao > 0 &&
        ultimoCodigoEntregue.current.codigo === codigo &&
        agora - ultimoCodigoEntregue.current.t < janelaRepeticao

      if (!ehRepetido) {
        ultimoCodigoEntregue.current = { codigo, t: agora }
        tocarBeepSucesso()
        vibrar()
        aoLerRef.current?.(codigo, { via, tipo, modo })
      }
      return true
    }
    if (tipo === 'ean') anunciar(`${codigo} não é ISBN — parece código de preço`, 'erro')
    // Na circulação o código de preço cai em 'desconhecido' junto com o resto: o
    // vocabulário do contrato não tem 'ean', e para o balcão a informação útil é a
    // mesma — isso não identifica exemplar nem leitor.
    else if (modo === 'circulacao' && codigo) {
      anunciar(`${codigo} não parece tombo, ISBN nem carteirinha`, 'erro')
    }
    return false
  }, [anunciar, classificar, janelaRepeticao, modo])

  const rodarLaco = useCallback((detector) => {
    iniciarLacoNativo({
      videoRef, detector, alvo: ALVO,
      refs: {
        ultimoCandidatoRef, candidatoEstavelInicioRef, ultimoFullScanRef, ultimaLeitura,
        pausadoRef, passoPedidoRef, etapasRef, maxCaixasRef,
        caixasEstaveisRef, ultimoRenderCaixasRef,
      },
      setDeteccoes, entregar, classificarCodigo: classificar, ativoRef, lacoRef,
      aoDiagnosticar: (registro) => aoDepurarRef.current?.(registro),
    })
  }, [classificar, entregar])

  const parar = useCallback(async () => {
    geracaoRef.current += 1
    ativoRef.current = false; clearTimeout(lacoRef.current); lacoRef.current = null
    leitorRef.current?.stop?.().catch(() => {})
    desmonitorarQuadroRef.current?.()
    fecharCamera(streamRef.current, videoRef.current, ELEMENTO)
    streamRef.current = null; videoRef.current = null; trackRef.current = null; leitorRef.current = null
    ultimoCandidatoRef.current = null
    pausadoRef.current = false; passoPedidoRef.current = false
    setEscaneando(false); setMotor(''); setRecursos({ lanterna: false, zoom: null })
    setLanternaLigada(false); setZoom(null); setDeteccoes([]); setPausado(false)
    setQuadro({ largura: 0, altura: 0 })
    anunciar('Câmera fechada')
  }, [anunciar])

  const iniciar = useCallback(async () => {
    if (ativoRef.current) return
    const geracao = geracaoRef.current + 1
    geracaoRef.current = geracao
    const minha = () => geracaoRef.current === geracao && ativoRef.current
    setErroCamera(''); ativoRef.current = true; anunciar('Abrindo a câmera…')
    try {
      const formatos = await formatosNativos(modo)
      if (formatos) {
        const { stream, video, track } = await abrirCamera(ELEMENTO)
        if (!minha()) { fecharCamera(stream, video, ELEMENTO); return }
        streamRef.current = stream; videoRef.current = video; trackRef.current = track
        const caps = await ajustarCamera(track)
        setRecursos(caps); setZoom(track.getSettings?.().zoom ?? caps.zoom?.min ?? null); setMotor(tipoMotor())
        monitorarQuadro(video)
        rodarLaco(criarDetectorNativo(formatos))
      } else {
        const { instancia, video } = await iniciarLeitorReserva(ELEMENTO, RESTRICOES_VIDEO, (t) => entregar(t, 'codigo'), modo)
        if (!minha()) { instancia?.stop?.().catch(() => {}); return }
        leitorRef.current = instancia; videoRef.current = video
        // O motor de reserva abre a câmera por dentro: a faixa é recuperada do
        // próprio <video> para que lanterna, zoom e foco também existam aqui.
        const track = obterTrackDoVideo(video)
        trackRef.current = track
        if (track) {
          const caps = await ajustarCamera(track)
          setRecursos(caps); setZoom(track.getSettings?.().zoom ?? caps.zoom?.min ?? null)
        }
        monitorarQuadro(video)
        setMotor('zxing')
      }
      if (!minha()) return
      setEscaneando(true)
      anunciar(modo === 'circulacao'
        ? 'Aponte para a etiqueta do exemplar'
        : 'Aponte para o código de barras')
    } catch (e) {
      parar(); setErroCamera(formatarErroCamera(e))
    }
  }, [anunciar, entregar, modo, monitorarQuadro, parar, rodarLaco])

  const tentarOcr = useCallback(() => {
    const video = videoRef.current || document.querySelector(`#${ELEMENTO} video`)
    if (!video?.videoWidth) {
      anunciar('Aguarde a câmera iniciar antes de ler os números', 'info')
      return
    }
    executarTentativaOcr({
      video,
      regiao: null,
      ocrRodandoRef: ocrRodando,
      ultimoOcrRef: ultimoOcr,
      setOcrAtivo,
      anunciar,
      entregar,
    })
  }, [anunciar, entregar])

  const alternarLanternaHook = useCallback(async () => {
    const track = trackRef.current || obterTrackDoVideo(videoRef.current)
    if (!track) {
      anunciar('Abra a câmera antes de acender a lanterna', 'info')
      return
    }
    trackRef.current = track
    const ok = await alternarLanterna(track, !lanternaLigada)
    if (ok) {
      setLanternaLigada((v) => !v)
      anunciar(lanternaLigada ? 'Lanterna apagada' : 'Lanterna acesa')
    } else {
      setLanternaLigada(false)
      anunciar('A lanterna não respondeu neste aparelho', 'erro')
    }
  }, [lanternaLigada, anunciar])

  const mudarZoomHook = useCallback((v) => { setZoom(v); aplicarZoom(trackRef.current, v) }, [])
  const dispararFocoHook = useCallback(() => dispararPulsoFoco(trackRef.current), [])

  // --- Controles de depuração (usados pela tela /scanner-debug) ---

  const alternarPausa = useCallback(() => {
    pausadoRef.current = !pausadoRef.current
    setPausado(pausadoRef.current)
    anunciar(pausadoRef.current ? 'Laço congelado' : 'Laço rodando')
  }, [anunciar])

  const pausar = useCallback((valor = true) => {
    pausadoRef.current = Boolean(valor)
    setPausado(Boolean(valor))
    anunciar(valor ? 'Laço congelado' : 'Laço rodando')
  }, [anunciar])

  const limparUltimoCodigo = useCallback(() => {
    ultimoCodigoEntregue.current = { codigo: '', t: 0 }
  }, [])
  /** Nome antigo, mantido porque `TelaDebugScanner.jsx` chama por ele. */
  const limparUltimoIsbn = limparUltimoCodigo

  const passoUnico = useCallback(() => { passoPedidoRef.current = true }, [])

  const definirEtapas = useCallback((mudanca) => {
    setEtapas((atual) => {
      const proximo = { ...atual, ...mudanca }
      etapasRef.current = proximo
      return proximo
    })
  }, [])

  const definirMaxCaixas = useCallback((n) => { maxCaixasRef.current = Math.max(1, Number(n) || 1) }, [])

  const lerArquivo = useCallback((arq) => {
    formatosNativos(modo).then((f) => executarLeituraFoto({
      arquivo: arq, formatos: f, anunciar, entregar, classificarCodigo: classificar,
    }))
  }, [anunciar, classificar, entregar, modo])

  useEffect(() => () => {
    ativoRef.current = false; clearTimeout(lacoRef.current)
    desmonitorarQuadroRef.current?.()
    fecharCamera(streamRef.current, videoRef.current, ELEMENTO)
    encerrarWorkerOcr()
  }, [])

  return {
    elementoId: ELEMENTO, modo, escaneando, status, tomStatus, erroCamera, motor,
    recursos, lanternaLigada, zoom, ocrAtivo, ocrAutoAtivo: false, deteccoes,
    quadro, alvo: ALVO, pausado, etapas,
    iniciar, parar, lerArquivo, tentarOcr, dispararFoco: dispararFocoHook,
    alternarLanterna: alternarLanternaHook, mudarZoom: mudarZoomHook, anunciar,
    alternarPausa, pausar, limparUltimoCodigo, limparUltimoIsbn, passoUnico,
    definirEtapas, definirMaxCaixas, classificar,
  }
}
