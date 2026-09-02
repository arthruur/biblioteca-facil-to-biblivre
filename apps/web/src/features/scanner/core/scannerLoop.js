/**
 * @fileoverview Lógica e orquestração de um ciclo individual de varredura no vídeo.
 *
 * PROPOSITO:
 * Executa as duas fases de leitura (Fase 1: candidatos ROI ultraleve; Fase 2: decodificação
 * focada em alta resolução) e gerencia o ajuste dinâmico de taxa de quadros e salvaguarda.
 *
 * INTERFACE:
 * - INTERVALO_ATIVO: number (45ms)
 * - INTERVALO_OCIOSO: number (90ms)
 * - INTERVALO_PAUSA: number (450ms)
 * - ETAPAS_PADRAO: { candidatos: boolean, salvaguarda: boolean }
 * - executarPassoLeitura(ctx: object): Promise<{ proxima: number, leu: boolean }>
 * - iniciarLacoNativo(params: object): void
 *
 * FLUXO:
 * Invocado a cada iteração do laço nativo pelo hook `useScanner.js`.
 *
 * LIMITACOES:
 * Depende de elemento de vídeo com reprodução ativa (`readyState >= 2`).
 */

import { encontrarCandidatos, recortarRegiao } from './candidatos.js'
import { maiorArea, maiorDentroDoAlvo } from './geometria.js'

export const INTERVALO_ATIVO = 45
export const INTERVALO_OCIOSO = 90
export const INTERVALO_PAUSA = 450
const INTERVALO_CONGELADO = 200

/**
 * As duas etapas de busca podem ser desligadas em separado na tela de depuração:
 * com `candidatos: false` o laço só faz varredura de quadro cheio (é o teste que
 * responde "a heurística de ROI está atrapalhando?"); com `salvaguarda: false`
 * ele só confia no ROI.
 */
export const ETAPAS_PADRAO = Object.freeze({ candidatos: true, salvaguarda: true })

function criarRegistro(video, alvo) {
  return {
    t: Date.now(),
    fase: 'espera',
    videoW: video?.videoWidth || 0,
    videoH: video?.videoHeight || 0,
    readyState: video?.readyState ?? 0,
    candidatos: 0,
    densidade: 0,
    caixas: [],
    tentativas: 0,
    achados: 0,
    bruto: null,
    tipo: null,
    aceito: false,
    recorte: null,
    alvo,
    ms: 0,
  }
}

async function tentarDecodificarRecorte(video, regiao, detector, aoLerCodigo, agora, registro) {
  const recorte = recortarRegiao(video, regiao)
  if (!recorte) return false
  registro.tentativas += 1
  registro.recorte = recorte

  const achados = await detector.detect(recorte)
  registro.achados += achados?.length || 0
  if (!achados?.length) return false

  const escolhido = maiorArea(achados)
  if (!escolhido?.rawValue) return false
  registro.bruto = escolhido.rawValue

  return aoLerCodigo(escolhido.rawValue, regiao, agora)
}

function estabilizarCaixas(novas, anteriores) {
  if (!anteriores?.length || !novas?.length) return novas
  return novas.map((nova, i) => {
    const ant = anteriores[i]
    if (!ant) return nova
    const dx = Math.abs(nova.x - ant.x)
    const dy = Math.abs(nova.y - ant.y)
    const dw = Math.abs(nova.w - ant.w)
    const dh = Math.abs(nova.h - ant.h)
    // Se a variação for sutil (< 3%), aplica amortecimento (LERP) para eliminar tremor visual
    if (dx < 0.03 && dy < 0.03 && dw < 0.04 && dh < 0.04) {
      return {
        ...nova,
        x: ant.x * 0.65 + nova.x * 0.35,
        y: ant.y * 0.65 + nova.y * 0.35,
        w: ant.w * 0.65 + nova.w * 0.35,
        h: ant.h * 0.65 + nova.h * 0.35,
      }
    }
    return nova
  })
}

