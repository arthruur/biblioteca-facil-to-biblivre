import { useEffect, useRef } from 'react'
import './componentes.css'

const juntar = (...cls) => cls.filter(Boolean).join(' ')

/* --- Ícones SVG limpos e modernos --- */

export function IconeScanner({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 7V5a2 2 0 0 1 2-2h2" />
      <path d="M17 3h2a2 2 0 0 1 2 2v2" />
      <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
      <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
      <line x1="7" y1="12" x2="17" y2="12" />
      <line x1="7" y1="8" x2="17" y2="8" />
      <line x1="7" y1="16" x2="17" y2="16" />
    </svg>
  )
}

export function IconeFila({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}

export function IconeExportar({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}

export function IconeBanco({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  )
}

export function IconeRecarregar({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  )
}

export function IconeBuscar({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

export function IconeEditar({ tamanho = 16, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

export function IconeRemover({ tamanho = 16, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

export function IconeCheck({ tamanho = 16, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

export function IconePendente({ tamanho = 16, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  )
}

export function IconeLivro({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

export function IconeFoto({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}

export function IconeLanterna({ tamanho = 18, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

export function IconeCopiar({ tamanho = 16, className = '' }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

/* --- Componentes Básicos --- */

export function Botao({
  variante = 'secundario',
  tamanho,
  bloco,
  className,
  children,
  icone,
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
      {icone && <span className="btn__icone" aria-hidden="true">{icone}</span>}
      {children}
    </button>
  )
}

export function Selo({ tom = 'neutro', children, className = '', ...resto }) {
  return (
    <span className={juntar('selo', `selo--${tom}`, className)} {...resto}>
      {children}
    </span>
  )
}

export function Pilula({ tom, children, className = '', ...resto }) {
  const Elemento = resto.onClick ? 'button' : 'span'
  return (
    <Elemento className={juntar('pilula', tom && `pilula--${tom}`, className)} {...resto}>
      <span className="pilula__ponto" aria-hidden="true" />
      <span className="pilula__texto">{children}</span>
    </Elemento>
  )
}

export function Aviso({ tom, icone, titulo, children, className = '' }) {
  return (
    <div className={juntar('aviso', tom && `aviso--${tom}`, className)} role="status">
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
 * Modal acessível com Escape, fechamento suave e trava de foco.
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
          <button className="modal__fechar" onClick={aoFechar} aria-label="Fechar modal">
            ✕
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
        type="button"
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
        type="button"
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
      {acao && <div className="vazio__acao">{acao}</div>}
    </div>
  )
}

/* --- Navegação e App Shell --- */

export function Navbar({
  rotaAtiva,
  aoNavegar,
  loteQtd = 0,
  filaQtd = 0,
  conexao,
  aoAbrirBanco,
  aoAbrirExport,
  aoReconsultar,
  reconsultando = false,
}) {
  return (
    <header className="app-nav">
      <div className="app-nav__esquerda">
        <button
          className="app-nav__marca"
          onClick={() => aoNavegar('escanear')}
          title="Ir para o scanner"
        >
          <div className="app-nav__logo" aria-hidden="true">
            <IconeLivro tamanho={20} />
          </div>
          <div className="app-nav__titulos">
            <span className="app-nav__nome">BiblioFácil</span>
            <span className="app-nav__sub">BibLivre 5</span>
          </div>
        </button>
      </div>

      <nav className="app-nav__centro" aria-label="Navegação principal">
        <button
          className={juntar('app-nav__item', rotaAtiva === 'escanear' && 'app-nav__item--ativo')}
          onClick={() => aoNavegar('escanear')}
          aria-current={rotaAtiva === 'escanear' ? 'page' : undefined}
        >
          <IconeScanner tamanho={17} />
          <span>Escanear</span>
          {loteQtd > 0 && <span className="badge-lote">{loteQtd}</span>}
        </button>

        <button
          className={juntar('app-nav__item', rotaAtiva === 'fila' && 'app-nav__item--ativo')}
          onClick={() => aoNavegar('fila')}
          aria-current={rotaAtiva === 'fila' ? 'page' : undefined}
        >
          <IconeFila tamanho={17} />
          <span>Fila de Revisão</span>
          {filaQtd > 0 && <span className="badge-fila">{filaQtd}</span>}
        </button>

        <button
          className="app-nav__item app-nav__item--export"
          onClick={aoAbrirExport}
          title="Abrir diálogo de exportação para o BibLivre"
        >
          <IconeExportar tamanho={17} />
          <span>Exportar</span>
        </button>
      </nav>

      <div className="app-nav__direita">
        {conexao && (
          <Pilula
            tom={conexao.tom}
            onClick={aoAbrirBanco}
            title={conexao.detalhe || 'Configurar conexão com o PostgreSQL do BibLivre'}
          >
            {conexao.rotulo}
          </Pilula>
        )}

        {conexao?.conectado && (
          <button
            className="btn-icone-nav"
            onClick={aoReconsultar}
            disabled={reconsultando}
            title="Revarrer acervo e reavaliar a fila"
            aria-label="Revarrer acervo e reavaliar fila"
          >
            <IconeRecarregar
              tamanho={16}
              className={reconsultando ? 'animacao-girar' : ''}
            />
          </button>
        )}
      </div>
    </header>
  )
}

export function BottomNav({
  rotaAtiva,
  aoNavegar,
  loteQtd = 0,
  filaQtd = 0,
  aoAbrirExport,
  aoAbrirBanco,
  conexao,
}) {
  return (
    <nav className="bottom-nav" aria-label="Navegação móvel">
      <button
        className={juntar('bottom-nav__item', rotaAtiva === 'escanear' && 'bottom-nav__item--ativo')}
        onClick={() => aoNavegar('escanear')}
        aria-current={rotaAtiva === 'escanear' ? 'page' : undefined}
      >
        <div className="bottom-nav__icone-wrap">
          <IconeScanner tamanho={22} />
          {loteQtd > 0 && <span className="bottom-nav__badge">{loteQtd}</span>}
        </div>
        <span>Escanear</span>
      </button>

      <button
        className={juntar('bottom-nav__item', rotaAtiva === 'fila' && 'bottom-nav__item--ativo')}
        onClick={() => aoNavegar('fila')}
        aria-current={rotaAtiva === 'fila' ? 'page' : undefined}
      >
        <div className="bottom-nav__icone-wrap">
          <IconeFila tamanho={22} />
          {filaQtd > 0 && <span className="bottom-nav__badge">{filaQtd}</span>}
        </div>
        <span>Fila</span>
      </button>

      <button
        className="bottom-nav__item"
        onClick={aoAbrirExport}
        aria-label="Exportar para o BibLivre"
      >
        <div className="bottom-nav__icone-wrap">
          <IconeExportar tamanho={22} />
        </div>
        <span>Exportar</span>
      </button>

      <button
        className={juntar(
          'bottom-nav__item',
          conexao?.conectado ? 'bottom-nav__item--db-ok' : 'bottom-nav__item--db-alerta'
        )}
        onClick={aoAbrirBanco}
        aria-label="Status do banco de dados BibLivre"
      >
        <div className="bottom-nav__icone-wrap">
          <IconeBanco tamanho={22} />
          <span
            className={juntar(
              'bottom-nav__ponto-status',
              conexao?.conectado ? 'bottom-nav__ponto--ok' : 'bottom-nav__ponto--alerta'
            )}
          />
        </div>
        <span>BibLivre</span>
      </button>
    </nav>
  )
}
