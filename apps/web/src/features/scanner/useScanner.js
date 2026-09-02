import { useCallback, useEffect, useRef, useState } from 'react'
import { classificarCodigo } from './isbn'
import { encerrarOcr, lerNumerosDoVideo } from './ocrNumeros'

const ELEMENTO = 'visor-camera'

/**
 * Dois motores de leitura, e a razão de existirem os dois.
 *
 * O html5-qrcode decodifica num canvas do tamanho **em CSS px** do visor: ele
 * reduz o quadro nativo para ~330×150 antes de entregar ao ZXing (veja
 * `foreverScan`, em html5-qrcode.js). Um EAN-13 tem 95 módulos; se o código
 * ocupa metade da largura do visor, cada barra fica com menos de dois pixels e
 * nenhum decodificador fecha isso. Era esse o teto que fazia o scanner "não
 * pegar" mesmo com o livro bem enquadrado.
 *
 * Por isso o caminho principal aqui é nosso: `getUserMedia` + `BarcodeDetector`
 * lendo o elemento de vídeo em resolução nativa, sem canvas no meio. O
 * html5-qrcode fica como plano B onde não há `BarcodeDetector` — iOS Safari e
 * desktop — e lá o teto continua existindo, mas ao menos com foco contínuo e
 * enquadramento corretos.
 */
const FORMATOS_NATIVOS = [
  'ean_13',
  'ean_8',
  'upc_a',
  'upc_e',
  'code_128',
  'code_39',
]

/**
 * Resolução pedida à câmera.
 *
 * `ideal` e não `exact`: aparelho que não entrega 1080p devolve o que tem em
 * vez de estourar a abertura da câmera. Perder nitidez é ruim; não abrir a
 * câmera no meio de um lote é pior.
 */
const RESTRICOES_VIDEO = {
  facingMode: { ideal: 'environment' },
  width: { ideal: 1920 },
  height: { ideal: 1080 },
  frameRate: { ideal: 30 },
}

/**
 * Região do quadro onde um código é aceito, em fração do lado.
 *
 * Espelha a marcação desenhada no visor (`.visor__alvo`). Sem ela, escanear
 * uma estante pegaria o código do livro vizinho: o `BarcodeDetector` enxerga o
 * quadro inteiro, não só o que está dentro da moldura. A folga é generosa de
 * propósito — apertar demais devolve o problema de enquadramento que estamos
 * tentando resolver.
 */
const ALVO = { largura: 0.86, altura: 0.62 }

const INTERVALO_LEITURA = 60 // ~16 tentativas por segundo
const PAUSA_APOS_LEITURA = 900 // deixa o "Adicionado" parado na tela
const SEM_LEITURA_ATE_DICA = 3000
const SEM_LEITURA_ATE_OCR = 6000
const INTERVALO_ENTRE_OCR = 9000

let suporteNativo = null

/**
 * Formatos que o `BarcodeDetector` deste aparelho realmente decodifica.
 *
 * Consultamos `getSupportedFormats()` em vez de só testar `'BarcodeDetector' in
 * window`: no Chrome desktop a classe existe, o construtor funciona e
 * `detect()` nunca acha nada, porque o serviço de código de barras do sistema
 * não está lá. É a mesma armadilha em que o `isSupported()` do html5-qrcode
 * cai — e o motivo de o flag `useBarCodeDetectorIfSupported` dele não ser
 * confiável.
 */
function formatosNativos() {
  if (!suporteNativo) {
    suporteNativo = (async () => {
      if (typeof window === 'undefined' || !('BarcodeDetector' in window)) {
        return null
      }
      try {
        const disponiveis = await window.BarcodeDetector.getSupportedFormats()
        const uteis = FORMATOS_NATIVOS.filter((f) => disponiveis.includes(f))
        // Sem EAN-13 não vale a pena: é o formato da contracapa de todo livro.
        return uteis.includes('ean_13') ? uteis : null
      } catch {
        return null
      }
    })()
  }
  return suporteNativo
}