async function processarCandidatos({ video, detector, candidatos, ctx, agora, registro }) {
  const melhor = candidatos[0]
  ctx.ultimoCandidatoRef.current = melhor
  registro.fase = 'candidatos'
  registro.candidatos = candidatos.length
  registro.densidade = melhor?.densidade || 0

  const caixasBrutas = candidatos.slice(0, ctx.maxCaixas || 3).map((c, i) => ({
    x: c.x, y: c.y, w: c.largura, h: c.altura,
    dentroAlvo: c.dentroAlvo !== false, tipo: 'candidato', pulsando: true,
    miolo: c.mioloBarras, densidade: c.densidade, ordem: i,
    id: `cand-${i}`,
  }))

  const caixas = estabilizarCaixas(caixasBrutas, ctx.caixasEstaveisRef?.current)
  if (ctx.caixasEstaveisRef) ctx.caixasEstaveisRef.current = caixas
  registro.caixas = caixas

  // Rate limiter visual para evitar sobrecarga de renderização no React (~110ms)
  const agoraMs = performance.now()
  const ultimoRender = ctx.ultimoRenderCaixasRef?.current || 0
  if (agoraMs - ultimoRender > 110) {
    if (ctx.ultimoRenderCaixasRef) ctx.ultimoRenderCaixasRef.current = agoraMs
    ctx.aoAtualizarDeteccoes(caixas)
  }

  let leu = await tentarDecodificarRecorte(video, melhor, detector, ctx.aoLerCodigo, agora, registro)
  if (!leu && candidatos.length > 1) {
    leu = await tentarDecodificarRecorte(video, candidatos[1], detector, ctx.aoLerCodigo, agora, registro)
  }

  return { proxima: leu ? INTERVALO_PAUSA : INTERVALO_ATIVO, leu }
}

function extrairRegiao(item, videoW, videoH) {
  const b = item?.boundingBox
  if (b && b.width > 0) {
    return {
      x: b.x / videoW,
      y: b.y / videoH,
      largura: b.width / videoW,
      altura: b.height / videoH,
    }
  }
  const cp = item?.cornerPoints
  if (cp && cp.length >= 4) {
    const xs = cp.map((p) => p.x)
    const ys = cp.map((p) => p.y)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    return {
      x: minX / videoW,
      y: minY / videoH,
      largura: Math.max(0.1, (maxX - minX) / videoW),
      altura: Math.max(0.1, (maxY - minY) / videoH),
    }
  }
  return { x: 0.15, y: 0.35, largura: 0.70, altura: 0.30 }
}

async function executarSalvaguarda({ video, detector, alvo, ctx, agora, registro }) {
  registro.fase = 'salvaguarda'
  if (Date.now() - ctx.ultimoFullScanRef.current <= 150) {
    registro.fase = 'espera'
    return { proxima: INTERVALO_OCIOSO, leu: false }
  }
  ctx.ultimoFullScanRef.current = Date.now()
  registro.tentativas += 1
  const achados = await detector.detect(video)
  registro.achados += achados?.length || 0
  if (!achados?.length) return { proxima: INTERVALO_OCIOSO, leu: false }

  const escolhido = maiorDentroDoAlvo(achados, video.videoWidth, video.videoHeight, alvo)
  if (!escolhido?.rawValue) return { proxima: INTERVALO_OCIOSO, leu: false }
  registro.bruto = escolhido.rawValue

  const regiao = extrairRegiao(escolhido, video.videoWidth, video.videoHeight)
  const caixas = [{
    x: regiao.x, y: regiao.y, w: regiao.largura, h: regiao.altura,
    dentroAlvo: true, tipo: 'candidato', pulsando: true, raw: escolhido.rawValue,
    id: 'nativo-0',
  }]
  registro.caixas = caixas
  ctx.aoAtualizarDeteccoes(caixas)
  const leu = ctx.aoLerCodigo(escolhido.rawValue, regiao, agora)
  return { proxima: leu ? INTERVALO_PAUSA : INTERVALO_OCIOSO, leu }
}

/**
 * Executa um ciclo completo de detecção de candidatos, decodificação e salvaguarda.
 *
 * @param {object} ctx - Contexto com referências e callbacks do scanner
 * @returns {Promise<{ proxima: number, leu: boolean }>}
 */
