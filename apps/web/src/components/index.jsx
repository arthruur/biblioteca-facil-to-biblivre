import { useEffect, useRef } from 'react'
import './componentes.css'

const juntar = (...cls) => cls.filter(Boolean).join(' ')

export function Botao({
  variante = 'secundario',
  tamanho,
  bloco,
  className,
  children,
  ...resto
}) {
  return (
    <button
      className={juntar(
        'btn',
        `btn--${variante}`,
        tamanho && `btn--${tamanho}`,
        bloco && 'btn--bloco',
        className
      )}
      {...resto}
    >
      {children}
    </button>
  )
}

export function Selo({ tom = 'neutro', children, ...resto }) {
  return (
    <span className={juntar('selo', `selo--${tom}`)} {...resto}>
      {children}
    </span>
  )
}

export function Pilula({ tom, children, ...resto }) {
  const Elemento = resto.onClick ? 'button' : 'span'
  return (
    <Elemento className={juntar('pilula', tom && `pilula--${tom}`)} {...resto}>
      <span className="pilula__ponto" aria-hidden="true" />
      {children}
    </Elemento>
  )
}

export function Aviso({ tom, icone, titulo, children }) {
  return (
    <div className={juntar('aviso', tom && `aviso--${tom}`)} role="status">
      {icone && (
        <span className="aviso__icone" aria-hidden="true">
          {icone}
        </span>
      )}
      <div className="aviso__corpo">
        {titulo && <strong>{titulo}</strong>}
        {children}
      </div>
    </div>
  )
}

/**
 * Modal com as garantias de acessibilidade que a spec pede: `Esc` fecha,
 * o foco volta para quem abriu, e clique fora fecha (menos quando a ação é
 * destrutiva — aí o fechamento acidental custaria caro).
 */
export function Modal({
  titulo,
  aoFechar,
  largo,
  rodape,
  children,
  fecharNoFundo = true,
}) {
  const anterior = useRef(null)
  const caixa = useRef(null)

  useEffect(() => {
    anterior.current = document.activeElement
    const aoTeclar = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        aoFechar()
      }
    }
    document.addEventListener('keydown', aoTeclar)
    caixa.current?.focus()
    return () => {
      document.removeEventListener('keydown', aoTeclar)
      anterior.current?.focus?.()
    }
  }, [aoFechar])

  return (
    <div
      className="modal-fundo"
      onMouseDown={(e) => {
        if (fecharNoFundo && e.target === e.currentTarget) aoFechar()
      }}
    >
      <div
        className={juntar('modal', largo && 'modal--largo')}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        tabIndex={-1}
        ref={caixa}
      >
        <header className="modal__cabecalho">
          <h2 className="modal__titulo">{titulo}</h2>
          <button className="modal__fechar" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
        </header>
        <div className="modal__corpo">{children}</div>
        {rodape && <footer className="modal__rodape">{rodape}</footer>}
      </div>
    </div>
  )
}

export function Stepper({ valor, aoMudar, min = 1, max = 999, grande, rotulo }) {
  const n = Number(valor) || min
  return (
    <div
      className={juntar('stepper', grande && 'stepper--grande')}
      role="group"
      aria-label={rotulo || 'Quantidade de exemplares'}
    >
      <button
        className="stepper__btn"
        onClick={() => aoMudar(Math.max(min, n - 1))}
        disabled={n <= min}
        aria-label="Um exemplar a menos"
      >
        −
      </button>
      <span className="stepper__valor" aria-live="polite">
        {n}
      </span>
      <button
        className="stepper__btn"
        onClick={() => aoMudar(Math.min(max, n + 1))}
        disabled={n >= max}
        aria-label="Um exemplar a mais"
      >
        +
      </button>
    </div>
  )
}

export function Campo({ rotulo, ajuda, largo, ...resto }) {
  return (
    <label className={juntar('campo', largo && 'campo--largo')}>
      <span className="campo__rotulo">{rotulo}</span>
      <input className="campo__entrada" {...resto} />
      {ajuda && <span className="campo__ajuda">{ajuda}</span>}
    </label>
  )
}

export function EstadoVazio({ icone, titulo, children, acao }) {
  return (
    <div className="vazio">
      {icone && (
        <span className="vazio__icone" aria-hidden="true">
          {icone}
        </span>
      )}
      <p className="vazio__titulo">{titulo}</p>
      {children && <p className="vazio__texto">{children}</p>}
      {acao}
    </div>
  )
}
