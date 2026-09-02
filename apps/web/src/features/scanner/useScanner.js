/**
 * @fileoverview Hook React orquestrador do leitor de código de barras.
 *
 * PROPOSITO:
 * Centraliza o estado reativo da interface (status, erros, motor, recursos)
 * e conecta o ciclo de vida da câmera (`core/camera.js`), o laço nativo
 * (`core/scannerLoop.js`) e o fallback para OCR (`core/ocr.js`).
 *
 * INTERFACE:
 * - useScanner({ aoLer: Function }): object
 *
 * FLUXO:
 * Consumido por `TelaCelular.jsx`. Orquestra módulos de `core/` e `utils/`.
 *
 * LIMITACOES:
 * Exige ambiente de navegador com suporte a getUserMedia e Canvas.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { tocarBeepSucesso, vibrar } from './core/audio.js'
import { abrirCamera, ajustarCamera, alternarLanterna, aplicarZoom, dispararPulsoFoco, fecharCamera, RESTRICOES_VIDEO } from './core/camera.js'
import { criarDetectorNativo, executarLeituraFoto, formatosNativos, iniciarLeitorReserva } from './core/decodificador.js'
import { ALVO } from './core/geometria.js'
import { encerrarWorkerOcr, executarTentativaOcr } from './core/ocr.js'
import { iniciarLacoNativo } from './core/scannerLoop.js'
import { classificarCodigo } from './isbn.js'
import { formatarErroCamera } from './utils/erros.js'

const ELEMENTO = 'visor-camera'

export function useScanner({ aoLer }) {
  const [escaneando, setEscaneando] = useState(false)
  const [status, setStatus] = useState(''); const [tomStatus, setTomStatus] = useState('')
  const [erroCamera, setErroCamera] = useState(''); const [motor, setMotor] = useState('')
  const [recursos, setRecursos] = useState({ lanterna: false, zoom: null })
  const [lanternaLigada, setLanternaLigada] = useState(false); const [zoom, setZoom] = useState(null)
  const [deteccoes, setDeteccoes] = useState([]); const [ocrAtivo, setOcrAtivo] = useState(false)

  const videoRef = useRef(null); const trackRef = useRef(null); const streamRef = useRef(null)
  const leitorRef = useRef(null); const lacoRef = useRef(null); const ativoRef = useRef(false)
  const ultimaLeitura = useRef(0); const ultimoOcr = useRef(0); const ocrRodando = useRef(false)
  const ultimoCandidatoRef = useRef(null); const candidatoEstavelInicioRef = useRef(0); const ultimoFullScanRef = useRef(0)
  const aoLerRef = useRef(aoLer); aoLerRef.current = aoLer

  const anunciar = useCallback((texto, tom = '') => { setStatus(texto); setTomStatus(tom) }, [])

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
      refs: { ultimoCandidatoRef, candidatoEstavelInicioRef, ultimoFullScanRef, ultimaLeitura },
      setDeteccoes, entregar, classificarCodigo, ativoRef, lacoRef,
    })
  }, [entregar])

  const parar = useCallback(async () => {
    ativoRef.current = false; clearTimeout(lacoRef.current); lacoRef.current = null
    leitorRef.current?.stop?.().catch(() => {})
    fecharCamera(streamRef.current, videoRef.current, ELEMENTO)
    streamRef.current = null; videoRef.current = null; trackRef.current = null; leitorRef.current = null
    ultimoCandidatoRef.current = null
    setEscaneando(false); setMotor(''); setRecursos({ lanterna: false, zoom: null })
    setLanternaLigada(false); setZoom(null); setDeteccoes([])
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
        rodarLaco(criarDetectorNativo(formatos))
      } else {
        const { instancia, video } = await iniciarLeitorReserva(ELEMENTO, RESTRICOES_VIDEO, (t) => entregar(t, 'codigo'))
        leitorRef.current = instancia; videoRef.current = video
        setMotor('zxing')
      }
      setEscaneando(true); anunciar('Aponte para o código de barras')
    } catch (e) {
      parar(); setErroCamera(formatarErroCamera(e))
    }
  }, [anunciar, entregar, parar, rodarLaco])

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
    const ok = await alternarLanterna(trackRef.current, !lanternaLigada)
    if (ok) setLanternaLigada((v) => !v)
    else anunciar('A lanterna não respondeu neste aparelho')
  }, [lanternaLigada, anunciar])

  const mudarZoomHook = useCallback((v) => { setZoom(v); aplicarZoom(trackRef.current, v) }, [])
  const dispararFocoHook = useCallback(() => dispararPulsoFoco(trackRef.current), [])

  const lerArquivo = useCallback((arq) => {
    formatosNativos().then((f) => executarLeituraFoto({ arquivo: arq, formatos: f, anunciar, entregar, classificarCodigo }))
  }, [anunciar, entregar])

  useEffect(() => () => {
    ativoRef.current = false; clearTimeout(lacoRef.current)
    fecharCamera(streamRef.current, videoRef.current, ELEMENTO)
    encerrarWorkerOcr()
  }, [])

  return {
    elementoId: ELEMENTO, escaneando, status, tomStatus, erroCamera, motor,
    recursos, lanternaLigada, zoom, ocrAtivo, ocrAutoAtivo: false, deteccoes,
    iniciar, parar, lerArquivo, tentarOcr, dispararFoco: dispararFocoHook,
    alternarLanterna: alternarLanternaHook, mudarZoom: mudarZoomHook, anunciar,
  }
}
