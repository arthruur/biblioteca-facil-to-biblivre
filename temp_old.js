import { useCallback, useEffect, useRef, useState } from 'react'
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode'

const ELEMENTO = 'visor-camera'

/** Formatos que um livro pode ter na contracapa. EAN-13 ├® o caso normal. */
const FORMATOS = [
  Html5QrcodeSupportedFormats.EAN_13,
  Html5QrcodeSupportedFormats.EAN_8,
  Html5QrcodeSupportedFormats.UPC_A,
  Html5QrcodeSupportedFormats.UPC_E,
  Html5QrcodeSupportedFormats.CODE_128,
  Html5QrcodeSupportedFormats.CODE_39,
]

/**
 * Quantas leituras falhas seguidas antes de tentar o OCR.
 *
 * O decodificador reporta falha a cada frame que n├úo tem c├│digo; 8 ├® o n├║mero
 * calibrado em campo: alto o bastante para n├úo disparar OCR enquanto a pessoa
 * ainda est├í enquadrando, baixo o bastante para socorrer um c├│digo riscado
 * antes de a pessoa desistir.
 */
const FALHAS_ATE_OCR = 8

export function ehIsbn(texto) {
  const limpo = String(texto || '').replace(/[\s-]/g, '')
  return /^\d{10}(\d{3})?$/.test(limpo) ? limpo : null
}

export function normalizarIsbnDigitado(texto) {
  const d = String(texto || '').replace(/[^0-9Xx]/g, '')
  if (d.length === 13) return /^\d{13}$/.test(d) ? d : null
  if (d.length === 10) return /^\d{9}[\dXx]$/.test(d) ? d : null
  return null
}

function digitoIsbn13Confere(isbn13) {
  let s = 0
  for (let i = 0; i < 12; i++) s += parseInt(isbn13[i], 10) * (i % 2 === 0 ? 1 : 3)
  return ((10 - (s % 10)) % 10) === parseInt(isbn13[12], 10)
}

/**
 * OCR de socorro sobre a faixa de n├║meros impressa abaixo do c├│digo de barras.
 *
 * Quando as barras est├úo riscadas ou amassadas o ZXing n├úo decodifica, mas os
 * d├¡gitos em OCR-B logo abaixo continuam leg├¡veis. Recortamos essa faixa,
 * ampliamos sem suaviza├º├úo (preservar a borda dura do glifo ├® o que faz o
 * Tesseract acertar) e binarizamos antes de reconhecer. O resultado s├│ ├®
 * aceito se o d├¡gito verificador do ISBN-13 fechar ÔÇö OCR erra, e um ISBN
 * errado catalogaria o livro errado.
 */
async function ocrDaFaixaDeNumeros(video) {
  const w = video.videoWidth
  const h = video.videoHeight
  if (!w) return null

  const quadro = document.createElement('canvas')
  quadro.width = w
  quadro.height = h
  quadro.getContext('2d').drawImage(video, 0, 0, w, h)

  const rw = Math.floor(w * 0.8)
  const rh = Math.floor(h * 0.18)
  const rx = Math.floor((w - rw) / 2)
  const ry = Math.floor(h * 0.68)

  const recorte = document.createElement('canvas')
  recorte.width = rw
  recorte.height = rh
  recorte.getContext('2d').drawImage(quadro, rx, ry, rw, rh, 0, 0, rw, rh)

  const ampliado = document.createElement('canvas')
  ampliado.width = rw * 2
  ampliado.height = rh * 2
  const ctx = ampliado.getContext('2d')
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(recorte, 0, 0, ampliado.width, ampliado.height)

  const img = ctx.getImageData(0, 0, ampliado.width, ampliado.height)
  for (let i = 0; i < img.data.length; i += 4) {
    const luz =
      0.299 * img.data[i] + 0.587 * img.data[i + 1] + 0.114 * img.data[i + 2]
    const bw = luz > 140 ? 255 : 0
    img.data[i] = img.data[i + 1] = img.data[i + 2] = bw
  }
  ctx.putImageData(img, 0, 0)

  // Import din├ómico: o Tesseract ├® pesado e a maioria dos lotes nunca precisa
  // dele. S├│ entra na rede quando o c├│digo de barras realmente falhou.
  const { default: Tesseract } = await import('tesseract.js')
  const {
    data: { text },
  } = await Tesseract.recognize(ampliado, 'eng', {
    tessedit_char_whitelist: '0123456789- ',
    tessedit_pageseg_mode: '7',
  })

  const achado = text.replace(/[^0-9]/g, '').match(/\d{13}/)
  return achado && digitoIsbn13Confere(achado[0]) ? achado[0] : null
}

/**
 * Controla a c├ómera e entrega ISBNs decodificados.
 *
 * `aoLer` recebe o ISBN limpo. O hook n├úo sabe nada de lote nem de API: quem
 * decide o que fazer com o n├║mero ├® a tela.
 */
