import { useEffect, useRef, useState } from 'react'
import { Botao, Cantos, IconeBuscar, IconeCirculacao, IconeLanterna, Modal } from '../../components'
import { OverlayDeteccoes } from '../scanner/OverlayDeteccoes'
import { useScanner } from '../scanner/useScanner'
import {
  exemplarDisponivel,
  formatarData,
  idDoExemplar,
  idDoLeitor,
  nomeDe,
  tituloDe,
  tomboDe,
  useCirculacao,
} from './useCirculacao'
import './circulacao.css'

/**
 * O balcão móvel: emprestar e devolver bipando, de pé, com o leitor na frente.
 *
 * É a segunda tela que o celular ganha — até aqui a captura era a única, e é
 * por isso que o aparelho não tem barra de navegação. A volta para a câmera de
 * catalogação é oferecida aqui, no cabeçalho: quem decide como se sai de uma
 * tela é ela, não o App.
 *
 * AQUI O BIPE ESPERA
 * Na captura o celular nunca bloqueia: bipe é rascunho e o servidor reconcilia
 * depois (docs/SPEC_UI.md §7). Nesta tela é o contrário, e de propósito —
 * dizer "levou" antes do commit é mentir para quem está na frente do balcão.
 * Cada bipe passa por "gravando…" e termina em confirmação (verde, som subindo)
 * ou recusa (vermelho, som grave, motivo em uma linha). Enquanto espera, leitura
 * nova é ignorada; o hook `useCirculacao` é quem segura isso.
 *
 * DUAS COISAS QUE A TELA NÃO INVENTA
 * 1. O que o código é — quem diz é `GET /api/circulacao/resolver`. O operador
 *    nunca escolhe "tipo" antes de bipar.
 * 2. Se o leitor pode levar — quem diz é o servidor. A tela só traduz o motivo
 *    para uma frase de balcão (`traduzirCodigo`, em useCirculacao.js).
 *
 * O CAMINHO DO ISBN É DE PRIMEIRA CLASSE
 * Boa parte do acervo migrado não tem etiqueta impressa: são 16.251 tombos que
 * existem no banco e nem todos no papel. Bipar o código de barras da CAPA
 * devolve os exemplares daquela obra com o estado de cada um, e o operador
 * escolhe qual está na mão. Não é plano B, é o caminho normal de metade da
 * estante.
 */
