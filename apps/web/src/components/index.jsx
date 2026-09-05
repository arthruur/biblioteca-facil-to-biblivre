import { useEffect, useRef } from 'react'
import './componentes.css'

const juntar = (...cls) => cls.filter(Boolean).join(' ')

/* --- Moldura de prancheta --- */

/**
 * As quatro marcas de registro de um bloco.
 *
 * Ficam fora da caixa, então quem as usa precisa ser `position: relative` e
 * não pode ter `overflow: hidden` — daí existirem separadas de `Moldura`: um
 * botão já é relativo por conta própria e só precisa das marcas.
 */
export function Cantos() {
  return (
    <>
      <span className="moldura__canto moldura__canto--se" aria-hidden="true" />
      <span className="moldura__canto moldura__canto--sd" aria-hidden="true" />
      <span className="moldura__canto moldura__canto--ie" aria-hidden="true" />
      <span className="moldura__canto moldura__canto--id" aria-hidden="true" />
    </>
  )
}

/** Bloco de prancheta: contorno de fio + marcas de registro nos cantos. */
export function Moldura({ como: Como = 'div', className, children, ...resto }) {
  return (
    <Como className={juntar('moldura', className)} {...resto}>
      <Cantos />
      {children}
    </Como>
  )
}

/* --- Ícones SVG limpos e modernos --- */

export function IconeInverterCamera({ tamanho = 18, className = '' }) {
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
      <path d="M20 10V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3" />
      <path d="M4 14v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      <polyline points="1 10 4 7 7 10" />
      <polyline points="23 14 20 17 17 14" />
    </svg>
  )
}

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

export function IconeMigracao({ tamanho = 18, className = '' }) {
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
      <path d="M3 7V5a2 2 0 0 1 2-2h4l2 2h4a2 2 0 0 1 2 2v1" />
      <path d="M4 21h13a2 2 0 0 0 2-2v-6" />
      <polyline points="9 13 13 17 9 21" />
      <line x1="13" y1="17" x2="3" y2="17" />
    </svg>
  )
}

/** Circulação: o que sai e o que volta. Duas setas, dois sentidos. */
export function IconeCirculacao({ tamanho = 18, className = '' }) {
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
      <polyline points="17 2 21 6 17 10" />
      <path d="M21 6H8a4 4 0 0 0-4 4v1" />
      <polyline points="7 22 3 18 7 14" />
      <path d="M3 18h13a4 4 0 0 0 4-4v-1" />
    </svg>
  )
}

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

export function Campo({ rotulo, ajuda, largo, className, ...resto }) {
  return (
    <label className={juntar('campo', largo && 'campo--largo', className)}>
      <span className="campo__rotulo">{rotulo}</span>
      <input className="campo__entrada" {...resto} />
      {ajuda && <span className="campo__ajuda">{ajuda}</span>}
    </label>
  )
}

/**
 * Controle segmentado: opções mutuamente exclusivas num só contorno.
 *
 * `opcoes` é uma lista de `[valor, rótulo]` — a mesma forma da constante ABAS
 * da tela da fila, para não precisar transformar nada na chamada.
 */
export function Segmentado({ opcoes, valor, aoMudar, rotulo }) {
  return (
    <div className="segmentado" role="tablist" aria-label={rotulo}>
      {opcoes.map(([v, r]) => (
        <button
          key={v}
          role="tab"
          aria-selected={valor === v}
          className={juntar(
            'segmentado__opcao',
            valor === v && 'segmentado__opcao--ativa'
          )}
          onClick={() => aoMudar(v)}
        >
          {r}
        </button>
      ))}
    </div>
  )
}

/**
 * Faixa de indicadores: os números grandes que abrem a tela da fila.
 *
 * Cada item: `{ n, rotulo, nota, tom, ativo, aoClicar }`. O `tom` é o
 * vocabulário de destino ('nova', 'existente', 'alerta', 'erro', 'acento') e é
 * ele que colore o número — a única razão de a faixa ter cor.
 */
