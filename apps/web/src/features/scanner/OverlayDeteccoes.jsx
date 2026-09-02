import { useEffect, useRef, useState } from 'react'
import { enquadrarCover } from './core/projecao.js'
import './overlay.css'

/**
 * A camada dos quadradinhos por cima da câmera.
 *
 * O scanner devolve as caixas normalizadas (0..1) sobre o quadro que a câmera
 * entrega — 1920×1080, por exemplo. O visor é um retângulo em pé e desenha esse
 * quadro com `object-fit: cover`: amplia até cobrir e corta as laterais. Por isso
 * a camada não pode ser simplesmente `inset: 0` com as caixas em porcentagem:
 * ela mede o visor, reconstrói o retângulo onde o vídeo realmente está (inclusive
 * a parte que sobra fora da tela) e põe as caixas em porcentagem *dele*. É a
 * diferença entre o quadradinho pousar em cima das barras e pousar dois dedos ao
 * lado.
 *
 * Em modo de depuração ela mostra também a mira do alvo, o miolo das barras que
 * a etapa de candidatos achou e a densidade de cada candidato — o suficiente
 * para ver, sem console, se a etapa 2 está enxergando o código.
 */
export function OverlayDeteccoes({
  deteccoes = [],
  quadro,
  alvo,
  depurando = false,
  dica = '',
}) {
  const ref = useRef(null)
  const [caixa, setCaixa] = useState({ largura: 0, altura: 0 })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const medir = () =>
      setCaixa({ largura: el.clientWidth, altura: el.clientHeight })
    medir()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', medir)
      return () => window.removeEventListener('resize', medir)
    }
    const observador = new ResizeObserver(medir)
    observador.observe(el)
    return () => observador.disconnect()
  }, [])

  const enq = enquadrarCover(
    quadro?.largura,
    quadro?.altura,
    caixa.largura,
    caixa.altura
  )

  const estiloQuadro = {
    left: `${enq.esquerda}px`,
    top: `${enq.topo}px`,
    width: `${enq.largura}px`,
    height: `${enq.altura}px`,
  }

  return (
    <div className="cel__overlay" ref={ref} aria-hidden="true">
      <div className="ov__quadro" style={estiloQuadro}>
        {depurando && alvo && (
          <div
            className="ov__alvo"
            style={{
              left: `${(0.5 - alvo.largura / 2) * 100}%`,
              top: `${(0.5 - alvo.altura / 2) * 100}%`,
              width: `${alvo.largura * 100}%`,
              height: `${alvo.altura * 100}%`,
            }}
          >
            <span className="ov__alvo-rotulo mono">alvo</span>
          </div>
        )}

        {deteccoes.map((d, i) => (
          <div
            key={d.id || `${d.raw}-${i}`}
            className={`cel__frame cel__frame--${d.tipo} ${d.dentroAlvo ? 'cel__frame--central' : ''} ${d.pulsando ? 'cel__frame--pulsando' : ''} ${depurando ? 'ov__frame--depuracao' : ''}`}
            style={{
              left: `${d.x * 100}%`,
              top: `${d.y * 100}%`,
              width: `${d.w * 100}%`,
              height: `${d.h * 100}%`,
            }}
          >
            <span className="cel__frame-canto cel__frame-canto--se" />
            <span className="cel__frame-canto cel__frame-canto--sd" />
            <span className="cel__frame-canto cel__frame-canto--ie" />
            <span className="cel__frame-canto cel__frame-canto--id" />

            {depurando && d.miolo && (
              <span
                className="ov__miolo"
                style={{
                  left: `${((d.miolo.x - d.x) / d.w) * 100}%`,
                  top: `${((d.miolo.y - d.y) / d.h) * 100}%`,
                  width: `${(d.miolo.largura / d.w) * 100}%`,
                  height: `${(d.miolo.altura / d.h) * 100}%`,
                }}
              />
            )}

            {d.raw ? (
              <span className="cel__frame-label mono">{d.raw.slice(-4)}</span>
            ) : depurando && d.densidade ? (
              <span className="cel__frame-label mono">
                #{(d.ordem ?? i) + 1} · d{Math.round(d.densidade)}
              </span>
            ) : null}
          </div>
        ))}
      </div>

      {dica && deteccoes.length === 0 && (
        <span className="cel__hint-discreto">{dica}</span>
      )}

      {depurando && (
        <span className="ov__medidas mono">
          {quadro?.largura || 0}×{quadro?.altura || 0} · visor{' '}
          {Math.round(caixa.largura)}×{Math.round(caixa.altura)} · escala{' '}
          {enq.escala.toFixed(2)}
        </span>
      )}
    </div>
  )
}
