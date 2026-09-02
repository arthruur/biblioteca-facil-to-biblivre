/**
 * @fileoverview Acumulador puro das etapas do laço de leitura (telemetria do scanner).
 *
 * PROPOSITO:
 * O laço de leitura tem quatro etapas em sequência — quadro pronto, candidatos
 * (ROI), decodificação do recorte e salvaguarda de quadro cheio — e quando o
 * scanner "não lê" é preciso saber em qual delas ele para. Este módulo recebe um
 * evento por passo do laço e devolve o estado acumulado que a tela de depuração
 * mostra: contadores por etapa, taxa de quadros e o histórico dos últimos códigos
 * brutos com o veredito da classificação.
 *
 * INTERFACE:
 * - MAX_HISTORICO: number
 * - estadoInicial(): object
 * - acumular(estado, evento): object
 * - calcularFps(marcas: number[]): number
 * - diagnosticarEtapa(estado): string
 *
 * FLUXO:
 * `scannerLoop.js` emite o evento por `ctx.aoDiagnosticar`; `TelaDebugScanner.jsx`
 * acumula com `acumular` e desenha o resumo.
 *
 * LIMITACOES:
 * Puro e sem relógio próprio: o carimbo de tempo vem no evento (`t`).
 */

export const MAX_HISTORICO = 8
const MAX_MARCAS = 24

/**
 * Estado zerado dos contadores.
 *
 * @returns {object} Novo estado (nunca compartilhado entre instâncias)
 */
export function estadoInicial() {
  return {
    passos: 0,
    quadrosCrus: 0,
    comCandidatos: 0,
    semCandidatos: 0,
    salvaguardas: 0,
    tentativas: 0,
    achados: 0,
    decodificados: 0,
    aceitos: 0,
    rejeitados: 0,
    fase: 'parado',
    candidatos: 0,
    densidade: 0,
    videoW: 0,
    videoH: 0,
    readyState: 0,
    ms: 0,
    fps: 0,
    ultimoBruto: null,
    historico: [],
    marcas: [],
  }
}

/**
 * Calcula a taxa de passos por segundo a partir dos carimbos de tempo.
 *
 * @param {number[]} marcas - Carimbos em milissegundos, em ordem crescente
 * @returns {number} Passos por segundo (0 com menos de dois carimbos)
 */
export function calcularFps(marcas) {
  if (!Array.isArray(marcas) || marcas.length < 2) return 0
  const janela = marcas[marcas.length - 1] - marcas[0]
  if (!(janela > 0)) return 0
  return ((marcas.length - 1) * 1000) / janela
}

/**
 * Incorpora um passo do laço ao estado acumulado.
 *
 * @param {object} estado - Estado anterior (de `estadoInicial` ou `acumular`)
 * @param {object} evento - Registro do passo emitido por `scannerLoop.js`
 * @returns {object} Novo estado
 */
export function acumular(estado, evento) {
  if (!evento) return estado
  const base = estado || estadoInicial()
  const marcas = [...base.marcas, Number(evento.t) || 0].slice(-MAX_MARCAS)
  const leuAlgo = Boolean(evento.bruto)

  const historico = leuAlgo
    ? [
        {
          t: evento.t,
          bruto: evento.bruto,
          tipo: evento.tipo || 'desconhecido',
          aceito: Boolean(evento.aceito),
          fase: evento.fase,
        },
        ...base.historico,
      ].slice(0, MAX_HISTORICO)
    : base.historico

  return {
    ...base,
    passos: base.passos + 1,
    quadrosCrus: base.quadrosCrus + (evento.fase === 'espera' ? 1 : 0),
    comCandidatos: base.comCandidatos + (evento.candidatos > 0 ? 1 : 0),
    semCandidatos:
      base.semCandidatos + (evento.fase !== 'espera' && !evento.candidatos ? 1 : 0),
    salvaguardas: base.salvaguardas + (evento.fase === 'salvaguarda' ? 1 : 0),
    tentativas: base.tentativas + (Number(evento.tentativas) || 0),
    achados: base.achados + (Number(evento.achados) || 0),
    decodificados: base.decodificados + (leuAlgo ? 1 : 0),
    aceitos: base.aceitos + (evento.aceito ? 1 : 0),
    rejeitados: base.rejeitados + (leuAlgo && !evento.aceito ? 1 : 0),
    fase: evento.fase || base.fase,
    candidatos: Number(evento.candidatos) || 0,
    densidade: Number(evento.densidade) || 0,
    videoW: Number(evento.videoW) || 0,
    videoH: Number(evento.videoH) || 0,
    readyState: Number(evento.readyState) || 0,
    ms: Number(evento.ms) || 0,
    fps: calcularFps(marcas),
    ultimoBruto: leuAlgo ? evento.bruto : base.ultimoBruto,
    historico,
    marcas,
  }
}

/**
 * Traduz os contadores na primeira etapa que está travando a leitura.
 *
 * @param {object} estado - Estado acumulado
 * @returns {string} Frase curta apontando a etapa suspeita
 */
export function diagnosticarEtapa(estado) {
  const e = estado || estadoInicial()
  if (!e.passos) return 'Laço não rodou nenhum passo — a câmera está aberta?'
  if (!e.videoW) return 'O vídeo não entrega quadro (videoWidth = 0)'
  if (e.quadrosCrus === e.passos) return 'Vídeo sem readyState suficiente em todos os passos'
  if (!e.comCandidatos && !e.salvaguardas) return 'Nenhuma etapa de busca rodou'
  if (!e.comCandidatos) return 'A etapa 2 não acha candidatos — só a salvaguarda roda'
  if (!e.tentativas) return 'Candidatos achados, mas nenhum recorte foi decodificado'
  if (!e.decodificados) return 'A etapa 3 recorta e o decodificador não lê nada'
  if (!e.aceitos) return 'Códigos lidos, todos recusados na classificação (etapa 4)'
  return 'As quatro etapas fecharam ao menos uma vez'
}