export function FaixaIndicadores({ itens }) {
  return (
    <div className="indicadores">
      {itens.map((it) => {
        const classes = juntar(
          'indicador',
          it.tom && `indicador--${it.tom}`,
          !it.n && 'indicador--zero',
          it.ativo && 'indicador--ativo'
        )
        const conteudo = (
          <>
            <span className="indicador__numero numero">{it.n ?? 0}</span>
            <span className="indicador__rotulo">{it.rotulo}</span>
            {it.nota && <span className="indicador__nota">{it.nota}</span>}
          </>
        )

        return it.aoClicar ? (
          <button
            key={it.rotulo}
            className={classes}
            onClick={it.aoClicar}
            aria-pressed={!!it.ativo}
            title={it.nota}
          >
            {conteudo}
          </button>
        ) : (
          <div key={it.rotulo} className={classes} title={it.nota}>
            {conteudo}
          </div>
        )
      })}
    </div>
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

/*
 * A rota `/` chama-se "captura" e nao "escanear" porque ela e duas telas: no
 * celular e a camera, no PC e o balcao que gerencia os celulares. O destino e
 * o mesmo; o rotulo aqui e fixo porque esta barra so existe no PC.
 *
 * Ela e a unica navegacao do app. O celular nao tem barra nenhuma: la a
 * captura e a tela unica, e o titulo dela e da propria tela.
 */

export function Navbar({
  rotaAtiva,
  aoNavegar,
  loteQtd = 0,
  filaQtd = 0,
  // Atrasos em aberto. Como o badge da fila, conta o que PEDE AÇÃO — quem quer
  // saber o total de empréstimos abre a tela. Fica 0 enquanto a circulação não
  // estiver implementada, e o badge simplesmente não aparece.
  atrasosQtd = 0,
  conexao,
  aoAbrirBanco,
  aoAbrirExport,
}) {
  return (
    <header className="app-nav">
      <div className="app-nav__esquerda">
        <button
          className="app-nav__marca"
          onClick={() => aoNavegar('captura')}
          title="Ir para a captura"
        >
          <div className="app-nav__logo" aria-hidden="true">
            <IconeLivro tamanho={18} />
          </div>
          <div className="app-nav__titulos">
            <span className="app-nav__nome">BiblioFácil</span>
            <span className="app-nav__sub">BibLivre 5</span>
          </div>
        </button>
      </div>

      <nav className="app-nav__centro" aria-label="Navegação principal">
        <button
          className={juntar('app-nav__item', rotaAtiva === 'captura' && 'app-nav__item--ativo')}
          onClick={() => aoNavegar('captura')}
          aria-current={rotaAtiva === 'captura' ? 'page' : undefined}
        >
          <IconeScanner tamanho={16} />
          <span>Balcão de captura</span>
          {loteQtd > 0 && <span className="badge-lote">{loteQtd}</span>}
        </button>

        <button
          className={juntar('app-nav__item', rotaAtiva === 'fila' && 'app-nav__item--ativo')}
          onClick={() => aoNavegar('fila')}
          aria-current={rotaAtiva === 'fila' ? 'page' : undefined}
        >
          <IconeFila tamanho={16} />
          <span>Fila de revisão</span>
          {/* O badge conta o que pede acao, nao o total: item ja exportado
              continua na fila para consulta, e um "7" ao lado de uma fila sem
              nada a fazer e so um alarme falso. */}
          {filaQtd > 0 && <span className="badge-fila">{filaQtd}</span>}
        </button>

        {/* Circulação é a tela do dia seguinte ao primeiro dia: depois que o
            acervo entrou, é ela que a biblioteca abre de manhã e fecha à
            noite. Fica entre a fila e a migração porque é trabalho diário,
            não instalação. */}
        <button
          className={juntar('app-nav__item', rotaAtiva === 'circulacao' && 'app-nav__item--ativo')}
          onClick={() => aoNavegar('circulacao')}
          aria-current={rotaAtiva === 'circulacao' ? 'page' : undefined}
          title="Emprestar, devolver e consultar o leitor"
        >
          <IconeCirculacao tamanho={16} />
          <span>Circulação</span>
          {atrasosQtd > 0 && <span className="badge-fila">{atrasosQtd}</span>}
        </button>

        {/* Migração fica ao lado das duas telas de trabalho, e não escondida
            num menu: é o primeiro caminho de uma biblioteca que chega de
            sistema legado, e quem não souber que ele existe vai digitar 14 mil
            fichas à mão. */}
        <button
          className={juntar('app-nav__item', rotaAtiva === 'migracao' && 'app-nav__item--ativo')}
          onClick={() => aoNavegar('migracao')}
          aria-current={rotaAtiva === 'migracao' ? 'page' : undefined}
          title="Trazer um acervo inteiro do Biblioteca Fácil"
        >
          <IconeMigracao tamanho={16} />
          <span>Migração</span>
        </button>

        <button
          className="app-nav__item app-nav__item--export"
          onClick={aoAbrirExport}
          title="Abrir a confirmação de gravação no BibLivre"
        >
          <IconeExportar tamanho={16} />
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
      </div>
    </header>
  )
}

