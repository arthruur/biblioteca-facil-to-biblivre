/**
 * @fileoverview Estado e chamadas da circulação no celular: emprestar e devolver.
 *
 * PROPOSITO:
 * Concentra tudo o que a tela do celular precisa saber para bipar um livro e
 * dizer, com honestidade, o que aconteceu do outro lado: sessão do operador,
 * modo corrente, leitor fixado, decisões pendentes e o resultado do último
 * bipe já traduzido para uma frase de balcão.
 *
 * A POSTURA (o oposto da captura):
 * Na captura o celular nunca bloqueia — bipe é rascunho e o servidor
 * reconcilia depois (docs/SPEC_UI.md §7). Aqui ele ESPERA: dizer "levou"
 * antes do commit é mentir para quem está na frente do balcão. Por isso
 * `processar` recusa leitura nova enquanto há trabalho em curso ou decisão
 * aberta, e por isso falha de rede vira "não deu para confirmar", nunca
 * "emprestado".
 *
 * QUEM DECIDE O QUÊ:
 * - o que o código é           -> o servidor (`GET /api/circulacao/resolver`)
 * - se o leitor pode levar     -> o servidor (`situacao.pode_levar` e o 409)
 * - como isso se diz em português -> aqui (`FRASES`)
 * A tela não tem estado próprio de verdade; o empréstimo é do servidor.
 *
 * INTERFACE:
 * - useCirculacao(): object   (ver o `return` no fim do arquivo)
 * - traduzirCodigo(codigo): { frase, saida }
 *
 * LIMITACOES:
 * Os nomes de campo das respostas (`tombo`/`accession_number`,
 * `titulo`/`title`, `nome`/`name`) ainda não estão fechados no contrato —
 * as funções `tomboDe`, `tituloDe` e `nomeDe` aceitam as variantes plausíveis
 * de propósito, e isso deve encolher quando o pacote A3 fechar as chaves.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, definirSessao } from '../../api/client'

/**
 * Onde o token vive.
 *
 * `client.js` guarda a sessão só em memória e deixa explícito que quem decide
 * sobreviver a um F5 é a tela. No balcão isso importa: o celular bloqueia,
 * volta, e obrigar a digitar a senha a cada retomada faria o operador escolher
 * a senha mais curta possível. `sessionStorage` é o meio-termo — vive enquanto
 * a aba viver, morre quando o navegador é fechado, e não fica no aparelho
 * depois que o turno acaba.
 */
const CHAVE_SESSAO = 'biblio.circulacao.sessao'

/**
 * Janela em que o mesmo código, já concluído, é ignorado.
 *
 * O scanner entrega a mesma etiqueta muitas vezes enquanto o livro está
 * enquadrado, e ele já tem a própria janela anti-repetição. Esta aqui é outra
 * coisa: depois de um empréstimo CONFIRMADO, o livro costuma ficar mais alguns
 * segundos na frente da câmera enquanto o operador conversa. Sem a janela, o
 * segundo bipe viraria uma recusa vermelha ("já emprestado") logo depois do
 * verde — assustador e mentiroso.
 */
const JANELA_CONCLUIDO = 5000

/* ------------------------------------------------------------------ *
 * Vocabulário do balcão                                              *
 * ------------------------------------------------------------------ */

/**
 * Cada código de impedimento do §4.3 do plano, em frase de balcão.
 *
 * `frase` é o que aconteceu; `saida` é o que a pessoa faz agora. Nenhuma das
 * duas menciona número de status, código interno ou nome de tabela: quem lê
 * está de pé, com o leitor na frente, e precisa de uma instrução, não de um
 * diagnóstico.
 */