export function useScanner({ aoLer }) {
  const [escaneando, setEscaneando] = useState(false)
  const [status, setStatus] = useState('')
  const [tomStatus, setTomStatus] = useState('')
  const [erroCamera, setErroCamera] = useState('')

  const leitor = useRef(null)
  const falhas = useRef(0)
  const ocrRodando = useRef(false)
  const aoLerRef = useRef(aoLer)
  aoLerRef.current = aoLer

  const anunciar = useCallback((texto, tom = '') => {
    setStatus(texto)
    setTomStatus(tom)
  }, [])

  const tentarOcr = useCallback(async () => {
    if (ocrRodando.current) return
    const video = document.querySelector(`#${ELEMENTO} video`)
    if (!video || !video.videoWidth) return

    ocrRodando.current = true
    anunciar('C├│digo danificado ÔÇö lendo os n├║merosÔÇª')
    try {
      const isbn = await ocrDaFaixaDeNumeros(video)
      if (isbn) {
        anunciar(`Lido pelos n├║meros: ${isbn}`, 'ok')
        falhas.current = 0
        aoLerRef.current?.(isbn, { via: 'ocr' })
      } else {
        anunciar('N├úo deu para ler ÔÇö aproxime e foque nos n├║meros')
      }
    } catch {
      // OCR ├® socorro, n├úo caminho principal: falhar aqui ├® silencioso.
    } finally {
      ocrRodando.current = false
    }
  }, [anunciar])

  const iniciar = useCallback(async () => {
    if (escaneando) return
    setErroCamera('')
    const instancia = new Html5Qrcode(ELEMENTO, { formatsToSupport: FORMATOS })
    leitor.current = instancia
    falhas.current = 0
    anunciar('Procurando c├│digo de barrasÔÇª')

    try {
      await instancia.start(
        { facingMode: 'environment' },
        {
          fps: 10,
          // Faixa larga e baixa: ├® a propor├º├úo de um c├│digo de barras de livro,
          // e enquadrar assim evita que o leitor gaste tempo no resto da capa.
          qrbox: (w, h) => {
            const m = Math.min(w, h)
            return { width: Math.floor(m * 0.85), height: Math.floor(m * 0.4) }
          },
          aspectRatio: 1.0,
          // O BarcodeDetector nativo perde c├│digos que o ZXing pega em papel
          // fosco e sob luz fraca de estante.
          experimentalFeatures: { useBarCodeDetectorIfSupported: false },
          formatsToSupport: FORMATOS,
        },
        (texto) => {
          falhas.current = 0
          const isbn = ehIsbn(texto)
          if (isbn) aoLerRef.current?.(isbn, { via: 'codigo' })
        },
        () => {
          falhas.current += 1
          if (falhas.current > FALHAS_ATE_OCR && !ocrRodando.current) {
            falhas.current = 0
            tentarOcr()
          }
        }
      )
      setEscaneando(true)
    } catch (e) {
      const msg = String(e?.message || e)
      setErroCamera(
        /permission|denied|notallowed/i.test(msg)
          ? 'A c├ómera foi bloqueada pelo navegador. Libere o acesso nas permiss├Áes do site e tente de novo.'
          : `N├úo foi poss├¡vel abrir a c├ómera: ${msg}`
      )
      leitor.current = null
    }
  }, [escaneando, anunciar, tentarOcr])

  const parar = useCallback(async () => {
    const instancia = leitor.current
    if (!instancia) return
    try {
      await instancia.stop()
      instancia.clear()
    } catch {
      /* j├í estava parado */
    }
    // O html5-qrcode nem sempre solta a track; sem isto a luz da c├ómera fica
    // acesa e o celular esquenta no meio do turno.
    const video = document.querySelector(`#${ELEMENTO} video`)
    if (video?.srcObject) {
      video.srcObject.getTracks().forEach((t) => t.stop())
      video.srcObject = null
    }
    leitor.current = null
    setEscaneando(false)
    anunciar('C├ómera fechada')
  }, [anunciar])

  /** Decodifica uma foto do rolo da c├ómera (livro fora do alcance da luz). */
  const lerArquivo = useCallback(
    async (arquivo) => {
      anunciar('Lendo a fotoÔÇª')
      const instancia = new Html5Qrcode(ELEMENTO, { formatsToSupport: FORMATOS })
      try {
        const texto = await instancia.scanFile(arquivo, true)
        const isbn = ehIsbn(texto)
        if (!isbn) {
          anunciar('Nenhum ISBN encontrado na foto', 'erro')
          return
        }
        anunciar(`Lido da foto: ${isbn}`, 'ok')
        aoLerRef.current?.(isbn, { via: 'foto' })
      } catch {
        anunciar('Nenhum c├│digo detectado ÔÇö tente mais perto e com foco', 'erro')
      } finally {
        try {
          instancia.clear()
        } catch {
          /* nada a limpar */
        }
      }
    },
    [anunciar]
  )

  // Sair da tela com a c├ómera aberta deixaria a track viva.
  useEffect(() => () => {
    leitor.current?.stop?.().catch(() => {})
  }, [])

  return {
    elementoId: ELEMENTO,
    escaneando,
    status,
    tomStatus,
    erroCamera,
    iniciar,
    parar,
    lerArquivo,
    anunciar,
  }
}