export function TelaCirculacaoCelular({ conexao, aoNavegar }) {
  const c = useCirculacao()

  // O modo do scanner que o pacote A5 acrescenta: além do EAN-13 da capa, ele
  // passa a ler Code 39 / Code 128 da etiqueta do tombo. Enquanto A5 não
  // aterrissar, `useScanner` ignora a opção e só entrega ISBN — a tela
  // continua inteira, só que pelo caminho do ISBN e da digitação.
  const scanner = useScanner({
    modo: 'circulacao',
    aoLer: (codigo) => c.processar(codigo),
  })

  const [manual, setManual] = useState('')
  const [mostrarBusca, setMostrarBusca] = useState(false)
  const [buscandoLivro, setBuscandoLivro] = useState(false)

  const semAcervo = Boolean(conexao?.bruto) && !conexao.conectado
  const emprestando = c.modo === 'emprestar'
  const leitor = c.ficha?.leitor || null

  // Sessão morreu no meio do turno: a câmera aberta apontada para nada só
  // consome bateria enquanto a tela pede senha.
  useEffect(() => {
    if (!c.operador && scanner.escaneando) scanner.parar()
  }, [c.operador, scanner.escaneando, scanner.parar])

  if (c.verificandoSessao) {
    return (
      <div className="circ circ--espera">
        <span className="microrrotulo">Verificando a sessão</span>
      </div>
    )
  }

  // Sem operador, o login é a única coisa na tela: quem emprestou é informação
  // de balcão que vai para `lendings.created_by`, e não há circulação anônima.
  if (!c.operador) {
    return (
      <TelaEntrar
        entrando={c.entrando}
        erro={c.erroLogin}
        aoEntrar={c.entrar}
        aoVoltar={() => aoNavegar?.('captura')}
      />
    )
  }

  const enviarManual = () => {
    const texto = manual.trim()
    if (!texto) return
    setManual('')
    c.processar(texto)
  }

  return (
    <div className={`circ circ--${c.modo}`}>
      <header className="circ__topo">
        <button className="circ__voltar" onClick={() => aoNavegar?.('captura')}>
          ← Escanear
        </button>
        <span className="circ__marca">
          <IconeCirculacao tamanho={14} />
          Circulação
        </span>
        <button className="circ__operador" onClick={c.sair} title="Encerrar a sessão">
          {c.operador.nome || c.operador.login}
        </button>
      </header>

      {/*
        Os dois modos, no topo e do tamanho de um polegar. A cor é o que se lê à
        distância de um braço, e ela é diferente do verde/vermelho da
        confirmação de propósito: modo é onde eu estou, verde/vermelho é o que
        acabou de acontecer. Misturar os dois faria a tela inteira parecer um
        erro toda vez que estivesse em devolução.
      */}
      <div className="circ__modos" role="tablist" aria-label="Modo de circulação">
        <button
          role="tab"
          aria-selected={emprestando}
          className={`circ__modo circ__modo--emprestar${emprestando ? ' circ__modo--ativo' : ''}`}
          onClick={() => c.trocarModo('emprestar')}
          disabled={c.ocupado}
        >
          Emprestar
        </button>
        <button
          role="tab"
          aria-selected={!emprestando}
          className={`circ__modo circ__modo--devolver${!emprestando ? ' circ__modo--ativo' : ''}`}
          onClick={() => c.trocarModo('devolver')}
          disabled={c.ocupado}
        >
          Devolver
        </button>
      </div>

      {semAcervo && (
        <p className="circ__sem-banco" role="alert">
          <strong>Sem conexão com o acervo.</strong> Nada pode ser gravado agora —
          anote no papel e avise quem cuida do servidor.
        </p>
      )}

      {emprestando &&
        (leitor ? (
          <FaixaLeitor
            leitor={leitor}
            situacao={c.ficha?.situacao}
            saidas={c.movimentos.filter((m) => m.tipo === 'saiu').length}
            aoSoltar={c.soltarLeitor}
          />
        ) : (
          <PassoLeitor
            carregando={c.carregandoLeitor}
            mostrarBusca={mostrarBusca}
            aoAlternarBusca={() => setMostrarBusca((v) => !v)}
            aoBuscar={c.buscarLeitores}
            aoEscolher={(l) => {
              setMostrarBusca(false)
              c.fixarLeitorPorId(idDoLeitor(l))
            }}
          />
        ))}

      <Visor scanner={scanner} modo={c.modo} trabalho={c.trabalho} ocupado={c.ocupado} />

      {c.barreira ? (
        <PainelBarreira barreira={c.barreira} aoFechar={c.limparBarreira} />
      ) : c.resultado ? (
        <PainelResultado resultado={c.resultado} aoFechar={c.limparResultado} />
      ) : null}

      <footer className="circ__rodape">
        <div className="circ__manual">
          <input
            className="circ__manual-campo mono"
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && enviarManual()}
            placeholder={emprestando && !leitor ? 'Nº da carteirinha' : 'Tombo ou ISBN'}
            aria-label="Digitar o código à mão"
            autoComplete="off"
          />
          <Botao variante="secundario" onClick={enviarManual} disabled={!manual.trim() || c.ocupado}>
            Ir
          </Botao>
          {(!emprestando || leitor) && (
            <button
              className="circ__passo-busca"
              onClick={() => setBuscandoLivro((v) => !v)}
              aria-expanded={buscandoLivro}
            >
              <IconeBuscar tamanho={14} />
              Título
            </button>
          )}
        </div>

        {buscandoLivro && (!emprestando || leitor) && (
          <BuscaLivro
            aoBuscar={c.buscarObras}
            aoEscolher={(obra) => {
              setBuscandoLivro(false)
              c.abrirObra(obra)
            }}
          />
        )}

        {c.movimentos.length > 0 && (
          <ul className="circ__movimentos">
            {c.movimentos.map((m) => (
              <li key={m.chave} className={`circ__mov circ__mov--${m.tipo}`}>
                <span className="circ__mov-marca" aria-hidden="true">
                  {m.tipo === 'saiu' ? '→' : '←'}
                </span>
                <span className="circ__mov-titulo">{m.titulo || 'sem título'}</span>
                <span className="circ__mov-tombo mono">{m.tombo}</span>
              </li>
            ))}
          </ul>
        )}
      </footer>

      {c.decisao?.tipo === 'exemplares' && (
        <FolhaExemplares
          decisao={c.decisao}
          aoEscolher={c.escolherExemplar}
          aoFechar={c.cancelarDecisao}
        />
      )}

      {c.decisao?.tipo === 'avisos' && (
        <FolhaAvisos
          decisao={c.decisao}
          leitor={leitor}
          aoConfirmar={c.confirmarAvisos}
          aoFechar={c.cancelarDecisao}
        />
      )}

      {c.decisao?.tipo === 'trocar_leitor' && (
        <FolhaTrocarLeitor
          novo={c.decisao.leitor}
          atual={leitor}
          aoConfirmar={c.confirmarTrocaDeLeitor}
          aoFechar={c.cancelarDecisao}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Entrar                                                             *
 * ------------------------------------------------------------------ */

/**
 * O login, sozinho na tela.
 *
 * É a mesma senha do BibLivre (tabela `logins`), e o motivo de existir não é
 * burocracia: sem operador, `lendings.created_by` volta a ser o admin do
 * instalador e qualquer celular no wi-fi da biblioteca registra empréstimo.
 */
function TelaEntrar({ entrando, erro, aoEntrar, aoVoltar }) {
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')

  const enviar = (e) => {
    e.preventDefault()
    if (usuario.trim() && senha) aoEntrar(usuario.trim(), senha)
  }

  return (
    <div className="circ circ--entrar">
      <form className="circ-entrar" onSubmit={enviar}>
        <span className="microrrotulo">Circulação</span>
        <h1 className="circ-entrar__titulo">Quem está no balcão?</h1>
        <p className="circ-entrar__texto">
          O empréstimo fica registrado no seu nome. É o mesmo usuário e a mesma
          senha do BibLivre.
        </p>

        <label className="circ-entrar__campo">
          <span className="microrrotulo">Usuário</span>
          <input
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="username"
            aria-label="Usuário"
            autoFocus
          />
        </label>

        <label className="circ-entrar__campo">
          <span className="microrrotulo">Senha</span>
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="current-password"
            aria-label="Senha"
          />
        </label>

        {erro && (
          <p className="circ-entrar__erro" role="alert">
            {erro}
          </p>
        )}

        <button
          type="submit"
          className="btn btn--primario btn--toque btn--bloco moldura"
          disabled={entrando || !usuario.trim() || !senha}
        >
          <Cantos />
          {entrando ? 'Entrando…' : 'Entrar'}
        </button>

        <button type="button" className="circ-entrar__voltar" onClick={aoVoltar}>
          Voltar para a captura
        </button>
      </form>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Etapa 1: o leitor                                                   *
 * ------------------------------------------------------------------ */

/** A instrução do passo 1, com a busca por nome escondida atrás de um toque. */
function PassoLeitor({ carregando, mostrarBusca, aoAlternarBusca, aoBuscar, aoEscolher }) {
  return (
    <section className="circ__passo">
      <div className="circ__passo-linha">
        <span className="circ__passo-numero numero">1</span>
        <p className="circ__passo-texto">
          {carregando ? 'Abrindo a ficha…' : 'Quem vai levar? Bipe a carteirinha ou digite o número.'}
        </p>
        <button className="circ__passo-busca" onClick={aoAlternarBusca} aria-expanded={mostrarBusca}>
          <IconeBuscar tamanho={14} />
          Nome
        </button>
      </div>
      {mostrarBusca && <BuscaLeitor aoBuscar={aoBuscar} aoEscolher={aoEscolher} />}
    </section>
  )
}

/** Busca por nome: o caminho de quem esqueceu a carteirinha. */
function BuscaLeitor({ aoBuscar, aoEscolher }) {
  const [texto, setTexto] = useState('')
  const [achados, setAchados] = useState([])
  const [procurando, setProcurando] = useState(false)
  const pedido = useRef(0)

  useEffect(() => {
    const alvo = texto.trim()
    if (alvo.length < 2) {
      setAchados([])
      return
    }
    const meu = ++pedido.current
    setProcurando(true)
    const t = setTimeout(async () => {
      const r = await aoBuscar(alvo)
      // Resposta velha chegando depois da nova sobrescreveria a lista certa.
      if (pedido.current === meu) {
        setAchados(r)
        setProcurando(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [texto, aoBuscar])

  return (
    <div className="circ-busca">
      <input
        className="circ-busca__campo"
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="Parte do nome"
        aria-label="Procurar leitor pelo nome"
        autoFocus
      />
      {procurando && <p className="circ-busca__nota">procurando…</p>}
      {!procurando && texto.trim().length >= 2 && achados.length === 0 && (
        <p className="circ-busca__nota">Ninguém com esse nome no cadastro.</p>
      )}
      <ul className="circ-busca__lista">
        {achados.map((l) => (
          <li key={idDoLeitor(l)}>
            <button className="circ-busca__item" onClick={() => aoEscolher(l)}>
              <span className="circ-busca__nome">{nomeDe(l)}</span>
              <span className="circ-busca__id mono">#{idDoLeitor(l)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Busca por título: o livro sem etiqueta legível e sem ISBN na capa. Escolher
 * a obra abre a mesma folha do caminho do ISBN.
 */
function BuscaLivro({ aoBuscar, aoEscolher }) {
  const [texto, setTexto] = useState('')
  const [achados, setAchados] = useState([])
  const [procurando, setProcurando] = useState(false)
  const pedido = useRef(0)

  useEffect(() => {
    const alvo = texto.trim()
    if (alvo.length < 3) {
      setAchados([])
      return
    }
    const meu = ++pedido.current
    setProcurando(true)
    const t = setTimeout(async () => {
      const r = await aoBuscar(alvo)
      if (pedido.current === meu) {
        setAchados(r)
        setProcurando(false)
      }
    }, 400)
    return () => clearTimeout(t)
  }, [texto, aoBuscar])

  return (
    <div className="circ-busca">
      <input
        className="circ-busca__campo"
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="Parte do título ou do autor"
        aria-label="Procurar livro pelo título"
        autoFocus
      />
      {procurando && <p className="circ-busca__nota">procurando…</p>}
      {!procurando && texto.trim().length >= 3 && achados.length === 0 && (
        <p className="circ-busca__nota">Nenhum livro com esse título no acervo.</p>
      )}
      <ul className="circ-busca__lista">
        {achados.map((o) => (
          <li key={o.record_id}>
            <button className="circ-busca__item" onClick={() => aoEscolher(o)}>
              <span className="circ-busca__nome">{o.titulo || 'sem título'}</span>
              <span className="circ-busca__id mono">
                {o.disponiveis}/{o.total}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * O leitor fixado no topo, como sessão.
 *
 * Fica visível o tempo todo enquanto os livros são bipados: sem isso, dois
 * atendimentos seguidos viram um empréstimo no nome errado, que é o erro mais
 * caro que esta tela pode cometer.
 */
function FaixaLeitor({ leitor, situacao, saidas, aoSoltar }) {
  const s = situacao || {}
  const partes = [
    `${Number(s.abertos) || 0} em aberto`,
    Number(s.atrasados) > 0 && `${s.atrasados} atrasado${s.atrasados > 1 ? 's' : ''}`,
    Number(s.multas) > 0 && `multa de ${Number(s.multas).toFixed(2).replace('.', ',')}`,
  ].filter(Boolean)

  return (
    <section className="circ-leitor">
      <div className="circ-leitor__corpo">
        <p className="circ-leitor__nome">{nomeDe(leitor) || `Leitor #${idDoLeitor(leitor)}`}</p>
        <p className="circ-leitor__situacao">
          {partes.join(' · ')}
          {saidas > 0 && <strong> · {saidas} levando agora</strong>}
        </p>
      </div>
      <button className="circ-leitor__sair" onClick={aoSoltar} aria-label="Encerrar o atendimento">
        Encerrar
      </button>
    </section>
  )
}

/* ------------------------------------------------------------------ *
 * Visor                                                               *
 * ------------------------------------------------------------------ */

/**
 * A câmera.
 *
 * É a mesma do scanner de captura, com uma diferença de postura visível: a
 * barra de status mostra "gravando…" enquanto o servidor não respondeu, porque
 * aqui existe um intervalo em que o operador precisa esperar.
 */
function Visor({ scanner, modo, trabalho, ocupado }) {
  if (scanner.erroCamera) {
    return (
      <div className="circ__visor circ__visor--negado" role="alert">
        <p className="circ__negado-titulo">Sem acesso à câmera</p>
        <p className="circ__negado-texto">{scanner.erroCamera}</p>
        <p className="circ__negado-nota">
          Dá para trabalhar assim: digite o tombo ou o ISBN no campo lá embaixo.
        </p>
        <Botao variante="primario" tamanho="toque" onClick={scanner.iniciar}>
          Pedir permissão de novo
        </Botao>
      </div>
    )
  }

  return (
    <div
      className="circ__visor"
      onClick={() => scanner.escaneando && scanner.dispararFoco?.()}
    >
      <div id={scanner.elementoId} className="circ__camera" />

      {!scanner.escaneando ? (
        <div className="circ__repouso">
          <Botao variante="primario" tamanho="toque" onClick={scanner.iniciar}>
            Abrir a câmera
          </Botao>
        </div>
      ) : (
        <>
          <OverlayDeteccoes
            deteccoes={scanner.deteccoes}
            quadro={scanner.quadro}
            alvo={scanner.alvo}
            dica={modo === 'devolver' ? 'Bipe a etiqueta do livro' : 'Bipe a carteirinha ou a etiqueta'}
          />
          <div className="circ__controles">
            <button
              type="button"
              className={`circ__botao${scanner.lanternaLigada ? ' circ__botao--ativo' : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                scanner.alternarLanterna()
              }}
              aria-pressed={scanner.lanternaLigada}
              aria-label={scanner.lanternaLigada ? 'Apagar a lanterna' : 'Acender a lanterna'}
            >
              <IconeLanterna tamanho={16} />
            </button>
            <button
              type="button"
              className="circ__botao"
              onClick={(e) => {
                e.stopPropagation()
                scanner.parar()
              }}
              aria-label="Fechar a câmera"
            >
              ✕
            </button>
          </div>
        </>
      )}

      <div
        className={`circ__barra${ocupado ? ' circ__barra--ocupada' : ''}`}
        role="status"
        aria-live="polite"
      >
        <span>
          {ocupado
            ? trabalho || 'Gravando…'
            : scanner.escaneando
              ? scanner.status || 'Aponte para o código de barras'
              : 'Câmera fechada'}
        </span>
        {ocupado && <span className="circ__barra-espera" aria-hidden="true" />}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Resultado do bipe                                                   *
 * ------------------------------------------------------------------ */

const TITULO_TOM = {
  ok: 'Confirmado',
  aviso: 'Atenção',
  erro: 'Recusado',
  incerto: 'Sem confirmação',
}

/**
 * A resposta do servidor, em uma frase.
 *
 * Quatro tons, e o quarto é o que a tela não pode perder: `incerto` é quando a
 * rede caiu no meio. Ele não é verde nem vermelho porque nenhum dos dois seria
 * verdade — o empréstimo pode ter sido gravado, e afirmar qualquer coisa aqui
 * seria inventar estado que a tela não tem.
 */
function PainelResultado({ resultado, aoFechar }) {
  const r = resultado
  return (
    <section className={`circ-res circ-res--${r.tom}`} role="status" aria-live="assertive">
      <div className="circ-res__topo">
        <span className="microrrotulo">{TITULO_TOM[r.tom] || 'Resposta'}</span>
        <button className="circ-res__fechar" onClick={aoFechar} aria-label="Fechar o aviso">
          ✕
        </button>
      </div>
      <p className="circ-res__titulo">{r.titulo}</p>
      <p className="circ-res__frase">{r.frase}</p>
      {r.saida && <p className="circ-res__saida">{r.saida}</p>}

      {r.linhas?.length > 0 && (
        <dl className="circ-res__linhas">
          {r.linhas.map((l) => (
            <div key={l.rotulo} className={l.tom ? `circ-res__linha--${l.tom}` : undefined}>
              <dt>{l.rotulo}</dt>
              <dd className={l.mono ? 'mono' : undefined}>{l.valor}</dd>
            </div>
          ))}
        </dl>
      )}

      {r.multa && (
        <p className="circ-res__multa">
          <strong>Multa de {r.multa.valor}</strong>
          {r.multa.dias > 0 && ` por ${r.multa.dias} ${r.multa.dias === 1 ? 'dia' : 'dias'} de atraso`}
          . Acerte antes de emprestar de novo para esta pessoa.
        </p>
      )}

      {r.reserva && (
        <p className="circ-res__reserva">
          <strong>Separe este livro.</strong> Está reservado para {r.reserva.leitor}.
        </p>
      )}

      {r.motivos?.length > 0 && (
        <ul className="circ-res__motivos">
          {r.motivos.map((m) => (
            <li key={m.codigo}>{m.frase}</li>
          ))}
        </ul>
      )}

      {r.avisosIgnorados?.length > 0 && (
        <p className="circ-res__ignorado">
          Emprestado ignorando: {r.avisosIgnorados.map((a) => a.frase).join(' ')}
        </p>
      )}
    </section>
  )
}

/** O leitor barrado na etapa 1: não dá nem para bipar livro. */
function PainelBarreira({ barreira, aoFechar }) {
  return (
    <section className="circ-res circ-res--erro" role="alert">
      <div className="circ-res__topo">
        <span className="microrrotulo">Não pode levar</span>
        <button className="circ-res__fechar" onClick={aoFechar} aria-label="Fechar">
          ✕
        </button>
      </div>
      <p className="circ-res__titulo">
        {nomeDe(barreira.leitor) || `Leitor #${idDoLeitor(barreira.leitor)}`}
      </p>
      <ul className="circ-res__motivos">
        {barreira.motivos.map((m) => (
          <li key={m.codigo}>
            <strong>{m.frase}</strong> {m.saida}
          </li>
        ))}
      </ul>
      <p className="circ-res__saida">
        Enquanto isso não for resolvido, este leitor não leva livro — nem bipando.
      </p>
    </section>
  )
}

/* ------------------------------------------------------------------ *
 * Folhas de decisão                                                   *
 * ------------------------------------------------------------------ */

/**
 * O caminho do ISBN: qual destes exemplares está na sua mão?
 *
 * A lista mostra o estado de cada cópia porque é ele que decide o que dá para
 * fazer: emprestar só o que está livre, devolver só o que está fora. Exemplar
 * que não serve continua na lista, desabilitado e com o motivo — sumir com ele
 * faria o operador procurar na estante um livro que a tela escondeu.
 */
function FolhaExemplares({ decisao, aoEscolher, aoFechar }) {
  const devolvendo = decisao.acao === 'devolver'
  const exemplares = decisao.exemplares || []
  const titulo = tituloDe(decisao.obra) || 'Obra sem título'

  return (
    <Modal titulo={devolvendo ? 'Qual exemplar voltou?' : 'Qual exemplar está na mão?'} aoFechar={aoFechar}>
      <p className="circ-folha__obra">{titulo}</p>
      <p className="circ-folha__nota">
        {decisao.origem === 'titulo'
          ? 'Livro encontrado pela busca por título. '
          : 'Este livro não foi identificado pela etiqueta, e sim pelo código de barras da capa. '}
        A biblioteca tem {exemplares.length}{' '}
        {exemplares.length === 1 ? 'exemplar' : 'exemplares'} desta obra — escolha
        pelo tombo escrito no livro.
      </p>

      {exemplares.length === 0 ? (
        <p className="circ-folha__vazio">
          Nenhum exemplar desta obra no acervo. Confira no PC antes de continuar.
        </p>
      ) : (
        <ul className="circ-folha__lista">
          {exemplares.map((ex) => {
            const livre = exemplarDisponivel(ex)
            const serve = devolvendo ? !livre : livre
            const estado = livre
              ? 'na estante'
              : ex.emprestimo?.previsto_para
                ? `emprestado até ${formatarData(ex.emprestimo.previsto_para)}`
                : 'emprestado'
            return (
              <li key={idDoExemplar(ex)}>
                <button
                  className={`circ-folha__item${serve ? '' : ' circ-folha__item--inerte'}`}
                  onClick={() => serve && aoEscolher(ex)}
                  disabled={!serve}
                >
                  <span className="circ-folha__tombo mono">{tomboDe(ex) || `#${idDoExemplar(ex)}`}</span>
                  <span className={`circ-folha__estado circ-folha__estado--${livre ? 'livre' : 'fora'}`}>
                    {estado}
                  </span>
                  {ex.localizacao && <span className="circ-folha__local">{ex.localizacao}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Modal>
  )
}

/**
 * Aviso não barra — mas passar por cima dele é decisão de gente, e a tela
 * precisa dizer exatamente o que está sendo ignorado antes de reenviar com
 * `forcar_avisos`.
 */
function FolhaAvisos({ decisao, leitor, aoConfirmar, aoFechar }) {
  return (
    <Modal
      titulo="Emprestar mesmo assim?"
      aoFechar={aoFechar}
      rodape={
        <div className="circ-folha__acoes">
          <Botao variante="secundario" tamanho="toque" onClick={aoFechar}>
            Não emprestar
          </Botao>
          <button className="btn btn--primario btn--toque moldura" onClick={aoConfirmar}>
            <Cantos />
            Emprestar assim mesmo
          </button>
        </div>
      }
    >
      <p className="circ-folha__nota">
        O empréstimo para{' '}
        <strong>{nomeDe(leitor) || 'este leitor'}</strong> pode ser feito, mas
        você estará ignorando:
      </p>
      <ul className="circ-folha__avisos">
        {decisao.motivos.map((m) => (
          <li key={m.codigo}>
            <strong>{m.frase}</strong> {m.saida}
          </li>
        ))}
      </ul>
      <p className="circ-folha__nota">
        Confirmando, o empréstimo fica gravado no seu nome de operador.
      </p>
    </Modal>
  )
}

/** Duas carteirinhas seguidas: quase sempre é o próximo da fila. */
function FolhaTrocarLeitor({ novo, atual, aoConfirmar, aoFechar }) {
  return (
    <Modal
      titulo="Trocar de leitor?"
      aoFechar={aoFechar}
      rodape={
        <div className="circ-folha__acoes">
          <Botao variante="secundario" tamanho="toque" onClick={aoFechar}>
            Continuar com {nomeDe(atual)?.split(' ')[0] || 'o atual'}
          </Botao>
          <button className="btn btn--primario btn--toque moldura" onClick={aoConfirmar}>
            <Cantos />
            Atender {nomeDe(novo)?.split(' ')[0] || 'o novo'}
          </button>
        </div>
      }
    >
      <p className="circ-folha__nota">
        Você bipou a carteirinha de <strong>{nomeDe(novo) || `#${idDoLeitor(novo)}`}</strong>{' '}
        enquanto atendia <strong>{nomeDe(atual) || 'outro leitor'}</strong>.
      </p>
      <p className="circ-folha__nota">
        O que já foi emprestado continua gravado — a troca só muda quem leva os
        próximos.
      </p>
    </Modal>
  )
}