function maiorArea(codigos) {
  let escolhido = null
  let maior = -1
  for (const c of codigos || []) {
    const caixa = c.boundingBox
    const area = caixa ? caixa.width * caixa.height : 0
    if (area > maior) {
      maior = area
      escolhido = c
    }
  }
  return escolhido
}

function maiorDentroDoAlvo(codigos, largura, altura) {
  const dentro = (codigos || []).filter((c) => {
    const caixa = c.boundingBox
    if (!caixa) return true
    const cx = (caixa.x + caixa.width / 2) / largura
    const cy = (caixa.y + caixa.height / 2) / altura
    return (
      Math.abs(cx - 0.5) <= ALVO.largura / 2 &&
      Math.abs(cy - 0.5) <= ALVO.altura / 2
    )
  })
  return maiorArea(dentro)
}

/**
 * Foco contínuo e leitura das capacidades da câmera.
 *
 * Código de barras é foto macro: sem `focusMode: 'continuous'` o Android trava
 * o foco no infinito e a pessoa fica balançando o livro na frente de uma
 * câmera que nunca vai focar. Depois da resolução, este é o maior ganho de
 * reconhecimento do fluxo inteiro.
 */
async function ajustarCamera(track) {
  const caps = track.getCapabilities?.() ?? {}

  if (caps.focusMode?.includes('continuous')) {
    try {
      await track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] })
    } catch {
      /* aparelho que recusa: segue com o foco automático padrão */
    }
  }

  const zoom = caps.zoom
  return {
    lanterna: caps.torch === true,
    zoom:
      zoom && typeof zoom === 'object' && zoom.max > zoom.min
        ? { min: zoom.min, max: zoom.max, passo: zoom.step || 0.1 }
        : null,
  }
}

function mensagemDeErro(e) {
  const msg = String(e?.message || e)
  if (/permission|denied|notallowed/i.test(msg)) {
    return 'A câmera foi bloqueada pelo navegador. Libere o acesso nas permissões do site e tente de novo.'
  }
  if (/notfound|devicesnotfound/i.test(msg)) {
    return 'Nenhuma câmera encontrada neste aparelho.'
  }
  if (/notreadable|trackstart/i.test(msg)) {
    return 'A câmera está ocupada por outro aplicativo. Feche-o e tente de novo.'
  }
  return `Não foi possível abrir a câmera: ${msg}`
}

/**
 * Controla a câmera e entrega ISBNs decodificados.
 *
 * `aoLer` recebe o ISBN já validado. O hook não sabe nada de lote nem de API:
 * quem decide o que fazer com o número é a tela.
 */