export async function executarPassoLeitura(ctx) {
  const { video, detector, alvo } = ctx
  const etapas = ctx.etapas || ETAPAS_PADRAO
  const inicio = performance.now()
  const registro = criarRegistro(video, alvo)

  const emitir = (resultado) => {
    registro.ms = performance.now() - inicio
    registro.aceito = Boolean(resultado.leu)
    if (registro.bruto && ctx.classificar) {
      registro.tipo = ctx.classificar(registro.bruto)?.tipo || null
    }
    ctx.aoDiagnosticar?.(registro)
    return resultado
  }

  if (!video?.videoWidth || video.readyState < 2) {
    return emitir({ proxima: INTERVALO_OCIOSO, leu: false })
  }

  const candidatos = etapas.candidatos ? encontrarCandidatos(video, alvo) : []
  const agora = performance.now()

  if (candidatos.length > 0) {
    return emitir(await processarCandidatos({ video, detector, candidatos, ctx, agora, registro }))
  }

  ctx.ultimoCandidatoRef.current = null
  ctx.candidatoEstavelInicioRef.current = 0
  ctx.aoLimparDeteccoesDebounced()

  if (!etapas.salvaguarda) {
    return emitir({ proxima: INTERVALO_OCIOSO, leu: false })
  }

  return emitir(await executarSalvaguarda({ video, detector, alvo, ctx, agora, registro }))
}

/**
 * Inicia o laço contínuo de varredura nativa com agendamento via setTimeout.
 *
 * @param {object} params
 */
export function iniciarLacoNativo({
  videoRef,
  detector,
  alvo,
  refs,
  setDeteccoes,
  entregar,
  classificarCodigo,
  ativoRef,
  lacoRef,
  aoDiagnosticar,
}) {
  const passo = async () => {
    if (!ativoRef.current) return

    // Congelado: o laço continua vivo (a câmera não fecha) mas não gasta CPU
    // analisando quadro. Um "passo" pedido na tela de depuração destrava um
    // ciclo só, para inspecionar o recorte e os contadores sem o vídeo correndo.
    if (refs.pausadoRef?.current && !refs.passoPedidoRef?.current) {
      lacoRef.current = setTimeout(passo, INTERVALO_CONGELADO)
      return
    }
    if (refs.passoPedidoRef?.current) refs.passoPedidoRef.current = false

    const { proxima } = await executarPassoLeitura({
      video: videoRef.current,
      detector,
      alvo,
      etapas: refs.etapasRef?.current,
      maxCaixas: refs.maxCaixasRef?.current,
      classificar: classificarCodigo,
      aoDiagnosticar,
      ultimoCandidatoRef: refs.ultimoCandidatoRef,
      candidatoEstavelInicioRef: refs.candidatoEstavelInicioRef,
      ultimoFullScanRef: refs.ultimoFullScanRef,
      caixasEstaveisRef: refs.caixasEstaveisRef,
      ultimoRenderCaixasRef: refs.ultimoRenderCaixasRef,
      aoAtualizarDeteccoes: setDeteccoes,
      aoLimparDeteccoesDebounced: () =>
        setTimeout(() => {
          if (Date.now() - refs.ultimaLeitura.current > 450 && !refs.ultimoCandidatoRef.current) {
            if (refs.caixasEstaveisRef) refs.caixasEstaveisRef.current = []
            setDeteccoes([])
          }
        }, 350),
      aoLerCodigo: (raw, regiao, agora) => {
        const caixa = regiao || { x: 0.15, y: 0.35, largura: 0.70, altura: 0.30 }
        const { tipo } = classificarCodigo(raw)
        setDeteccoes([
          {
            x: caixa.x,
            y: caixa.y,
            w: caixa.largura,
            h: caixa.altura,
            dentroAlvo: true,
            tipo: tipo || 'isbn',
            pulsando: false,
            raw,
            id: 'codigo-lido',
          },
        ])
        if (!entregar(raw, 'codigo')) return false
        return true
      },
    })
    if (ativoRef.current) {
      lacoRef.current = setTimeout(passo, refs.pausadoRef?.current ? INTERVALO_CONGELADO : proxima)
    }
  }
  passo()
}
