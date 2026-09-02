/**
 * @fileoverview Projeção das caixas do quadro de vídeo para a área desenhada na tela.
 *
 * PROPOSITO:
 * O `<video>` do visor é desenhado com `object-fit: cover`: o quadro da câmera é
 * ampliado até cobrir a caixa e o excedente é cortado nas laterais (ou no topo e
 * na base). As coordenadas que o scanner produz são normalizadas (0..1) sobre o
 * quadro *inteiro* — inclusive a parte cortada. Desenhar essas coordenadas como
 * porcentagem do elemento coloca os quadradinhos no lugar errado, e quanto mais
 * diferente a proporção do vídeo é da do visor, mais longe do código de barras
 * eles caem. Este módulo faz a conversão.
 *
 * INTERFACE:
 * - enquadrarCover(videoW, videoH, caixaW, caixaH): { escala, largura, altura, esquerda, topo }
 *
 * FLUXO:
 * Usado por `OverlayDeteccoes.jsx`, que mede a caixa do visor, posiciona um
 * quadro do tamanho e no lugar exatos do vídeo desenhado e põe as caixas de
 * detecção como porcentagem *desse* quadro — não do visor.
 *
 * LIMITACOES:
 * Só cobre `object-fit: cover` centralizado (o único usado no visor).
 */

const VAZIO = Object.freeze({ escala: 1, largura: 0, altura: 0, esquerda: 0, topo: 0 })

/**
 * Calcula onde o quadro do vídeo é realmente desenhado dentro da caixa do visor.
 *
 * @param {number} videoW - Largura nativa do quadro
 * @param {number} videoH - Altura nativa do quadro
 * @param {number} caixaW - Largura do elemento na tela
 * @param {number} caixaH - Altura do elemento na tela
 * @returns {{ escala: number, largura: number, altura: number, esquerda: number, topo: number }}
 *   Medidas em pixels de tela; `esquerda`/`topo` são negativos quando há corte.
 */
export function enquadrarCover(videoW, videoH, caixaW, caixaH) {
  if (!(videoW > 0) || !(videoH > 0) || !(caixaW > 0) || !(caixaH > 0)) {
    return { ...VAZIO, largura: caixaW > 0 ? caixaW : 0, altura: caixaH > 0 ? caixaH : 0 }
  }

  const escala = Math.max(caixaW / videoW, caixaH / videoH)
  const largura = videoW * escala
  const altura = videoH * escala

  return {
    escala,
    largura,
    altura,
    esquerda: (caixaW - largura) / 2,
    topo: (caixaH - altura) / 2,
  }
}
