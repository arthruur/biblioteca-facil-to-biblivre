/**
 * @fileoverview Utilitário de formatação e tratamento de mensagens de erro da câmera.
 *
 * PROPOSITO:
 * Centraliza a tradução de exceções e erros de hardware da MediaDevices API
 * em mensagens em português claras, acionáveis e amigáveis para o usuário da biblioteca.
 *
 * INTERFACE:
 * - formatarErroCamera(erro: unknown): string
 *
 * FLUXO:
 * Invocado por `useScanner.js` quando a promessa de abertura da câmera falha
 * durante o `navigator.mediaDevices.getUserMedia`.
 *
 * LIMITACOES:
 * Depende das strings de mensagem padronizadas pelos navegadores (W3C Media Capture).
 * Erros proprietários não reconhecidos caem na mensagem genérica padrão.
 */

/**
 * Traduz erros técnicos de abertura de câmera para instruções amigáveis.
 *
 * @param {unknown} erro - Erro ou exceção capturada
 * @returns {string} Mensagem legível para exibição no visor
 */
export function formatarErroCamera(erro) {
  const msg = String(erro?.message || erro || '')

  if (/permission|denied|notallowed/i.test(msg)) {
    return 'A câmera foi bloqueada pelo navegador. Libere o acesso nas permissões do site e tente de novo.'
  }
  if (/notfound|devicesnotfound/i.test(msg)) {
    return 'Nenhuma câmera encontrada neste aparelho.'
  }
  if (/notreadable|trackstart/i.test(msg)) {
    return 'A câmera está ocupada por outro aplicativo. Feche-o e tente de novo.'
  }
  if (/overconstrained/i.test(msg)) {
    return 'A resolução solicitada não é suportada pela câmera deste aparelho.'
  }

  return `Não foi possível abrir a câmera: ${msg || 'erro desconhecido'}`
}
