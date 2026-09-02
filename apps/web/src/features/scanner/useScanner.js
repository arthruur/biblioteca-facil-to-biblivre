/**
 * @fileoverview Hook React orquestrador do leitor de código de barras.
 *
 * PROPOSITO:
 * Centraliza o estado reativo da interface (status, erros, motor, recursos)
 * e conecta o ciclo de vida da câmera (`core/camera.js`), o laço nativo
 * (`core/scannerLoop.js`) e o fallback para OCR (`core/ocr.js`).
 *
 * INTERFACE:
 * - useScanner({ aoLer: Function, aoDepurar?: Function }): object
 *
 * FLUXO:
 * Consumido por `TelaCelular.jsx` (uso real) e por `TelaDebugScanner.jsx`
 * (depuração etapa por etapa). Orquestra módulos de `core/` e `utils/`.
 *
 * LIMITACOES:
 * Exige ambiente de navegador com suporte a getUserMedia e Canvas.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { tocarBeepSucesso, vibrar } from './core/audio.js'
import { abrirCamera, ajustarCamera, alternarLanterna, aplicarZoom, dispararPulsoFoco, fecharCamera, obterTrackDoVideo, RESTRICOES_VIDEO } from './core/camera.js'
import { criarDetectorNativo, executarLeituraFoto, formatosNativos, iniciarLeitorReserva } from './core/decodificador.js'
import { ALVO } from './core/geometria.js'
import { encerrarWorkerOcr, executarTentativaOcr } from './core/ocr.js'
import { ETAPAS_PADRAO, iniciarLacoNativo } from './core/scannerLoop.js'
import { classificarCodigo } from './isbn.js'
import { formatarErroCamera } from './utils/erros.js'

const ELEMENTO = 'visor-camera'

export function useScanner({ aoLer, aoDepurar } = {}) {
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

  const entregar = useCallback((texto, via) => {
    const { tipo, codigo } = classificarCodigo(texto)
    if (tipo === 'isbn') {
      ultimaLeitura.current = Date.now()
      tocarBeepSucesso(); vibrar(); aoLerRef.current?.(codigo, { via })
      return true
    }
    if (tipo === 'ean') anunciar(`${codigo} não é ISBN — parece código de preço`, 'erro')
    return false
  }, [anunciar])

  const rodarLaco = useCallback((detector) => {
    iniciarLacoNativo({
      videoRef, detector, alvo: ALVO,
      refs: {
        ultimoCandidatoRef, candidatoEstavelInicioRef, ultimoFullScanRef, ultimaLeitura,
        pausadoRef, passoPedidoRef, etapasRef, maxCaixasRef,
      },
      setDeteccoes, entregar, classificarCodigo, ativoRef, lacoRef,
      aoDiagnosticar: (registro) => aoDepurarRef.current?.(registro),
    })
  }, [entregar])

  const parar = useCallback(async () => {
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
    setErroCamera(''); ativoRef.current = true; anunciar('Abrindo a câmera…')
    try {
      const formatos = await formatosNativos()
      if (formatos) {
        const { stream, video, track } = await abrirCamera(ELEMENTO)
        streamRef.current = stream; videoRef.current = video; trackRef.current = track
        const caps = await ajustarCamera(track)
        setRecursos(caps); setZoom(track.getSettings?.().zoom ?? caps.zoom?.min ?? null); setMotor('nativo')
        monitorarQuadro(video)
        rodarLaco(criarDetectorNativo(formatos))
      } else {
        const { instancia, video } = await iniciarLeitorReserva(ELEMENTO, RESTRICOES_VIDEO, (t) => entregar(t, 'codigo'))
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
      setEscaneando(true); anunciar('Aponte para o código de barras')
    } catch (e) {
      parar(); setErroCamera(formatarErroCamera(e))
    }
  }, [anunciar, entregar, monitorarQuadro, parar, rodarLaco])

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
    formatosNativos().then((f) => executarLeituraFoto({ arquivo: arq, formatos: f, anunciar, entregar, classificarCodigo }))
  }, [anunciar, entregar])

  useEffect(() => () => {
    ativoRef.current = false; clearTimeout(lacoRef.current)
    desmonitorarQuadroRef.current?.()
    fecharCamera(streamRef.current, videoRef.current, ELEMENTO)
    encerrarWorkerOcr()
  }, [])

  return {
    elementoId: ELEMENTO, escaneando, status, tomStatus, erroCamera, motor,
    recursos, lanternaLigada, zoom, ocrAtivo, ocrAutoAtivo: false, deteccoes,
    quadro, alvo: ALVO, pausado, etapas,
    iniciar, parar, lerArquivo, tentarOcr, dispararFoco: dispararFocoHook,
    alternarLanterna: alternarLanternaHook, mudarZoom: mudarZoomHook, anunciar,
    alternarPausa, passoUnico, definirEtapas, definirMaxCaixas,
  }
}