export function useScanner({ aoLer }) {
  const [escaneando, setEscaneando] = useState(false)
  const [status, setStatus] = useState('')
  const [tomStatus, setTomStatus] = useState('')
  const [erroCamera, setErroCamera] = useState('')
  const [motor, setMotor] = useState('')
  const [recursos, setRecursos] = useState({ lanterna: false, zoom: null })
  const [lanternaLigada, setLanternaLigada] = useState(false)
  const [zoom, setZoom] = useState(null)

  const videoRef = useRef(null)
  const trackRef = useRef(null)
  const streamRef = useRef(null)
  const leitorRef = useRef(null)
  const lacoRef = useRef(null)
  const ativoRef = useRef(false)
  const ultimaLeitura = useRef(0)
  const ultimoAvisoEan = useRef(0)
  const ultimoOcr = useRef(0)
  const ocrRodando = useRef(false)
  const aoLerRef = useRef(aoLer)
  aoLerRef.current = aoLer

  const anunciar = useCallback((texto, tom = '') => {
    setStatus(texto)
    setTomStatus(tom)
  }, [])

  /**
   * Traduz o que o decodificador leu em ação da tela.
   *
   * Devolve `true` só quando era mesmo um ISBN. O caso `ean` é o do código de
   * preço colado ao lado do ISBN: dizer isso em voz alta é melhor do que ficar
   * mudo enquanto a pessoa insiste no código errado.
   */
  const entregar = useCallback(
    (texto, via) => {
      const { tipo, codigo } = classificarCodigo(texto)

      if (tipo === 'isbn') {
        ultimaLeitura.current = Date.now()
        aoLerRef.current?.(codigo, { via })
        return true
      }

      if (tipo === 'ean' && Date.now() - ultimoAvisoEan.current > 2500) {
        ultimoAvisoEan.current = Date.now()
        anunciar(`${codigo} não é ISBN — parece o código de preço. Use o de cima.`)
      }
      return false
    },
    [anunciar]
  )

  const tentarOcr = useCallback(async () => {
    if (ocrRodando.current) return
    const video = videoRef.current
    if (!video?.videoWidth) return

    ocrRodando.current = true
    ultimoOcr.current = Date.now()
    anunciar('Sem leitura pelas barras — lendo os números…')
    try {
      const isbn = await lerNumerosDoVideo(video)
      if (isbn) {
        anunciar(`Lido pelos números: ${isbn}`, 'ok')
        entregar(isbn, 'ocr')
      } else {
        anunciar('Não deu para ler os números — aproxime e segure firme')
      }
    } catch {
      // OCR é socorro, não caminho principal: falhar aqui não vira erro na tela.
      anunciar('Não deu para ler os números — aproxime e segure firme')
    } finally {
      ocrRodando.current = false
      ultimoOcr.current = Date.now()
    }
  }, [anunciar, entregar])

  // --- Motor nativo: BarcodeDetector sobre o vídeo, em resolução nativa ---

  const rodarLacoNativo = useCallback(
    (detector) => {
      const passo = async () => {
        if (!ativoRef.current) return
        const video = videoRef.current
        let proxima = INTERVALO_LEITURA

        if (video?.videoWidth && video.readyState >= 2) {
          try {
            const achados = await detector.detect(video)
            const alvo = maiorDentroDoAlvo(
              achados,
              video.videoWidth,
              video.videoHeight
            )
            if (alvo && entregar(alvo.rawValue, 'codigo')) {
              proxima = PAUSA_APOS_LEITURA
            }
          } catch {
            /* quadro ruim (troca de foco, buffer vazio): o próximo resolve */
          }
        }

        if (ativoRef.current) lacoRef.current = setTimeout(passo, proxima)
      }
      passo()
    },
    [entregar]
  )

  const iniciarNativo = useCallback(
    async (formatos) => {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: RESTRICOES_VIDEO,
      })
      streamRef.current = stream

      const video = document.createElement('video')
      video.autoplay = true
      video.muted = true
      video.playsInline = true
      // iOS só respeita o atributo, não a propriedade; sem ele o vídeo abre em
      // tela cheia no meio do lote.
      video.setAttribute('playsinline', 'true')
      video.setAttribute('muted', 'true')
      video.srcObject = stream

      document.getElementById(ELEMENTO)?.replaceChildren(video)
      videoRef.current = video
      await video.play()

      const track = stream.getVideoTracks()[0]
      trackRef.current = track
      const caps = await ajustarCamera(track)
      setRecursos(caps)
      setZoom(track.getSettings?.().zoom ?? caps.zoom?.min ?? null)
      setMotor('nativo')

      rodarLacoNativo(new window.BarcodeDetector({ formats: formatos }))
    },
    [rodarLacoNativo]
  )

  // --- Motor de reserva: html5-qrcode (iOS Safari, desktop) ---

  const iniciarReserva = useCallback(async () => {
    // Import dinâmico: no caminho nativo esta biblioteca nunca entra na rede.
    const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode')
    const formatos = [
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.UPC_E,
      Html5QrcodeSupportedFormats.CODE_128,
      Html5QrcodeSupportedFormats.CODE_39,
    ]

    const instancia = new Html5Qrcode(ELEMENTO, { formatsToSupport: formatos })
    leitorRef.current = instancia

    await instancia.start(
      { facingMode: 'environment' }, // ignorado: quem manda é videoConstraints
      {
        fps: 15,
        // Faixa 2,4:1, a proporção de um código de barras de livro. Sem
        // `aspectRatio`: forçar 1:1 recortava o sensor e jogava pixel fora.
        qrbox: (w, h) => {
          const largura = Math.floor(Math.min(w * 0.92, h * 2.4 * 0.92))
          return { width: largura, height: Math.floor(largura / 2.4) }
        },
        videoConstraints: RESTRICOES_VIDEO,
        // O BarcodeDetector aqui receberia o mesmo canvas reduzido que o ZXing
        // recebe — não ganharia nada. Quando ele existe, nem chegamos aqui.
        experimentalFeatures: { useBarCodeDetectorIfSupported: false },
        formatsToSupport: formatos,
      },
      (texto) => entregar(texto, 'codigo'),
      () => {}
    )

    const video = document.querySelector(`#${ELEMENTO} video`)
    videoRef.current = video
    const track = video?.srcObject?.getVideoTracks?.()[0] || null
    trackRef.current = track
    if (track) {
      const caps = await ajustarCamera(track)
      setRecursos(caps)
      setZoom(track.getSettings?.().zoom ?? caps.zoom?.min ?? null)
    }
    setMotor('zxing')
  }, [entregar])

  const iniciar = useCallback(async () => {
    if (ativoRef.current) return
    setErroCamera('')
    ativoRef.current = true
    ultimaLeitura.current = Date.now()
    ultimoOcr.current = Date.now()
    anunciar('Abrindo a câmera…')

    try {
      const formatos = await formatosNativos()
      if (formatos) await iniciarNativo(formatos)
      else await iniciarReserva()
      setEscaneando(true)
      anunciar('Aponte para o código de barras')
    } catch (e) {
      ativoRef.current = false
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      leitorRef.current = null
      videoRef.current = null
      trackRef.current = null
      setErroCamera(mensagemDeErro(e))
    }
  }, [anunciar, iniciarNativo, iniciarReserva])

  const parar = useCallback(async () => {
    ativoRef.current = false
    clearTimeout(lacoRef.current)
    lacoRef.current = null

    const leitor = leitorRef.current
    leitorRef.current = null
    if (leitor) {
      try {
        await leitor.stop()
        leitor.clear()
      } catch {
        /* já estava parado */
      }
    }

    // O html5-qrcode nem sempre solta a track; sem isto a luz da câmera fica
    // acesa e o celular esquenta no meio do turno.
    streamRef.current?.getTracks().forEach((t) => t.stop())
    const video = videoRef.current || document.querySelector(`#${ELEMENTO} video`)
    if (video?.srcObject) {
      video.srcObject.getTracks().forEach((t) => t.stop())
      video.srcObject = null
    }
    document.getElementById(ELEMENTO)?.replaceChildren()

    streamRef.current = null
    videoRef.current = null
    trackRef.current = null
    setEscaneando(false)
    setMotor('')
    setRecursos({ lanterna: false, zoom: null })
    setLanternaLigada(false)
    setZoom(null)
    anunciar('Câmera fechada')
  }, [anunciar])

  const alternarLanterna = useCallback(async () => {
    const track = trackRef.current
    if (!track) return
    const ligar = !lanternaLigada
    try {
      await track.applyConstraints({ advanced: [{ torch: ligar }] })
      setLanternaLigada(ligar)
    } catch {
      anunciar('A lanterna não respondeu neste aparelho')
    }
  }, [lanternaLigada, anunciar])

  const mudarZoom = useCallback(async (valor) => {
    const track = trackRef.current
    if (!track) return
    setZoom(valor)
    try {
      await track.applyConstraints({ advanced: [{ zoom: valor }] })
    } catch {
      /* fora de faixa: a próxima mudança corrige */
    }
  }, [])

  /** Decodifica uma foto do rolo da câmera (livro fora do alcance da luz). */
  const lerArquivo = useCallback(
    async (arquivo) => {
      anunciar('Lendo a foto…')

      const formatos = await formatosNativos()
      if (formatos) {
        try {
          const bitmap = await createImageBitmap(arquivo)
          const detector = new window.BarcodeDetector({ formats: formatos })
          const achados = await detector.detect(bitmap)
          bitmap.close?.()
          const escolhido = maiorArea(achados)
          if (escolhido && entregar(escolhido.rawValue, 'foto')) {
            anunciar(`Lido da foto: ${classificarCodigo(escolhido.rawValue).codigo}`, 'ok')
            return
          }
        } catch {
          /* cai para o leitor de arquivo do html5-qrcode */
        }
      }

      // Container fora da tela: usar o visor aqui derrubaria a câmera aberta.
      const caixa = document.createElement('div')
      caixa.id = `leitor-foto-${Date.now()}`
      caixa.style.cssText = 'position:fixed;left:-10000px;top:0;width:1px;height:1px'
      document.body.appendChild(caixa)

      const { Html5Qrcode } = await import('html5-qrcode')
      const instancia = new Html5Qrcode(caixa.id)
      try {
        const texto = await instancia.scanFile(arquivo, false)
        if (!entregar(texto, 'foto')) {
          anunciar('Nenhum ISBN encontrado na foto', 'erro')
          return
        }
        anunciar(`Lido da foto: ${classificarCodigo(texto).codigo}`, 'ok')
      } catch {
        anunciar('Nenhum código detectado — tente mais perto e com foco', 'erro')
      } finally {
        try {
          instancia.clear()
        } catch {
          /* nada a limpar */
        }
        caixa.remove()
      }
    },
    [anunciar, entregar]
  )

  /**
   * Vigia o silêncio: há quanto tempo nada é lido.
   *
   * O gatilho antigo era por contagem de quadros falhos (8), o que disparava o
   * OCR menos de um segundo depois de abrir a câmera — sempre, já que todo
   * quadro sem código conta como falha. A pessoa via "código danificado" antes
   * mesmo de terminar de enquadrar. Agora é por tempo, e a dica de
   * enquadramento vem antes de qualquer tentativa de OCR.
   */
  useEffect(() => {
    if (!escaneando) return undefined
    const id = setInterval(() => {
      if (ocrRodando.current) return
      const parado = Date.now() - ultimaLeitura.current
      if (parado < SEM_LEITURA_ATE_DICA) return

      if (parado < SEM_LEITURA_ATE_OCR) {
        anunciar(
          parado > 12000 && recursos.lanterna && !lanternaLigada
            ? 'Sem leitura — experimente ligar a lanterna'
            : 'Aproxime até o código preencher a marcação'
        )
      } else if (Date.now() - ultimoOcr.current > INTERVALO_ENTRE_OCR) {
        tentarOcr()
      }
    }, 700)
    return () => clearInterval(id)
  }, [escaneando, tentarOcr, anunciar, recursos.lanterna, lanternaLigada])

  // Sair da tela com a câmera aberta deixaria a track viva e o worker de OCR
  // ocupando memória. Aqui só se desliga hardware — nada de estado, o
  // componente já morreu.
  useEffect(
    () => () => {
      ativoRef.current = false
      clearTimeout(lacoRef.current)
      leitorRef.current?.stop?.().catch(() => {})
      streamRef.current?.getTracks().forEach((t) => t.stop())
      encerrarOcr()
    },
    []
  )

  return {
    elementoId: ELEMENTO,
    escaneando,
    status,
    tomStatus,
    erroCamera,
    motor,
    recursos,
    lanternaLigada,
    zoom,
    iniciar,
    parar,
    lerArquivo,
    alternarLanterna,
    mudarZoom,
    anunciar,
  }
}