const FRASES = {
  leitor_nao_encontrado: {
    frase: 'Não achei esse leitor no cadastro.',
    saida: 'Confira o número da carteirinha ou procure pelo nome.',
  },
  leitor_inativo: {
    frase: 'O cadastro deste leitor está inativo.',
    saida: 'Ele precisa ser reativado no BibLivre antes de levar livro.',
  },
  leitor_bloqueado: {
    frase: 'Este leitor está bloqueado.',
    saida: 'Só a biblioteca libera, pelo BibLivre.',
  },
  leitor_com_atraso: {
    frase: 'Este leitor tem livro atrasado.',
    saida: 'Precisa devolver o que está atrasado antes de levar outro.',
  },
  limite_atingido: {
    frase: 'Já está com o número máximo de livros permitido.',
    saida: 'Devolva um para poder levar outro.',
  },
  multa_em_aberto: {
    frase: 'Há multa em aberto no nome deste leitor.',
    saida: 'Acerte a multa na biblioteca antes de emprestar de novo.',
  },
  exemplar_nao_encontrado: {
    frase: 'Este tombo não existe no acervo.',
    saida: 'Confira a etiqueta, ou bipe o código de barras da capa para achar o livro pelo ISBN.',
  },
  exemplar_emprestado: {
    frase: 'Este exemplar já está emprestado para outra pessoa.',
    saida: 'Se ele está aqui na sua mão, devolva primeiro — troque para DEVOLVER e bipe de novo.',
  },
  exemplar_indisponivel: {
    frase: 'Este exemplar não pode sair da biblioteca.',
    saida: 'Está marcado como consulta local, em encadernação ou baixado.',
  },
  reserva_de_outro_leitor: {
    frase: 'Este livro está reservado para outro leitor.',
    saida: 'Separe o exemplar para quem reservou.',
  },
  sem_operador: {
    frase: 'Sua sessão expirou.',
    saida: 'Entre de novo para continuar emprestando.',
  },
  sem_banco: {
    frase: 'Sem conexão com o acervo — nada foi gravado.',
    saida: 'Avise quem cuida do servidor antes de continuar no papel.',
  },
  conflito: {
    frase: 'Este exemplar mudou de estado agora há pouco.',
    saida: 'Alguém pode ter mexido nele pelo BibLivre. Confira antes de repetir.',
  },
}

/**
 * O código -> a frase. Código que não conhecemos ainda vira uma frase honesta
 * em vez de vazar o identificador cru na tela.
 */
export function traduzirCodigo(codigo) {
  if (!codigo) return { frase: 'Não deu para concluir.', saida: 'Confira no PC antes de repetir.' }
  return (
    FRASES[codigo] || {
      frase: 'Não deu para concluir esta operação.',
      saida: 'Confira no PC antes de repetir.',
    }
  )
}

/** As frases de uma lista de códigos (impedimentos ou avisos). */
function traduzirLista(codigos) {
  return (codigos || []).map((c) => ({ codigo: c, ...traduzirCodigo(c) }))
}

/* ------------------------------------------------------------------ *
 * Leitura defensiva das respostas                                     *
 * ------------------------------------------------------------------ */

export const tomboDe = (ex) =>
  ex?.tombo || ex?.accession_number || ex?.numero || ''

export const tituloDe = (o) =>
  o?.titulo || o?.title || o?.obra?.titulo || o?.obra?.title || ''

export const nomeDe = (p) => p?.nome || p?.name || ''

export const idDoExemplar = (ex) => ex?.holding_id ?? ex?.id ?? null

export const idDoLeitor = (l) => l?.id ?? l?.user_id ?? null

/** Exemplar livre para sair? Aceita as duas formas plausíveis da resposta. */
export function exemplarDisponivel(ex) {
  if (!ex) return false
  if (ex.emprestado === true) return false
  if (ex.emprestimo) return false
  if (typeof ex.disponivel === 'boolean') return ex.disponivel
  if (ex.availability && ex.availability !== 'available') return false
  return true
}

/** "AAAA-MM-DD" -> "DD/MM/AAAA", sem passar por `Date` (que muda o dia por fuso). */
export function formatarData(iso) {
  if (!iso) return ''
  const m = String(iso).slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : String(iso)
}

