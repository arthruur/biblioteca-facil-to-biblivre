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
 * - executarPassoLeitura(ctx: object): Promise<{ proxima: number, leu: boolean }>
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
const INTERVALO_SALVAGUARDA = 450

async function tentarDecodificarRecorte(video, regiao, detector, aoLerCodigo, agora) {
  const recorte = recortarRegiao(video, regiao)
  if (!recorte) return false

  const achados = await detector.detect(recorte)
  if (!achados?.length) return false

  const escolhido = maiorArea(achados)
  if (!escolhido?.rawValue) return false

  return aoLerCodigo(escolhido.rawValue, regiao, agora)
}

async function processarCandidatos({ video, detector, candidatos, ctx, agora }) {
  const melhor = candidatos[0]
  ctx.ultimoCandidatoRef.current = melhor

  ctx.aoAtualizarDeteccoes(
    candidatos.slice(0, 3).map((c, i) => ({
      x: c.x, y: c.y, w: c.largura, h: c.altura,
      dentroAlvo: true, tipo: 'candidato', pulsando: true,
      id: `cand-${i}`,
    }))
  )

  let leu = await tentarDecodificarRecorte(video, melhor, detector, ctx.aoLerCodigo, agora)
  if (!leu && candidatos.length > 1) {
    leu = await tentarDecodificarRecorte(video, candidatos[1], detector, ctx.aoLerCodigo, agora)
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

async function executarSalvaguarda({ video, detector, alvo, ctx, agora }) {
  if (Date.now() - ctx.ultimoFullScanRef.current <= 150) {
    return { proxima: INTERVALO_OCIOSO, leu: false }
  }
  ctx.ultimoFullScanRef.current = Date.now()
  const achados = await detector.detect(video)
  if (!achados?.length) return { proxima: INTERVALO_OCIOSO, leu: false }

  const escolhido = maiorDentroDoAlvo(achados, video.videoWidth, video.videoHeight, alvo)
  if (!escolhido?.rawValue) return { proxima: INTERVALO_OCIOSO, leu: false }

  const regiao = extrairRegiao(escolhido, video.videoWidth, video.videoHeight)
  ctx.aoAtualizarDeteccoes([{
    x: regiao.x, y: regiao.y, w: regiao.largura, h: regiao.altura,
    dentroAlvo: true, tipo: 'candidato', pulsando: true, raw: escolhido.rawValue,
    id: 'nativo-0',
  }])
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
  if (!video?.videoWidth || video.readyState < 2) {
    return { proxima: INTERVALO_OCIOSO, leu: false }
  }

  const candidatos = encontrarCandidatos(video, alvo)
  const agora = performance.now()

  if (candidatos.length > 0) {
    return processarCandidatos({ video, detector, candidatos, ctx, agora })
  }

  ctx.ultimoCandidatoRef.current = null
  ctx.candidatoEstavelInicioRef.current = 0
  ctx.aoLimparDeteccoesDebounced()

  return executarSalvaguarda({ video, detector, alvo, ctx, agora })
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
}) {
  const passo = async () => {
    if (!ativoRef.current) return
    const { proxima } = await executarPassoLeitura({
      video: videoRef.current,
      detector,
      alvo,
      ultimoCandidatoRef: refs.ultimoCandidatoRef,
      candidatoEstavelInicioRef: refs.candidatoEstavelInicioRef,
      ultimoFullScanRef: refs.ultimoFullScanRef,
      aoAtualizarDeteccoes: setDeteccoes,
      aoLimparDeteccoesDebounced: () =>
        setTimeout(() => {
          if (Date.now() - refs.ultimaLeitura.current > 450 && !refs.ultimoCandidatoRef.current) {
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
    if (ativoRef.current) lacoRef.current = setTimeout(passo, proxima)
  }
  passo()
}