export function formatarDinheiro(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

/* ------------------------------------------------------------------ *
 * Som da confirmação                                                  *
 * ------------------------------------------------------------------ */

/*
 * Dois sons, e nenhum deles é o bipe do scanner.
 *
 * O bipe de 880Hz de `features/scanner/core/audio.js` já toca no instante em
 * que o código é DECODIFICADO — ele diz "li a etiqueta". Aqui o que interessa
 * é outra coisa: o servidor gravou, ou recusou. Se os dois sons fossem iguais,
 * o operador ouviria "ok" e guardaria o livro sem que nada tivesse sido
 * gravado. Por isso: duas notas subindo para confirmação, duas notas graves
 * descendo para recusa.
 *
 * O contexto é criado aqui porque `audio.js` não exporta o dele (e é arquivo
 * do pacote A5) — está relatado no relatório do pacote.
 */
let contextoAudio = null

function tocarNotas(notas) {
  try {
    if (typeof window === 'undefined') return
    const AudioCtx = window.AudioContext || window.webkitAudioContext
    if (!AudioCtx) return
    if (!contextoAudio || contextoAudio.state === 'closed') contextoAudio = new AudioCtx()
    if (contextoAudio.state === 'suspended') contextoAudio.resume().catch(() => {})

    const ctx = contextoAudio
    notas.forEach(([freq, atraso, duracao], i) => {
      const osc = ctx.createOscillator()
      const ganho = ctx.createGain()
      osc.type = i === 0 ? 'sine' : 'triangle'
      osc.frequency.value = freq
      ganho.gain.value = 0.14
      osc.connect(ganho).connect(ctx.destination)
      const inicio = ctx.currentTime + atraso
      osc.start(inicio)
      ganho.gain.setValueAtTime(0.14, inicio)
      ganho.gain.exponentialRampToValueAtTime(0.0001, inicio + duracao)
      osc.stop(inicio + duracao + 0.01)
    })
  } catch {
    /* aparelho em silencioso, autoplay bloqueado: a tela continua dizendo tudo */
  }
}

const somConfirmado = () => tocarNotas([[660, 0, 0.12], [990, 0.1, 0.18]])
const somRecusado = () => tocarNotas([[220, 0, 0.2], [165, 0.16, 0.3]])

function vibrarPadrao(padrao) {
  try {
    navigator?.vibrate?.(padrao)
  } catch {
    /* iOS Safari não vibra; o visual dá conta */
  }
}

/* ------------------------------------------------------------------ *
 * O hook                                                              *
 * ------------------------------------------------------------------ */

export function useCirculacao() {
  // Sessão do operador (`lendings.created_by` é ele, não o admin do instalador).
  const [operador, setOperador] = useState(null)
  const [verificandoSessao, setVerificandoSessao] = useState(true)
  const [entrando, setEntrando] = useState(false)
  const [erroLogin, setErroLogin] = useState('')

  const [modo, setModo] = useState('emprestar')
  const [ficha, setFicha] = useState(null) // {leitor, situacao, emprestimos}
  const [carregandoLeitor, setCarregandoLeitor] = useState(false)
  const [barreira, setBarreira] = useState(null) // leitor barrado na etapa 1
  const [ocupado, setOcupado] = useState(false)
  const [trabalho, setTrabalho] = useState('') // o que está sendo esperado
  const [resultado, setResultado] = useState(null)
  const [decisao, setDecisao] = useState(null) // escolha de exemplar / aviso / troca
  const [movimentos, setMovimentos] = useState([]) // o que saiu e o que voltou

  const modoRef = useRef(modo)
  const fichaRef = useRef(ficha)
  const ocupadoRef = useRef(false)
  const decisaoRef = useRef(null)
  const concluidos = useRef(new Map())

  modoRef.current = modo
  fichaRef.current = ficha
  decisaoRef.current = decisao

  /* --- sessão --- */

  const encerrarLocal = useCallback(() => {
    definirSessao(null)
    try {
      sessionStorage.removeItem(CHAVE_SESSAO)
    } catch {
      /* modo privado */
    }
    setOperador(null)
    setFicha(null)
    setBarreira(null)
  }, [])

  useEffect(() => {
    let vivo = true
    let token = null
    try {
      token = sessionStorage.getItem(CHAVE_SESSAO)
    } catch {
      token = null
    }
    if (!token) {
      setVerificandoSessao(false)
      return () => {
        vivo = false
      }
    }
    definirSessao(token)
    api.sessao
      .atual()
      .then((d) => vivo && setOperador(d?.operador || null))
      .catch(() => {
        // Token velho ou servidor sem a sessão em memória (ele reiniciou):
        // some com ele em vez de deixar a tela achar que está logada.
        definirSessao(null)
        try {
          sessionStorage.removeItem(CHAVE_SESSAO)
        } catch {
          /* modo privado */
        }
      })
      .finally(() => vivo && setVerificandoSessao(false))
    return () => {
      vivo = false
    }
  }, [])

  const entrar = useCallback(async (usuario, senha) => {
    setEntrando(true)
    setErroLogin('')
    try {
      const d = await api.sessao.entrar(usuario, senha)
      definirSessao(d.token)
      try {
        sessionStorage.setItem(CHAVE_SESSAO, d.token)
      } catch {
        /* modo privado: a sessão vale só enquanto a tela não recarregar */
      }
      setOperador(d.operador || null)
      return true
    } catch (e) {
      setErroLogin(
        e?.status === 401
          ? 'Usuário ou senha não conferem.'
          : e?.status === 0
            ? 'O servidor não respondeu. Confira o wi-fi da biblioteca.'
            : e?.message || 'Não deu para entrar.'
      )
      return false
    } finally {
      setEntrando(false)
    }
  }, [])

  const sair = useCallback(async () => {
    try {
      await api.sessao.sair()
    } catch {
      /* sessão local morre de todo jeito */
    }
    encerrarLocal()
    setResultado(null)
    setMovimentos([])
  }, [encerrarLocal])

  /* --- utilidades internas --- */

  const abrirTrabalho = useCallback((texto) => {
    ocupadoRef.current = true
    setOcupado(true)
    setTrabalho(texto)
    setResultado(null)
  }, [])

  const fecharTrabalho = useCallback(() => {
    ocupadoRef.current = false
    setOcupado(false)
    setTrabalho('')
  }, [])

  const anunciarOk = useCallback((r) => {
    somConfirmado()
    vibrarPadrao([45, 40, 45])
    setResultado(r)
  }, [])

  const anunciarRecusa = useCallback((r) => {
    somRecusado()
    vibrarPadrao([160, 70, 160])
    setResultado(r)
  }, [])

  /** Falha que não é 409: rede, sessão, servidor. */
  const tratarFalha = useCallback(
    (e, oQueFalhou) => {
      if (e?.status === 401) {
        encerrarLocal()
        const t = traduzirCodigo('sem_operador')
        anunciarRecusa({ tom: 'erro', titulo: 'Sessão expirada', ...t, linhas: [] })
        return
      }
      if (e?.status === 0) {
        // A regra mais importante da tela: NÃO afirmar que emprestou.
        anunciarRecusa({
          tom: 'incerto',
          titulo: 'Não deu para confirmar',
          frase: `A rede caiu no meio ${oQueFalhou}.`,
          saida: 'Não diga que levou. Confira no PC do balcão antes de repetir.',
          linhas: [],
        })
        return
      }
      anunciarRecusa({
        tom: 'erro',
        titulo: 'Não deu para concluir',
        frase: e?.message || 'O servidor recusou a operação.',
        saida: 'Confira no PC antes de repetir.',
        linhas: [],
      })
    },
    [anunciarRecusa, encerrarLocal]
  )

  /** 409: o vocabulário fechado do §4.3. */
  const tratarRecusa = useCallback(
    (corpo, contexto) => {
      const impedimentos = corpo?.impedimentos || []
      const principal = impedimentos[0] || corpo?.codigo
      const t = traduzirCodigo(principal)
      anunciarRecusa({
        tom: 'erro',
        titulo: contexto === 'devolucao' ? 'Não deu para devolver' : 'Não pode levar',
        ...t,
        motivos: traduzirLista(impedimentos.slice(1)),
        linhas: [],
      })
    },
    [anunciarRecusa]
  )

  const marcarConcluido = (codigo) => {
    if (codigo) concluidos.current.set(String(codigo), Date.now())
  }

  /* --- leitor --- */

  /**
   * Por que o leitor pode estar barrado.
   *
   * QUEM decide é o servidor (`situacao.pode_levar`, e no fim das contas o
   * 409). Isto aqui existe só para dizer POR QUÊ em português — política de
   * empréstimo mora no `LendingBO`, não numa tela de celular.
   */
  function motivosDoLeitor(dados) {
    if (Array.isArray(dados?.situacao?.impedimentos)) return dados.situacao.impedimentos
    const s = dados?.situacao || {}
    const l = dados?.leitor || {}
    const motivos = []
    if (l.status === 'inactive') motivos.push('leitor_inativo')
    if (l.status === 'blocked') motivos.push('leitor_bloqueado')
    if (Number(s.atrasados) > 0) motivos.push('leitor_com_atraso')
    if (Number(s.multas) > 0) motivos.push('multa_em_aberto')
    if (Number(s.limite) > 0 && Number(s.abertos) >= Number(s.limite))
      motivos.push('limite_atingido')
    return motivos
  }

  const fixarLeitorPorId = useCallback(
    async (userId) => {
      if (userId == null) return false
      setCarregandoLeitor(true)
      setBarreira(null)
      try {
        const dados = await api.circulacao.leitor(userId)
        const motivos = motivosDoLeitor(dados)
        // `pode_levar === false` é a única coisa que barra. Ausente, quem
        // decide é o POST — a tela não inventa política.
        if (dados?.situacao?.pode_levar === false) {
          setFicha(null)
          setBarreira({
            leitor: dados.leitor || null,
            situacao: dados.situacao || null,
            motivos: traduzirLista(motivos.length ? motivos : ['leitor_bloqueado']),
          })
          somRecusado()
          vibrarPadrao([160, 70, 160])
          return false
        }
        setFicha(dados)
        setMovimentos([])
        setResultado(null)
        somConfirmado()
        vibrarPadrao(45)
        return true
      } catch (e) {
        if (e?.status === 404) {
          const t = traduzirCodigo('leitor_nao_encontrado')
          anunciarRecusa({ tom: 'erro', titulo: 'Leitor não encontrado', ...t, linhas: [] })
        } else {
          tratarFalha(e, 'ao abrir a ficha do leitor')
        }
        return false
      } finally {
        setCarregandoLeitor(false)
      }
    },
    [anunciarRecusa, tratarFalha]
  )

  const soltarLeitor = useCallback(() => {
    setFicha(null)
    setBarreira(null)
    setResultado(null)
    setMovimentos([])
    concluidos.current.clear()
  }, [])

  const buscarLeitores = useCallback(async (busca) => {
    const texto = String(busca || '').trim()
    if (texto.length < 2) return []
    try {
      const d = await api.circulacao.leitores(texto)
      return d?.leitores || []
    } catch {
      return []
    }
  }, [])

  /** Obras pelo título, cada uma já com os exemplares e o estado. */
  const buscarObras = useCallback(async (busca) => {
    const texto = String(busca || '').trim()
    if (texto.length < 2) return []
    try {
      const d = await api.circulacao.obras(texto)
      return d?.obras || []
    } catch {
      return []
    }
  }, [])

  /** Recarrega a situação depois de um empréstimo, sem segurar a tela. */
  const recarregarFicha = useCallback((userId) => {
    if (userId == null) return
    api.circulacao
      .leitor(userId)
      .then((d) => setFicha((atual) => (idDoLeitor(atual?.leitor) === userId ? d : atual)))
      .catch(() => {
        /* a contagem da faixa fica um bipe atrasada; o próximo POST reconcilia */
      })
  }, [])

  /* --- as duas operações --- */

  const emprestarExemplar = useCallback(
    async (exemplar, { forcarAvisos = false } = {}) => {
      const holdingId = idDoExemplar(exemplar)
      const userId = idDoLeitor(fichaRef.current?.leitor)
      if (holdingId == null || userId == null) return
      abrirTrabalho('Gravando o empréstimo…')
      try {
        const d = await api.circulacao.emprestar({
          holding_id: holdingId,
          user_id: userId,
          forcar_avisos: forcarAvisos,
        })
        const emp = d?.emprestimo || {}
        const tombo = tomboDe(emp) || tomboDe(exemplar)
        const titulo = tituloDe(emp) || tituloDe(exemplar)
        marcarConcluido(tombo)
        setDecisao(null)
        anunciarOk({
          tom: 'ok',
          titulo: 'Levou',
          frase: titulo || `Exemplar ${tombo || holdingId}`,
          saida: emp.previsto_para
            ? `Devolver até ${formatarData(emp.previsto_para)}.`
            : '',
          linhas: [
            tombo && { rotulo: 'Tombo', valor: tombo, mono: true },
            emp.previsto_para && {
              rotulo: 'Devolver até',
              valor: formatarData(emp.previsto_para),
            },
          ].filter(Boolean),
          avisosIgnorados: forcarAvisos ? traduzirLista(decisaoRef.current?.avisos) : [],
        })
        setMovimentos((m) => [
          { chave: `e${holdingId}-${Date.now()}`, tipo: 'saiu', tombo, titulo },
          ...m,
        ])
        recarregarFicha(userId)
      } catch (e) {
        if (e?.status === 409) {
          const corpo = e.corpo || {}
          const impedimentos = corpo.impedimentos || []
          const avisos = corpo.avisos || []
          // Só aviso: passa com confirmação explícita, e a tela precisa dizer
          // O QUE está sendo ignorado antes de reenviar.
          if (!impedimentos.length && avisos.length) {
            setDecisao({
              tipo: 'avisos',
              exemplar,
              avisos,
              motivos: traduzirLista(avisos),
              mensagem: corpo.mensagem || '',
            })
            somRecusado()
            vibrarPadrao(90)
          } else {
            setDecisao(null)
            tratarRecusa(corpo, 'emprestimo')
          }
        } else {
          setDecisao(null)
          tratarFalha(e, 'ao gravar o empréstimo')
        }
      } finally {
        fecharTrabalho()
      }
    },
    [abrirTrabalho, anunciarOk, fecharTrabalho, recarregarFicha, tratarFalha, tratarRecusa]
  )

  const devolverExemplar = useCallback(
    async (exemplar) => {
      const holdingId = idDoExemplar(exemplar)
      if (holdingId == null) return
      abrirTrabalho('Registrando a devolução…')
      try {
        const d = await api.circulacao.devolver({ holding_id: holdingId })
        const dev = d?.devolucao
        const tombo = tomboDe(dev) || tomboDe(exemplar)
        const titulo = tituloDe(dev) || tituloDe(exemplar)
        setDecisao(null)

        // Livro que não estava emprestado não é falha: é informação. Vermelho
        // aqui treinaria o operador a ignorar vermelho.
        if (!dev) {
          anunciarOk({
            tom: 'aviso',
            titulo: 'Já estava na estante',
            frase: titulo || `Exemplar ${tombo || holdingId}`,
            saida: 'Não havia empréstimo aberto para este exemplar — nada mudou.',
            linhas: tombo ? [{ rotulo: 'Tombo', valor: tombo, mono: true }] : [],
          })
          marcarConcluido(tombo)
          return
        }

        const atraso = Number(d?.atraso_dias) || 0
        const multa = d?.multa
        const reserva = d?.reserva
        const linhas = [
          tombo && { rotulo: 'Tombo', valor: tombo, mono: true },
          dev.leitor && { rotulo: 'Devolveu', valor: nomeDe(dev.leitor) || String(dev.leitor) },
          atraso > 0 && {
            rotulo: 'Atraso',
            valor: `${atraso} ${atraso === 1 ? 'dia' : 'dias'}`,
            tom: 'alerta',
          },
        ].filter(Boolean)

        marcarConcluido(tombo)
        anunciarOk({
          tom: multa || reserva ? 'aviso' : 'ok',
          titulo: 'Devolvido',
          frase: titulo || `Exemplar ${tombo || holdingId}`,
          saida: '',
          linhas,
          multa: multa
            ? {
                valor: formatarDinheiro(multa.valor ?? multa),
                dias: atraso,
              }
            : null,
          reserva: reserva
            ? {
                leitor: nomeDe(reserva.leitor || reserva) || 'outro leitor',
              }
            : null,
        })
        setMovimentos((m) => [
          { chave: `d${holdingId}-${Date.now()}`, tipo: 'voltou', tombo, titulo },
          ...m,
        ])
      } catch (e) {
        if (e?.status === 409) {
          setDecisao(null)
          tratarRecusa(e.corpo || {}, 'devolucao')
        } else {
          setDecisao(null)
          tratarFalha(e, 'ao registrar a devolução')
        }
      } finally {
        fecharTrabalho()
      }
    },
    [abrirTrabalho, anunciarOk, fecharTrabalho, tratarFalha, tratarRecusa]
  )

  /* --- o bipe --- */

  /**
   * O caminho de um código, do bipe à frase.
   *
   * Enquanto há trabalho em curso ou decisão aberta, leitura nova é ignorada:
   * é o que faz "o celular espera" ser verdade e não uma promessa da
   * documentação.
   */
  const processar = useCallback(
    async (codigoBruto) => {
      const codigo = String(codigoBruto || '').trim()
      if (!codigo) return
      if (ocupadoRef.current || decisaoRef.current) return

      const t = concluidos.current.get(codigo)
      if (t && Date.now() - t < JANELA_CONCLUIDO) return

      abrirTrabalho('Conferindo…')
      let r
      try {
        // O tombo do acervo migrado é o NUMACERVO, só dígitos como o número do
        // leitor: esperando a carteirinha, "842" é o leitor; depois, o livro.
        const preferir =
          modoRef.current === 'emprestar' && !fichaRef.current ? 'leitor' : 'exemplar'
        r = await api.circulacao.resolver(codigo, preferir)
      } catch (e) {
        tratarFalha(e, 'ao consultar o código')
        fecharTrabalho()
        return
      }
      fecharTrabalho()

      const tipo = r?.tipo || 'desconhecido'

      if (tipo === 'desconhecido') {
        anunciarRecusa({
          tom: 'erro',
          titulo: 'Não reconheci este código',
          frase: `"${codigo}" não é tombo do acervo, ISBN nem carteirinha.`,
          saida: 'Confira se bipou a etiqueta certa ou digite o código à mão.',
          linhas: [],
        })
        return
      }

      if (modoRef.current === 'devolver') {
        if (tipo === 'leitor') {
          anunciarRecusa({
            tom: 'aviso',
            titulo: 'Isto é uma carteirinha',
            frase: 'No modo DEVOLVER quem é bipado é o livro.',
            saida: 'Bipe a etiqueta do exemplar — devolução não precisa do leitor.',
            linhas: [],
          })
          return
        }
        if (tipo === 'tombo') {
          await devolverExemplar(r.exemplar || {})
          return
        }
        // ISBN: o exemplar sem etiqueta impressa, que é o caso comum do acervo
        // migrado. A lista traz o estado de cada cópia; devolver só faz sentido
        // para as que estão fora.
        setDecisao({
          tipo: 'exemplares',
          acao: 'devolver',
          obra: r.obra || null,
          exemplares: r.exemplares || [],
        })
        vibrarPadrao(40)
        return
      }

      /* --- modo emprestar --- */

      if (tipo === 'leitor') {
        const dados = r.leitor || {}
        const id = idDoLeitor(dados)
        if (fichaRef.current && idDoLeitor(fichaRef.current.leitor) !== id) {
          setDecisao({ tipo: 'trocar_leitor', leitor: dados })
          vibrarPadrao(40)
          return
        }
        if (fichaRef.current) return // é o mesmo leitor: nada a fazer
        await fixarLeitorPorId(id)
        return
      }

      if (!fichaRef.current) {
        anunciarRecusa({
          tom: 'aviso',
          titulo: 'Falta dizer quem vai levar',
          frase: 'Identifique o leitor antes de bipar o livro.',
          saida: 'Bipe a carteirinha, digite o número ou procure pelo nome.',
          linhas: [],
        })
        return
      }

      if (tipo === 'tombo') {
        await emprestarExemplar(r.exemplar || {})
        return
      }

      setDecisao({
        tipo: 'exemplares',
        acao: 'emprestar',
        obra: r.obra || null,
        exemplares: r.exemplares || [],
      })
      vibrarPadrao(40)
    },
    [
      abrirTrabalho,
      anunciarRecusa,
      devolverExemplar,
      emprestarExemplar,
      fecharTrabalho,
      fixarLeitorPorId,
      tratarFalha,
    ]
  )

  /* --- respostas às decisões abertas --- */

  const escolherExemplar = useCallback(
    async (exemplar) => {
      const d = decisaoRef.current
      setDecisao(null)
      if (d?.acao === 'devolver') await devolverExemplar(exemplar)
      else await emprestarExemplar(exemplar)
    },
    [devolverExemplar, emprestarExemplar]
  )

  /**
   * O livro achado pela busca por título: segue o caminho do ISBN — a lista
   * dos exemplares, e o operador escolhe o que está na mão.
   */
  const abrirObra = useCallback(
    (obra) => {
      if (!obra || ocupadoRef.current || decisaoRef.current) return
      if (modoRef.current === 'emprestar' && !fichaRef.current) {
        anunciarRecusa({
          tom: 'aviso',
          titulo: 'Falta dizer quem vai levar',
          frase: 'Identifique o leitor antes de escolher o livro.',
          saida: 'Bipe a carteirinha, digite o número ou procure pelo nome.',
          linhas: [],
        })
        return
      }
      setDecisao({
        tipo: 'exemplares',
        acao: modoRef.current === 'devolver' ? 'devolver' : 'emprestar',
        origem: 'titulo',
        obra,
        exemplares: obra.exemplares || [],
      })
      vibrarPadrao(40)
    },
    [anunciarRecusa]
  )

  const confirmarAvisos = useCallback(async () => {
    const d = decisaoRef.current
    if (d?.tipo !== 'avisos') return
    await emprestarExemplar(d.exemplar, { forcarAvisos: true })
  }, [emprestarExemplar])

  const confirmarTrocaDeLeitor = useCallback(async () => {
    const d = decisaoRef.current
    setDecisao(null)
    if (d?.tipo !== 'trocar_leitor') return
    soltarLeitor()
    await fixarLeitorPorId(idDoLeitor(d.leitor))
  }, [fixarLeitorPorId, soltarLeitor])

  const cancelarDecisao = useCallback(() => setDecisao(null), [])

  const trocarModo = useCallback((novo) => {
    setModo(novo)
    setResultado(null)
    setDecisao(null)
    concluidos.current.clear()
  }, [])

  const limparResultado = useCallback(() => setResultado(null), [])
  const limparBarreira = useCallback(() => setBarreira(null), [])

  return {
    // sessão
    operador,
    verificandoSessao,
    entrando,
    erroLogin,
    entrar,
    sair,
    // modo e leitor
    modo,
    trocarModo,
    ficha,
    carregandoLeitor,
    barreira,
    limparBarreira,
    fixarLeitorPorId,
    soltarLeitor,
    buscarLeitores,
    buscarObras,
    abrirObra,
    // bipe
    processar,
    ocupado,
    trabalho,
    resultado,
    limparResultado,
    decisao,
    escolherExemplar,
    confirmarAvisos,
    confirmarTrocaDeLeitor,
    cancelarDecisao,
    movimentos,
  }
}
