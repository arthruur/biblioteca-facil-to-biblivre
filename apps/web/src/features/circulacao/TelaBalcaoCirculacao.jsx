import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, definirSessao } from '../../api/client'
import {
  Aviso,
  Botao,
  Campo,
  IconeBuscar,
  IconeCheck,
  IconeCirculacao,
  IconeCopiar,
  IconeLivro,
  IconeRecarregar,
  Segmentado,
  Selo,
} from '../../components'
import {
  FichaLeitor,
  campo,
  dataBr,
  diasDeAtraso,
  idDoEmprestimo,
  idDoExemplar,
  idDoLeitor,
  leitorDe,
  moeda,
  nomeDoLeitor,
  tituloDaObra,
  tomboDoItem,
} from './FichaLeitor'
import './balcao-circulacao.css'

/**
 * Balcão de circulação — a tela do PC.
 *
 * É a tela que tira o BibLivre do caminho no dia a dia: emprestar, devolver,
 * renovar, ver a ficha do leitor e ver quem está em atraso. Quem está aqui está
 * sentado, com teclado, e com um leitor de código de barras USB que — para o
 * navegador — é um teclado que digita rápido e aperta Enter.
 *
 * UMA BARRA DE COMANDO SÓ
 * -----------------------
 * Um campo, sempre com foco, que aceita tombo, ISBN ou número de leitor — e,
 * quando o que foi digitado tem letra e não é código nenhum, vira busca de
 * livro pelo título. Quem
 * decide o que foi bipado é o servidor (`GET /circulacao/resolver`), nunca o
 * bibliotecário: escolher "tipo" antes de bipar é um passo a mais em cima da
 * operação mais repetida do dia. Bipar com o foco perdido também funciona —
 * qualquer tecla imprimível fora de um campo devolve o foco à barra e entra
 * nela (ver `aoTeclarNaPagina`).
 *
 * AÇÃO SEMPRE EXPLÍCITA
 * ---------------------
 * Diferente do celular (pacote A6), aqui nada acontece por bipar. Bipou tombo
 * emprestado: a tela OFERECE devolver. Bipou tombo livre com leitor na tela:
 * OFERECE emprestar. O botão é a decisão, e a decisão é de quem está sentado
 * olhando a ficha inteira — inclusive a multa e o atraso que o celular não
 * mostra.
 *
 * SEM BANCO NÃO DEGRADA EM SILÊNCIO
 * ---------------------------------
 * `conexao.conectado === false` desabilita a barra e todas as ações, e a tela
 * diz por quê (docs/SPEC_UI.md §7.3). O mesmo vale para o código `sem_banco`
 * vindo do servidor no meio de uma operação.
 *
 * DUPLICAÇÃO DELIBERADA COM O PACOTE A6
 * -------------------------------------
 * A tabela `MOTIVOS` (código de impedimento → frase de balcão) e o tratamento
 * do 409 também são necessários na tela do celular, que é do pacote A6 e tem o
 * seu próprio `useCirculacao.js`. O plano manda duplicar o mínimo em vez de dar
 * dois donos a um arquivo (docs/PLANO_AGENTES.html §3) — e as frases daqui são
 * mais longas de propósito: no PC cabe explicação, no celular não.
 */

/* Atrasos não mudam a cada segundo: 15s é frequente o bastante para o painel
   refletir uma devolução feita no PC ao lado, e leve o bastante para não pesar
   sobre a mesma conexão que atende os celulares bipando. */
const INTERVALO_ATRASOS = 15000

/* Sobreviver ao F5 é decisão da tela: `client.js` guarda o token só em memória
   e diz, no próprio docstring, que quem quiser persistir escolhe onde. Fica em
   `sessionStorage` — morre quando a aba fecha, que é o turno do balcão, e não
   vaza para outro dia nem para outra janela. */
const CHAVE_SESSAO = 'biblio.circulacao.sessao'

/**
 * O vocabulário do 409 traduzido para o balcão (§4.3 do plano).
 *
 * Regra da tradução: dizer o que aconteceu E o que fazer agora. "Leitor
 * bloqueado" sozinho manda o bibliotecário adivinhar; "o desbloqueio é no
 * cadastro do BibLivre" encerra o assunto.
 */
const MOTIVOS = {
  leitor_nao_encontrado:
    'Não existe leitor com esse número. Confira a carteirinha ou busque pelo nome.',
  leitor_inativo:
    'O cadastro deste leitor está inativo. A reativação é feita no cadastro do BibLivre.',
  leitor_bloqueado:
    'Leitor bloqueado. O desbloqueio é feito no cadastro do BibLivre, não por aqui.',
  leitor_com_atraso:
    'Este leitor tem livro atrasado. Receba a devolução antes de emprestar outro.',
  limite_atingido:
    'O leitor já está com o número máximo de livros do tipo de cadastro dele.',
  multa_em_aberto:
    'Há multa em aberto no nome deste leitor. O acerto é feito no BibLivre.',
  exemplar_nao_encontrado:
    'Nenhum exemplar com esse tombo. Confira a etiqueta ou bipe o ISBN da capa — a tela mostra os exemplares da obra.',
  exemplar_emprestado:
    'Este exemplar já está emprestado. Registre a devolução antes de emprestar de novo.',
  exemplar_indisponivel:
    'Exemplar marcado como indisponível no acervo (consulta local, reparo ou baixa).',
  reserva_de_outro_leitor:
    'Há reserva de outro leitor para esta obra. Separe o exemplar para quem reservou.',
  sem_operador:
    'A sessão do operador expirou. Entre de novo — o empréstimo é registrado em nome de quem está no balcão.',
  sem_banco:
    'Sem conexão com o PostgreSQL do BibLivre. Nada pode ser gravado enquanto o banco não voltar.',
  conflito:
    'O exemplar mudou de estado; confira antes de repetir. Alguém pode ter emprestado ou devolvido pela tela do BibLivre agora há pouco.',
}

/** A frase de balcão de um código, com o texto do servidor como reserva. */
function frase(codigo, reserva) {
  return MOTIVOS[codigo] || reserva || `Impedimento não previsto: ${codigo}`
}

/**
 * O corpo de um 409 virado em recado de tela.
 *
 * `conflito` é o único que ganha título e tom próprios: não é erro de quem está
 * no balcão nem impedimento do leitor — é o BibLivre aberto na mesma base, no
 * PC ao lado, tendo mexido no mesmo exemplar entre a consulta e o clique (§1.3
 * do plano). Tratá-lo como falha vermelha treinaria o bibliotecário a insistir;
 * o que ele precisa é conferir e repetir.
 */
function recusa(corpo, tituloPadrao) {
  const dados = corpo || {}
  const impedimentos = dados.impedimentos || []
  const conflito = dados.codigo === 'conflito' || impedimentos.includes('conflito')
  const principal = dados.codigo || impedimentos[0]
  return {
    tom: conflito ? 'alerta' : 'erro',
    titulo: conflito ? 'O exemplar mudou de estado' : tituloPadrao,
    texto: principal
      ? frase(principal, dados.mensagem)
      : dados.mensagem || 'O servidor recusou sem dizer o motivo.',
    motivos: impedimentos.map((c) => frase(c)),
  }
}

const ABAS = [
  ['ficha', 'Ficha do leitor'],
  ['atrasos', 'Atrasos'],
]

const COLUNAS_ATRASO = [
  ['leitor', 'Leitor'],
  ['obra', 'Obra'],
  ['previsto', 'Previsto'],
  ['dias', 'Dias'],
]

function lerToken() {
  try {
    return window.sessionStorage.getItem(CHAVE_SESSAO) || null
  } catch {
    return null
  }
}

function gravarToken(token) {
  try {
    if (token) window.sessionStorage.setItem(CHAVE_SESSAO, token)
    else window.sessionStorage.removeItem(CHAVE_SESSAO)
  } catch {
    /* navegador com armazenamento bloqueado: a sessão vive só nesta carga */
  }
}

function agora() {
  return new Date().toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function TelaBalcaoCirculacao({ conexao, aoAbrirBanco }) {
  /* --- sessão do operador --- */
  const [operador, setOperador] = useState(null)
  const [verificandoSessao, setVerificandoSessao] = useState(true)

  /* --- barra de comando --- */
  const [codigo, setCodigo] = useState('')
  const [resolvendo, setResolvendo] = useState(false)
  const campoRef = useRef(null)

  /* --- atendimento --- */
  const [ficha, setFicha] = useState(null)
  const [carregandoFicha, setCarregandoFicha] = useState(false)
  const [pendente, setPendente] = useState(null)
  const [escolha, setEscolha] = useState(null)
  const [confirmacao, setConfirmacao] = useState(null)
  const [movimentos, setMovimentos] = useState([])
  const [ocupado, setOcupado] = useState('')

  /* --- recados --- */
  const [erro, setErro] = useState(null)
  const [recado, setRecado] = useState('')

  /* --- busca de leitor por nome --- */
  const [buscaLeitor, setBuscaLeitor] = useState('')
  const [achados, setAchados] = useState(null)

  /* --- busca de livro por título --- */
  const [buscaLivro, setBuscaLivro] = useState('')
  const [obrasAchadas, setObrasAchadas] = useState(null)

  /* --- atrasos --- */
  const [aba, setAba] = useState('atrasos')
  const [atrasos, setAtrasos] = useState(null)
  const [erroAtrasos, setErroAtrasos] = useState('')
  const [buscaAtrasos, setBuscaAtrasos] = useState('')
  const [ordem, setOrdem] = useState({ coluna: 'dias', desc: true })
  const assinaturaRef = useRef('')

  /* --- pareamento do celular --- */
  const [enderecoCelular, setEnderecoCelular] = useState('')
  const [copiado, setCopiado] = useState(false)

  const bancoVerificando = !conexao || conexao.bruto == null
  const semBanco = !bancoVerificando && !conexao.conectado
  const liberado = !!operador && !!conexao?.conectado

  const leitorId = idDoLeitor(ficha?.leitor)

  const focar = useCallback(() => {
    campoRef.current?.focus()
  }, [])

  /* ---------------------------------------------------------------- *
   * Sessão
   * ---------------------------------------------------------------- */

  useEffect(() => {
    let vivo = true
    const guardado = lerToken()
    if (guardado) definirSessao(guardado)
    api.sessao
      .atual()
      .then((d) => {
        if (vivo) setOperador(d?.operador || null)
      })
      .catch(() => {
        if (!vivo) return
        definirSessao(null)
        gravarToken(null)
        setOperador(null)
      })
      .finally(() => {
        if (vivo) setVerificandoSessao(false)
      })
    return () => {
      vivo = false
    }
  }, [])

  const sair = async () => {
    try {
      await api.sessao.sair()
    } catch {
      /* o servidor pode já ter esquecido o token; o que importa é a tela */
    }
    definirSessao(null)
    gravarToken(null)
    setOperador(null)
    setFicha(null)
    setPendente(null)
    setEscolha(null)
    setMovimentos([])
  }

  /**
   * 401 em qualquer chamada derruba a sessão da tela.
   *
   * Sem isso o operador continuaria vendo a tela cheia e cada ação falharia em
   * silêncio — e o empréstimo, se enfim gravasse, sairia em nome de ninguém.
   */
  const tratarFalha = useCallback((e, prefixo) => {
    if (e?.name === 'AbortError') return
    if (e?.status === 401) {
      definirSessao(null)
      gravarToken(null)
      setOperador(null)
      setErro({ titulo: 'Sessão encerrada', texto: frase('sem_operador') })
      return
    }
    const corpo = e?.corpo || {}
    if (corpo.codigo && MOTIVOS[corpo.codigo]) {
      setErro({ titulo: prefixo, texto: frase(corpo.codigo, corpo.mensagem) })
      return
    }
    setErro({
      titulo: prefixo,
      texto:
        e?.status === 0
          ? 'O servidor do BiblioFácil não respondeu. Nada foi gravado — confira a rede e repita.'
          : e?.message || 'Erro não identificado.',
    })
  }, [])

  /* O endereço que o celular abre é o do servidor (IP da rede, não o
     `localhost` que este PC pode estar usando), já na rota do balcão. */
  useEffect(() => {
    let vivo = true
    api.sistema
      .info()
      .then((d) => {
        if (vivo && d?.server_url) {
          setEnderecoCelular(`${d.server_url.replace(/\/+$/, '')}/circulacao`)
        }
      })
      .catch(() => {
        /* sem o endereço a tela só não mostra o QR; o balcão segue */
      })
    return () => {
      vivo = false
    }
  }, [])

  const copiarEndereco = () => {
    if (!enderecoCelular) return
    navigator.clipboard?.writeText(enderecoCelular)
    setCopiado(true)
    window.setTimeout(() => setCopiado(false), 1500)
  }

  /* ---------------------------------------------------------------- *
   * Leitor e ficha
   * ---------------------------------------------------------------- */

  const carregarFicha = useCallback(
    async (userId) => {
      if (userId == null) return null
      setCarregandoFicha(true)
      try {
        const d = await api.circulacao.leitor(userId)
        setFicha(d)
        setAba('ficha')
        return d
      } catch (e) {
        tratarFalha(e, 'Não deu para abrir a ficha do leitor')
        return null
      } finally {
        setCarregandoFicha(false)
      }
    },
    [tratarFalha]
  )

  const recarregarFicha = useCallback(async () => {
    if (leitorId == null) return
    await carregarFicha(leitorId)
  }, [leitorId, carregarFicha])

  const encerrarAtendimento = () => {
    setFicha(null)
    setAchados(null)
    setBuscaLeitor('')
    setConfirmacao(null)
    setErro(null)
    setAba('atrasos')
    focar()
  }

  const buscarLeitores = async () => {
    const busca = buscaLeitor.trim()
    if (!busca || !liberado) return
    setOcupado('busca')
    try {
      const d = await api.circulacao.leitores(busca)
      setAchados(d?.leitores || [])
    } catch (e) {
      tratarFalha(e, 'Não deu para buscar o leitor')
    } finally {
      setOcupado('')
    }
  }

  /**
   * Livro pelo título: o caminho de quem não tem etiqueta legível nem ISBN na
   * capa. Uma obra só já abre a escolha do exemplar; várias viram lista.
   */
  const buscarLivros = async (termo = buscaLivro) => {
    const busca = String(termo || '').trim()
    if (busca.length < 2 || !liberado) return
    setOcupado('busca-livro')
    setErro(null)
    try {
      const d = await api.circulacao.obras(busca)
      const obras = d?.obras || []
      setPendente(null)
      if (obras.length === 1) {
        setObrasAchadas(null)
        setEscolha({ obra: obras[0], exemplares: obras[0].exemplares || [], origem: 'titulo' })
      } else {
        setEscolha(null)
        setObrasAchadas({ busca, obras })
      }
    } catch (e) {
      tratarFalha(e, 'Não deu para buscar o livro')
    } finally {
      setOcupado('')
    }
  }

  /* ---------------------------------------------------------------- *
   * Atrasos — polling no padrão do balcão de captura
   * ---------------------------------------------------------------- */

  /**
   * `TelaBalcao.jsx` compara `versao` e só troca o estado quando ela muda. A
   * rota de pendências não promete esse contador (§4.2 do plano), então a
   * assinatura é derivada da própria resposta: enquanto ela não muda, o React
   * não re-renderiza a tabela debaixo da mão de quem está lendo.
   */
  const carregarAtrasos = useCallback(
    async (signal) => {
      if (!operador || !conexao?.conectado) return
      try {
        const d = await api.circulacao.pendencias('atrasados', signal)
        setErroAtrasos('')
        const itens = d?.itens || []
        const assinatura =
          d?.versao != null
            ? `v${d.versao}`
            : `${d?.total ?? itens.length}|${itens
                .map((i) => `${idDoEmprestimo(i) ?? idDoExemplar(i)}:${diasDeAtraso(i)}`)
                .join(',')}`
        if (assinatura === assinaturaRef.current) return
        assinaturaRef.current = assinatura
        setAtrasos(d)
      } catch (e) {
        if (e?.name === 'AbortError') return
        if (e?.status === 401) {
          tratarFalha(e, 'Sessão encerrada')
          return
        }
        setErroAtrasos(e?.message || 'não deu para ler os atrasos')
      }
    },
    [operador, conexao?.conectado, tratarFalha]
  )

  useEffect(() => {
    if (!operador || !conexao?.conectado) return undefined
    const ctrl = new AbortController()
    carregarAtrasos(ctrl.signal)
    const t = setInterval(() => carregarAtrasos(ctrl.signal), INTERVALO_ATRASOS)
    return () => {
      ctrl.abort()
      clearInterval(t)
    }
  }, [operador, conexao?.conectado, carregarAtrasos])

  /** Depois de gravar, a lista de atrasos está velha: força a próxima leitura. */
  const relerAtrasos = useCallback(() => {
    assinaturaRef.current = ''
    carregarAtrasos()
  }, [carregarAtrasos])

  /* ---------------------------------------------------------------- *
   * Barra de comando
   * ---------------------------------------------------------------- */

  const abrirExemplar = useCallback(
    async (holdingId) => {
      if (holdingId == null) return
      setOcupado(`exemplar:${holdingId}`)
      try {
        const d = await api.circulacao.exemplar(holdingId)
        setEscolha(null)
        setPendente({
          holding_id: holdingId,
          exemplar: d?.exemplar || null,
          obra: d?.obra || null,
          emprestimo: d?.emprestimo || null,
        })
      } catch (e) {
        tratarFalha(e, 'Não deu para abrir o exemplar')
      } finally {
        setOcupado('')
        focar()
      }
    },
    [tratarFalha, focar]
  )

  const enviarCodigo = async (evento) => {
    evento?.preventDefault()
    const bruto = codigo.trim()
    if (!bruto || !liberado || resolvendo) return
    setResolvendo(true)
    setErro(null)
    setRecado('')
    try {
      const r = await api.circulacao.resolver(bruto)
      setCodigo('')
      if (r?.tipo === 'leitor') {
        setEscolha(null)
        const id = idDoLeitor(r.leitor)
        if (id == null) {
          setErro({
            titulo: 'Leitor sem número',
            texto: frase('leitor_nao_encontrado'),
          })
        } else {
          await carregarFicha(id)
        }
      } else if (r?.tipo === 'tombo') {
        setEscolha(null)
        setObrasAchadas(null)
        setPendente({
          holding_id: idDoExemplar(r.exemplar) ?? idDoExemplar(r),
          exemplar: r.exemplar || null,
          obra: r.obra || null,
          emprestimo: r.emprestimo || null,
          /* O tombo migrado é o NUMACERVO, só dígitos: o mesmo número pode
             ser de um leitor. A tela mostra o livro e oferece a ficha. */
          tambemLeitor: r.tambem_leitor || null,
        })
      } else if (r?.tipo === 'isbn') {
        /* Livro sem etiqueta impressa é o caso comum do acervo migrado (§1.1
           do plano): bipar o ISBN da capa devolve os exemplares da obra, e
           escolher qual saiu da estante é trabalho do bibliotecário. */
        setPendente(null)
        setObrasAchadas(null)
        setEscolha({ obra: r.obra || null, exemplares: r.exemplares || [] })
      } else if (/\p{L}/u.test(bruto)) {
        /* Tem letra e não é código nenhum: é alguém digitando o título. */
        setBuscaLivro(bruto)
        await buscarLivros(bruto)
      } else {
        setErro({
          titulo: `Não reconheci "${bruto}"`,
          texto:
            'Não é tombo, ISBN nem número de leitor conhecido. Confira os dígitos, ou busque o leitor pelo nome e o livro pelo título no atendimento.',
        })
      }
    } catch (e) {
      tratarFalha(e, 'Não deu para consultar este código')
    } finally {
      setResolvendo(false)
      focar()
    }
  }

  /**
   * Bipar com o foco perdido não pode perder o bipe.
   *
   * O leitor USB digita rápido demais para o bibliotecário perceber que clicou
   * num botão antes. Qualquer tecla imprimível fora de um campo devolve o foco
   * à barra E entra nela — se só chamássemos `focus()`, o primeiro dígito do
   * tombo se perderia.
   */
  useEffect(() => {
    if (!liberado) return undefined
    const aoTeclarNaPagina = (e) => {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName)) return
      if (e.key === 'Escape') {
        setPendente(null)
        setEscolha(null)
        setObrasAchadas(null)
        setConfirmacao(null)
        setErro(null)
        focar()
        return
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key.length !== 1) return
      e.preventDefault()
      setCodigo((c) => c + e.key)
      focar()
    }
    document.addEventListener('keydown', aoTeclarNaPagina)
    return () => document.removeEventListener('keydown', aoTeclarNaPagina)
  }, [liberado, focar])

  useEffect(() => {
    if (liberado) focar()
  }, [liberado, focar])

  /* ---------------------------------------------------------------- *
   * Operações — cada uma espera a resposta do servidor e só então afirma
   * que aconteceu. A tela não tem estado próprio de verdade.
   * ---------------------------------------------------------------- */

  const registrar = (movimento) =>
    setMovimentos((atuais) =>
      [{ ...movimento, hora: agora() }, ...atuais].slice(0, 12)
    )

  const tituloDoPendente = () => tituloDaObra(pendente?.obra || pendente?.exemplar || {})
  const tomboDoPendente = () => tomboDoItem(pendente?.exemplar || {})

  const emprestar = async (holdingId, forcar = false) => {
    if (holdingId == null || !liberado) return
    if (leitorId == null) {
      setErro({
        titulo: 'Falta o leitor',
        texto:
          'Identifique o leitor antes de emprestar: bipe a carteirinha, digite o número dele na barra ou busque pelo nome.',
      })
      return
    }
    setOcupado('emprestimo')
    setErro(null)
    try {
      const r = await api.circulacao.emprestar({
        holding_id: holdingId,
        user_id: leitorId,
        forcar_avisos: forcar,
      })
      const emp = r?.emprestimo || {}
      const prazo = campo(emp, 'previsto_para')
      registrar({
        tipo: 'emprestimo',
        titulo:
          tituloDaObra(emp) !== 'sem título' ? tituloDaObra(emp) : tituloDoPendente(),
        tombo: campo(emp, 'tombo') || tomboDoPendente(),
        detalhe: `para ${nomeDoLeitor(ficha?.leitor)}${
          prazo ? ` · devolver até ${dataBr(prazo)}` : ''
        }`,
      })
      setRecado(
        prazo ? `Emprestado — devolver até ${dataBr(prazo)}.` : 'Emprestado.'
      )
      setPendente(null)
      setConfirmacao(null)
      await recarregarFicha()
      relerAtrasos()
    } catch (e) {
      if (e?.status === 409) {
        const corpo = e.corpo || {}
        const impedimentos = corpo.impedimentos || []
        const avisos = corpo.avisos || []
        /* Impedimento barra; aviso passa com confirmação explícita — e a tela
           precisa dizer O QUE está sendo ignorado (§4.3 do plano). */
        if (!impedimentos.length && avisos.length && !forcar) {
          setConfirmacao({ holdingId, avisos, mensagem: corpo.mensagem })
        } else {
          setConfirmacao(null)
          setErro(recusa(corpo, 'Empréstimo não registrado'))
        }
      } else {
        tratarFalha(e, 'Empréstimo não registrado')
      }
    } finally {
      setOcupado('')
      focar()
    }
  }

  const devolver = async ({ lendingId = null, holdingId = null }, item = null) => {
    if (!liberado) return
    setOcupado(`devolver:${lendingId ?? holdingId}`)
    setErro(null)
    try {
      const r = await api.circulacao.devolver({
        holding_id: holdingId,
        lending_id: lendingId,
      })
      const dev = r?.devolucao || {}
      const dias = Number(r?.atraso_dias || 0)
      const partes = []
      if (dias > 0) partes.push(`${dias} ${dias === 1 ? 'dia' : 'dias'} de atraso`)
      if (r?.multa) {
        partes.push(`multa de ${moeda(campo(r.multa, 'valor', 'multa', 'total'))}`)
      }
      if (r?.reserva) {
        partes.push(
          `reserva pendente — separe para ${nomeDoLeitor(leitorDe(r.reserva))}`
        )
      }
      registrar({
        tipo: 'devolucao',
        titulo:
          tituloDaObra(dev) !== 'sem título'
            ? tituloDaObra(dev)
            : tituloDaObra(item || pendente?.obra || pendente?.exemplar || {}),
        tombo: campo(dev, 'tombo') || tomboDoItem(item || pendente?.exemplar || {}),
        detalhe: partes.join(' · ') || 'sem multa e sem reserva',
      })
      setRecado(partes.length ? `Devolvido — ${partes.join(' · ')}.` : 'Devolvido.')
      setPendente(null)
      await recarregarFicha()
      relerAtrasos()
    } catch (e) {
      if (e?.status === 409) {
        setErro(recusa(e.corpo, 'Devolução não registrada'))
      } else {
        tratarFalha(e, 'Devolução não registrada')
      }
    } finally {
      setOcupado('')
      focar()
    }
  }

  const renovar = async (lendingId, item = null) => {
    if (lendingId == null || !liberado) return
    setOcupado(`renovar:${lendingId}`)
    setErro(null)
    try {
      const r = await api.circulacao.renovar(lendingId)
      const emp = r?.emprestimo || {}
      const prazo = campo(emp, 'previsto_para')
      registrar({
        tipo: 'renovacao',
        titulo:
          tituloDaObra(emp) !== 'sem título' ? tituloDaObra(emp) : tituloDaObra(item || {}),
        tombo: campo(emp, 'tombo') || tomboDoItem(item || {}),
        detalhe: prazo ? `novo prazo: ${dataBr(prazo)}` : 'renovado',
      })
      setRecado(prazo ? `Renovado — devolver até ${dataBr(prazo)}.` : 'Renovado.')
      await recarregarFicha()
      relerAtrasos()
    } catch (e) {
      if (e?.status === 409) {
        setErro(recusa(e.corpo, 'Renovação recusada'))
      } else {
        tratarFalha(e, 'Renovação recusada')
      }
    } finally {
      setOcupado('')
      focar()
    }
  }

  /* ---------------------------------------------------------------- *
   * Atrasos: filtro e ordenação, no cliente
   * ---------------------------------------------------------------- */

  const itensAtraso = useMemo(() => {
    const base = atrasos?.itens || []
    const busca = buscaAtrasos.trim().toLowerCase()
    const filtrados = busca
      ? base.filter((i) =>
          `${nomeDoLeitor(leitorDe(i))} ${tituloDaObra(i)} ${tomboDoItem(i)}`
            .toLowerCase()
            .includes(busca)
        )
      : base
    const chave = (i) => {
      if (ordem.coluna === 'leitor') return nomeDoLeitor(leitorDe(i)).toLowerCase()
      if (ordem.coluna === 'obra') return tituloDaObra(i).toLowerCase()
      if (ordem.coluna === 'previsto')
        return String(campo(i, 'previsto_para', 'expected_return_date') || '')
      return diasDeAtraso(i)
    }
    return [...filtrados].sort((a, b) => {
      const va = chave(a)
      const vb = chave(b)
      const cmp = va < vb ? -1 : va > vb ? 1 : 0
      return ordem.desc ? -cmp : cmp
    })
  }, [atrasos, buscaAtrasos, ordem])

  const ordenarPor = (coluna) =>
    setOrdem((o) =>
      o.coluna === coluna
        ? { coluna, desc: !o.desc }
        : { coluna, desc: coluna === 'dias' }
    )

  /* ---------------------------------------------------------------- *
   * Render
   * ---------------------------------------------------------------- */

  if (verificandoSessao) {
    return (
      <div className="bcirc-entrada">
        <p className="microrrotulo">Verificando a sessão…</p>
      </div>
    )
  }

  /* Sem operador a tela é só o login: registrar empréstimo em nome de ninguém
     é pior do que não registrar (§1.4 do plano — `created_by` passa a ser o
     operador de verdade). */
  if (!operador) {
    return <Entrada aoEntrar={setOperador} mensagem={erro?.texto} />
  }

  const total = atrasos?.total ?? (atrasos?.itens || []).length

  return (
    <div className="bcirc">
      <header className="bcirc__topo">
        <div className="bcirc__topo-esq">
          <h1 className="bcirc__titulo">Balcão de circulação</h1>
          <span className="bcirc__sub">
            emprestar, devolver, renovar e ver quem está devendo
          </span>
        </div>
        <div className="bcirc__topo-dir">
          <div className="bcirc__operador">
            <span className="microrrotulo">no balcão</span>
            <span className="bcirc__operador-nome">
              {operador.nome || operador.login}
            </span>
          </div>
          <Botao variante="secundario" tamanho="pequeno" onClick={sair}>
            Sair
          </Botao>
        </div>
      </header>

      <form className="bcirc__barra" onSubmit={enviarCodigo}>
        <div className="bcirc-cmd">
          <IconeCirculacao tamanho={18} className="bcirc-cmd__icone" />
          <input
            ref={campoRef}
            className="bcirc-cmd__campo"
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            onBlur={() => {
              /* O leitor USB precisa do campo com foco. Perdê-lo é sempre
                 acidental num balcão — devolvemos no quadro seguinte, depois
                 que o clique no botão já foi processado, e só se o foco tiver
                 caído no corpo da página. */
              window.setTimeout(() => {
                if (document.activeElement === document.body) focar()
              }, 0)
            }}
            placeholder="bipe ou digite: tombo, ISBN, número do leitor ou título"
            aria-label="Tombo, ISBN, número do leitor ou título do livro"
            autoComplete="off"
            spellCheck={false}
            disabled={!liberado}
          />
        </div>
        <Botao variante="primario" type="submit" disabled={!liberado || !codigo.trim()}>
          {resolvendo ? 'Consultando…' : 'Consultar'}
        </Botao>
        <span className="bcirc-cmd__dica">
          o leitor USB digita e aperta Enter · Esc limpa o atendimento
        </span>
      </form>

      {bancoVerificando && (
        <div className="bcirc__faixa">
          <span>Verificando a conexão com o PostgreSQL do BibLivre…</span>
        </div>
      )}

      {semBanco && (
        <div className="bcirc__faixa bcirc__faixa--alerta">
          <strong>Sem banco.</strong>
          <span>
            {frase('sem_banco')} As ações estão desabilitadas de propósito — a
            circulação só existe gravada.
          </span>
          {aoAbrirBanco && (
            <span className="bcirc__faixa-fim">
              <Botao variante="secundario" tamanho="pequeno" onClick={aoAbrirBanco}>
                Conectar ao PostgreSQL
              </Botao>
            </span>
          )}
        </div>
      )}

      {recado && (
        <div className="bcirc__faixa bcirc__faixa--ok">
          <IconeCheck tamanho={14} />
          <span>{recado}</span>
          <span className="bcirc__faixa-fim">
            <Botao variante="fantasma" tamanho="pequeno" onClick={() => setRecado('')}>
              dispensar
            </Botao>
          </span>
        </div>
      )}

      <div className="bcirc__corpo">
        {/* ---------- Região 1: ATENDIMENTO ---------- */}
        <div className="bcirc__coluna">
          <section className="bcirc-bloco moldura">
            <div className="bcirc-bloco__cabecalho">
              <span className="microrrotulo">Atendimento</span>
              {ficha && (
                <Botao
                  variante="fantasma"
                  tamanho="pequeno"
                  onClick={encerrarAtendimento}
                >
                  Encerrar
                </Botao>
              )}
            </div>

            {ficha ? (
              <div className="bcirc-leitor">
                <span className="bcirc-leitor__nome">{nomeDoLeitor(ficha.leitor)}</span>
                <span className="bcirc-leitor__meta">
                  {[
                    leitorId != null ? `nº ${leitorId}` : null,
                    campo(ficha.leitor, 'matricula', 'documento'),
                    campo(ficha.leitor, 'tipo', 'tipo_nome'),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                <ResumoSituacao situacao={ficha.situacao} />
              </div>
            ) : (
              <>
                <p className="bcirc-bloco__vazio">
                  Nenhum leitor em atendimento. Bipe a carteirinha, digite o
                  número na barra de comando ou busque pelo nome.
                </p>
                <div className="bcirc-busca">
                  <input
                    className="bcirc-busca__campo"
                    value={buscaLeitor}
                    onChange={(e) => setBuscaLeitor(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        buscarLeitores()
                      }
                    }}
                    placeholder="buscar leitor pelo nome"
                    aria-label="Buscar leitor pelo nome"
                    disabled={!liberado}
                  />
                  <Botao
                    variante="secundario"
                    onClick={buscarLeitores}
                    disabled={!liberado || !buscaLeitor.trim() || ocupado === 'busca'}
                  >
                    <IconeBuscar tamanho={13} />
                    {ocupado === 'busca' ? '…' : 'Buscar'}
                  </Botao>
                </div>
                {achados && achados.length === 0 && (
                  <p className="bcirc-bloco__vazio">
                    Nenhum leitor com esse nome. O cadastro de leitor continua
                    sendo feito no BibLivre.
                  </p>
                )}
                {achados && achados.length > 0 && (
                  <div className="bcirc-lista">
                    {achados.map((l, i) => (
                      <button
                        key={idDoLeitor(l) ?? `leitor-${i}`}
                        className="bcirc-lista__item"
                        onClick={() => {
                          setAchados(null)
                          setBuscaLeitor('')
                          carregarFicha(idDoLeitor(l))
                        }}
                      >
                        <span className="bcirc-lista__nome">{nomeDoLeitor(l)}</span>
                        <span className="bcirc-lista__meta">
                          nº {idDoLeitor(l) ?? '—'}
                          {campo(l, 'tipo', 'tipo_nome')
                            ? ` · ${campo(l, 'tipo', 'tipo_nome')}`
                            : ''}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}

            <div className="bcirc-busca">
              <input
                className="bcirc-busca__campo"
                value={buscaLivro}
                onChange={(e) => setBuscaLivro(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    buscarLivros()
                  }
                }}
                placeholder="buscar livro pelo título ou autor"
                aria-label="Buscar livro pelo título ou autor"
                disabled={!liberado}
              />
              <Botao
                variante="secundario"
                onClick={() => buscarLivros()}
                disabled={
                  !liberado || buscaLivro.trim().length < 2 || ocupado === 'busca-livro'
                }
              >
                <IconeLivro tamanho={13} />
                {ocupado === 'busca-livro' ? '…' : 'Buscar'}
              </Botao>
            </div>

            {obrasAchadas && (
              <ObrasAchadas
                achadas={obrasAchadas}
                aoEscolher={(o) => {
                  setObrasAchadas(null)
                  setEscolha({ obra: o, exemplares: o.exemplares || [], origem: 'titulo' })
                }}
                aoFechar={() => setObrasAchadas(null)}
              />
            )}

            {erro && (
              <Aviso tom={erro.tom || 'erro'} icone="⚠" titulo={erro.titulo}>
                <p>{erro.texto}</p>
                {erro.motivos?.length > 1 && (
                  <ul className="bcirc-motivos">
                    {erro.motivos.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ul>
                )}
                <div style={{ marginTop: 'var(--e2)' }}>
                  <Botao
                    variante="fantasma"
                    tamanho="pequeno"
                    onClick={() => setErro(null)}
                  >
                    Dispensar
                  </Botao>
                </div>
              </Aviso>
            )}

            {confirmacao && (
              <Aviso tom="alerta" icone="⚠" titulo="Passa, mas com ressalva">
                <p>
                  {confirmacao.mensagem ||
                    'O empréstimo pode ser registrado, mas há aviso a ignorar:'}
                </p>
                <ul className="bcirc-motivos">
                  {confirmacao.avisos.map((a, i) => (
                    <li key={typeof a === 'string' ? a : a.codigo || `aviso-${i}`}>
                      {typeof a === 'string' ? frase(a) : frase(a.codigo, a.mensagem)}
                    </li>
                  ))}
                </ul>
                <div className="bcirc-item__acoes">
                  <Botao
                    variante="primario"
                    tamanho="pequeno"
                    onClick={() => emprestar(confirmacao.holdingId, true)}
                    disabled={ocupado === 'emprestimo'}
                  >
                    Emprestar mesmo assim
                  </Botao>
                  <Botao
                    variante="secundario"
                    tamanho="pequeno"
                    onClick={() => setConfirmacao(null)}
                  >
                    Não emprestar
                  </Botao>
                </div>
              </Aviso>
            )}

            {escolha && (
              <EscolhaDeExemplar
                escolha={escolha}
                ocupado={ocupado}
                desabilitado={!liberado}
                aoEscolher={abrirExemplar}
                aoFechar={() => setEscolha(null)}
              />
            )}

            {pendente && (
              <ItemEmMaos
                pendente={pendente}
                ficha={ficha}
                ocupado={ocupado}
                desabilitado={!liberado}
                aoEmprestar={() => emprestar(pendente.holding_id)}
                aoDevolver={() =>
                  devolver(
                    {
                      lendingId: idDoEmprestimo(pendente.emprestimo || {}),
                      holdingId: pendente.holding_id,
                    },
                    pendente.obra || pendente.exemplar
                  )
                }
                aoRenovar={() =>
                  renovar(
                    idDoEmprestimo(pendente.emprestimo || {}),
                    pendente.obra || pendente.exemplar
                  )
                }
                aoAbrirLeitor={carregarFicha}
                aoDispensar={() => {
                  setPendente(null)
                  focar()
                }}
              />
            )}
          </section>

          <section className="bcirc-bloco moldura">
            <span className="microrrotulo">Neste atendimento</span>
            {movimentos.length === 0 ? (
              <p className="bcirc-bloco__vazio">
                O que for emprestado, devolvido ou renovado nesta tela aparece
                aqui, com a hora — é o comprovante do turno.
              </p>
            ) : (
              <div className="bcirc-recibo">
                {movimentos.map((m, i) => (
                  <div className="bcirc-recibo__linha" key={`${m.hora}-${i}`}>
                    <Selo
                      tom={
                        m.tipo === 'emprestimo'
                          ? 'acento'
                          : m.tipo === 'devolucao'
                            ? 'existente'
                            : 'neutro'
                      }
                    >
                      {m.tipo === 'emprestimo'
                        ? 'saiu'
                        : m.tipo === 'devolucao'
                          ? 'voltou'
                          : 'renovou'}
                    </Selo>
                    <span className="bcirc-recibo__obra">
                      {m.titulo}
                      {m.tombo && m.tombo !== '—' ? ` · ${m.tombo}` : ''}
                    </span>
                    <span className="bcirc-recibo__hora">{m.hora}</span>
                    {m.detalhe && (
                      <span className="bcirc-recibo__detalhe">{m.detalhe}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {enderecoCelular && (
            <section className="bcirc-bloco moldura bcirc-parear">
              <span className="microrrotulo">Abrir no celular</span>
              <div className="bcirc-parear__corpo">
                <div className="bcirc-parear__qr">
                  <img
                    src="/api/qrcode?tela=circulacao"
                    alt="QR code para abrir a circulação no celular"
                  />
                </div>
                <p className="bcirc-bloco__vazio">
                  Aponte a câmera do celular para o QR: ele abre direto o balcão
                  de circulação, para emprestar e devolver bipando. Aceite o
                  certificado na primeira vez.
                </p>
              </div>
              <div className="bcirc-parear__url">
                <code className="mono">{enderecoCelular}</code>
                <Botao variante="fantasma" tamanho="pequeno" onClick={copiarEndereco}>
                  <IconeCopiar tamanho={12} />
                  {copiado ? 'Copiado' : 'Copiar'}
                </Botao>
              </div>
            </section>
          )}
        </div>

        {/* ---------- Regiões 2 e 3: FICHA DO LEITOR e ATRASOS ----------
            As duas dividem a coluna larga: são as duas leituras longas da
            tela, e nenhuma das duas cabe embaixo da outra sem empurrar a
            barra de comando para fora do campo de visão. A aba troca sozinha
            para a ficha quando um leitor é identificado — que é o momento em
            que a pergunta muda de "quem está devendo?" para "o que este aqui
            está com a gente?". */}
        <div className="bcirc__coluna">
          <Segmentado
            opcoes={[ABAS[0], [ABAS[1][0], total ? `Atrasos (${total})` : 'Atrasos']]}
            valor={aba}
            aoMudar={setAba}
            rotulo="O que ver ao lado do atendimento"
          />

          {aba === 'ficha' ? (
            <FichaLeitor
              ficha={ficha}
              carregando={carregandoFicha}
              desabilitado={!liberado}
              ocupado={ocupado}
              aoRenovar={renovar}
              aoDevolver={devolver}
              aoAtualizar={ficha ? recarregarFicha : undefined}
              aoEncerrar={ficha ? encerrarAtendimento : undefined}
            />
          ) : (
            <Atrasos
              itens={itensAtraso}
              total={total}
              carregado={!!atrasos}
              erro={erroAtrasos}
              busca={buscaAtrasos}
              aoBuscar={setBuscaAtrasos}
              ordem={ordem}
              aoOrdenar={ordenarPor}
              desabilitado={!liberado}
              ocupado={ocupado}
              aoAbrirLeitor={carregarFicha}
              aoDevolver={devolver}
              aoAtualizar={relerAtrasos}
            />
          )}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Entrada do operador
 * ------------------------------------------------------------------ */

/**
 * Login contra a tabela `logins` do próprio BibLivre (§1.4 do plano).
 *
 * É a única coisa na tela enquanto não houver sessão: é o `logins.id` real que
 * vai para `lendings.created_by`, e sem ele o empréstimo sairia em nome do
 * admin do instalador — que é exatamente o que o dia a dia do balcão não pode
 * ter.
 */
function Entrada({ aoEntrar, mensagem }) {
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState(mensagem || '')
  const [entrando, setEntrando] = useState(false)

  const enviar = async (e) => {
    e.preventDefault()
    if (!usuario.trim() || !senha) return
    setEntrando(true)
    setErro('')
    try {
      const d = await api.sessao.entrar(usuario.trim(), senha)
      definirSessao(d?.token || null)
      gravarToken(d?.token || null)
      aoEntrar(d?.operador || null)
    } catch (err) {
      setErro(
        err?.status === 401
          ? 'Usuário ou senha não conferem com o cadastro do BibLivre.'
          : err?.status === 0
            ? 'O servidor do BiblioFácil não respondeu.'
            : err?.message || 'Não deu para entrar.'
      )
    } finally {
      setEntrando(false)
    }
  }

  return (
    <div className="bcirc-entrada">
      <form className="bcirc-entrada__caixa moldura" onSubmit={enviar}>
        <div>
          <h1 className="bcirc-entrada__titulo">
            <IconeLivro tamanho={20} /> Balcão de circulação
          </h1>
          <p className="bcirc-entrada__texto">
            Entre com o mesmo usuário e senha do BibLivre. É esse nome que fica
            registrado em cada empréstimo — por isso a tela não abre sem ele.
          </p>
        </div>

        <div className="bcirc-entrada__campos">
          <Campo
            rotulo="Usuário"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            autoFocus
            autoComplete="username"
          />
          <Campo
            rotulo="Senha"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="current-password"
          />
        </div>

        {erro && <p className="bcirc-entrada__erro">{erro}</p>}

        <Botao
          variante="primario"
          type="submit"
          bloco
          disabled={entrando || !usuario.trim() || !senha}
        >
          {entrando ? 'Entrando…' : 'Entrar'}
        </Botao>
      </form>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Blocos do atendimento
 * ------------------------------------------------------------------ */

function ResumoSituacao({ situacao }) {
  if (!situacao) return null
  const abertos = Number(campo(situacao, 'abertos', 'em_aberto') || 0)
  const atrasados = Number(campo(situacao, 'atrasados') || 0)
  const multas = Number(campo(situacao, 'multas', 'multa') || 0)
  const limite = campo(situacao, 'limite')

  return (
    <div className="bcirc-leitor__selos">
      <Selo tom={abertos ? 'acento' : 'neutro'}>
        {abertos} em aberto{limite ? ` de ${limite}` : ''}
      </Selo>
      <Selo tom={atrasados ? 'erro' : 'existente'}>
        {atrasados ? `${atrasados} atrasado${atrasados === 1 ? '' : 's'}` : 'sem atraso'}
      </Selo>
      {multas > 0 && <Selo tom="alerta">{moeda(multas)} de multa</Selo>}
      {situacao.pode_levar === false && <Selo tom="erro">não pode levar</Selo>}
    </div>
  )
}

/**
 * O exemplar que acabou de ser bipado, e o que se pode fazer com ele.
 *
 * Nunca decide sozinho: mostra o estado e oferece o botão. Emprestado → oferece
 * devolver (e renovar). Livre com leitor em atendimento → oferece emprestar.
 * Livre sem leitor → diz que falta identificar o leitor, e segura o exemplar
 * aqui até que ele apareça.
 */
function ItemEmMaos({
  pendente,
  ficha,
  ocupado,
  desabilitado,
  aoEmprestar,
  aoDevolver,
  aoRenovar,
  aoAbrirLeitor,
  aoDispensar,
}) {
  const exemplar = pendente.exemplar || {}
  const obra = pendente.obra || {}
  const emprestimo = pendente.emprestimo
  const emprestado = !!emprestimo
  const leitorDoEmprestimo = leitorDe(emprestimo)
  const atraso = emprestado ? diasDeAtraso(emprestimo) : 0
  const temLeitor = !!ficha
  const primeiroNome = temLeitor ? nomeDoLeitor(ficha.leitor).split(' ')[0] : ''

  return (
    <div className="bcirc-item">
      <span className="bcirc-item__tombo mono">{tomboDoItem(exemplar)}</span>
      <span className="bcirc-item__titulo">
        {tituloDaObra(obra) !== 'sem título' ? tituloDaObra(obra) : tituloDaObra(exemplar)}
      </span>
      {pendente.tambemLeitor && (
        <span className="bcirc-item__estado">
          O número {tomboDoItem(exemplar)} também é de um leitor.{' '}
          <Botao
            variante="fantasma"
            tamanho="pequeno"
            onClick={() => aoAbrirLeitor(pendente.tambemLeitor.user_id)}
          >
            Era o leitor? Abrir a ficha
          </Botao>
        </span>
      )}
      {campo(obra, 'autor', 'autores') && (
        <span className="bcirc-item__autor">{campo(obra, 'autor', 'autores')}</span>
      )}

      {emprestado ? (
        <span className="bcirc-item__estado">
          Está com <strong>{nomeDoLeitor(leitorDoEmprestimo)}</strong> desde{' '}
          {dataBr(campo(emprestimo, 'emprestado_em', 'created', 'saida'))} · previsto
          para {dataBr(campo(emprestimo, 'previsto_para', 'expected_return_date'))}
          {atraso > 0 && (
            <>
              {' · '}
              <span className="bcirc-dias">
                {atraso} {atraso === 1 ? 'dia' : 'dias'} de atraso
              </span>
            </>
          )}
        </span>
      ) : (
        <span className="bcirc-item__estado">
          {campo(exemplar, 'disponivel') === false ? (
            <>Exemplar na estante, mas marcado como indisponível no acervo.</>
          ) : temLeitor ? (
            <>
              Livre. Pode sair no nome de <strong>{nomeDoLeitor(ficha.leitor)}</strong>.
            </>
          ) : (
            <>
              Livre — falta identificar o leitor. Bipe a carteirinha ou digite o
              número dele na barra de comando; o exemplar fica aqui esperando.
            </>
          )}
        </span>
      )}

      <div className="bcirc-item__acoes">
        {emprestado ? (
          <>
            <Botao
              variante="primario"
              tamanho="pequeno"
              onClick={aoDevolver}
              disabled={desabilitado || !!ocupado}
            >
              Devolver
            </Botao>
            {idDoEmprestimo(emprestimo) != null && (
              <Botao
                variante="secundario"
                tamanho="pequeno"
                onClick={aoRenovar}
                disabled={desabilitado || !!ocupado}
              >
                Renovar
              </Botao>
            )}
            {idDoLeitor(leitorDoEmprestimo) != null && (
              <Botao
                variante="fantasma"
                tamanho="pequeno"
                onClick={() => aoAbrirLeitor(idDoLeitor(leitorDoEmprestimo))}
              >
                Abrir a ficha de quem está com ele
              </Botao>
            )}
          </>
        ) : (
          <Botao
            variante="primario"
            tamanho="pequeno"
            onClick={aoEmprestar}
            disabled={desabilitado || !temLeitor || ocupado === 'emprestimo'}
            title={
              temLeitor
                ? 'Registrar o empréstimo deste exemplar'
                : 'Identifique o leitor primeiro'
            }
          >
            {ocupado === 'emprestimo'
              ? 'Gravando…'
              : temLeitor
                ? `Emprestar para ${primeiroNome}`
                : 'Emprestar'}
          </Botao>
        )}
        <Botao variante="fantasma" tamanho="pequeno" onClick={aoDispensar}>
          Dispensar
        </Botao>
      </div>
    </div>
  )
}

/**
 * O caminho do ISBN: qual destes exemplares saiu da estante?
 *
 * Caso de primeira classe, não exceção — dos 16.251 exemplares migrados, a
 * maioria nunca teve etiqueta impressa (§1.1 do plano). Bipar a capa e escolher
 * na lista é o fluxo normal desse acervo.
 */
function EscolhaDeExemplar({ escolha, ocupado, desabilitado, aoEscolher, aoFechar }) {
  const exemplares = escolha.exemplares || []

  return (
    <div className="bcirc-item">
      <span className="bcirc-item__tombo">
        {escolha.origem === 'titulo' ? 'Busca por título' : 'ISBN da capa'}
      </span>
      <span className="bcirc-item__titulo">{tituloDaObra(escolha.obra || {})}</span>
      <span className="bcirc-item__estado">
        {exemplares.length === 0
          ? 'Esta obra não tem exemplar cadastrado no acervo.'
          : `${exemplares.length} ${
              exemplares.length === 1 ? 'exemplar' : 'exemplares'
            } desta obra. Qual está na sua mão?`}
      </span>

      {exemplares.length > 0 && (
        <div className="bcirc-lista">
          {exemplares.map((ex, i) => {
            const id = idDoExemplar(ex)
            const emprestado =
              campo(ex, 'emprestado') === true || !!campo(ex, 'emprestimo', 'lending_id')
            const local = campo(ex, 'localizacao', 'location')
            return (
              <button
                key={id ?? `ex-${i}`}
                className="bcirc-lista__item"
                onClick={() => aoEscolher(id)}
                disabled={desabilitado || id == null || ocupado === `exemplar:${id}`}
              >
                <span className="bcirc-lista__nome mono">{tomboDoItem(ex)}</span>
                <span className="bcirc-lista__meta">
                  {emprestado
                    ? 'emprestado'
                    : campo(ex, 'disponivel') === false
                      ? 'indisponível'
                      : 'na estante'}
                  {local ? ` · ${local}` : ''}
                </span>
              </button>
            )
          })}
        </div>
      )}

      <div className="bcirc-item__acoes">
        <Botao variante="fantasma" tamanho="pequeno" onClick={aoFechar}>
          Dispensar
        </Botao>
      </div>
    </div>
  )
}

/**
 * Mais de uma obra com esse título: qual é? Cada linha já diz quantos
 * exemplares estão na estante, que é o que decide entre duas edições.
 */
function ObrasAchadas({ achadas, aoEscolher, aoFechar }) {
  const obras = achadas.obras || []
  return (
    <div className="bcirc-item">
      <span className="bcirc-item__tombo">Busca por título</span>
      <span className="bcirc-item__estado">
        {obras.length === 0
          ? `Nenhuma obra com “${achadas.busca}” no título ou no autor.`
          : `${obras.length} ${obras.length === 1 ? 'obra' : 'obras'} com “${achadas.busca}”. Qual é a do livro na mão?`}
      </span>
      {obras.length > 0 && (
        <div className="bcirc-lista">
          {obras.map((o) => (
            <button
              key={o.record_id}
              className="bcirc-lista__item"
              onClick={() => aoEscolher(o)}
            >
              <span className="bcirc-lista__nome">{o.titulo || 'sem título'}</span>
              <span className="bcirc-lista__meta">
                {o.autor ? `${o.autor} · ` : ''}
                {o.total === 0
                  ? 'sem exemplar'
                  : `${o.disponiveis} de ${o.total} na estante`}
              </span>
            </button>
          ))}
        </div>
      )}
      <div className="bcirc-item__acoes">
        <Botao variante="fantasma" tamanho="pequeno" onClick={aoFechar}>
          Dispensar
        </Botao>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Região 3: atrasos
 * ------------------------------------------------------------------ */

/**
 * O relatório que hoje obriga a abrir o BibLivre: quem está devendo o quê e há
 * quantos dias. Ordenável e com busca, porque a pergunta muda — às vezes é
 * "quem está mais atrasado", às vezes é "cadê o livro tal".
 */
function Atrasos({
  itens,
  total,
  carregado,
  erro,
  busca,
  aoBuscar,
  ordem,
  aoOrdenar,
  desabilitado,
  ocupado,
  aoAbrirLeitor,
  aoDevolver,
  aoAtualizar,
}) {
  return (
    <section className="bcirc-bloco moldura">
      <div className="bcirc-bloco__cabecalho">
        <span className="microrrotulo">Atrasos</span>
        <Botao variante="fantasma" tamanho="pequeno" onClick={aoAtualizar}>
          <IconeRecarregar tamanho={12} /> Atualizar
        </Botao>
      </div>

      {erro && (
        <p className="bcirc-bloco__vazio">
          Não deu para atualizar a lista agora ({erro}). O que está na tela pode
          estar velho.
        </p>
      )}

      <div className="bcirc-atrasos__filtros">
        <input
          className="bcirc-busca__campo"
          value={busca}
          onChange={(e) => aoBuscar(e.target.value)}
          placeholder="filtrar por leitor, obra ou tombo"
          aria-label="Filtrar os atrasos"
        />
        <span className="bcirc-atrasos__contagem">
          {itens.length === total
            ? `${total} ${total === 1 ? 'atraso' : 'atrasos'}`
            : `${itens.length} de ${total}`}
        </span>
      </div>

      {itens.length === 0 ? (
        <p className="bcirc-bloco__vazio">
          {!carregado
            ? 'Carregando os atrasos…'
            : total === 0
              ? 'Nenhum livro atrasado. É o estado normal de uma biblioteca em dia — e o único relatório que vale a pena ver vazio.'
              : 'Nenhum atraso com esse filtro.'}
        </p>
      ) : (
        <div className="bcirc-tabela-wrap">
          <table className="bcirc-tabela">
            <thead>
              <tr>
                {COLUNAS_ATRASO.map(([chave, rotulo]) => (
                  <th key={chave}>
                    <button
                      className="bcirc-tabela__ordenar"
                      onClick={() => aoOrdenar(chave)}
                    >
                      {rotulo}
                      {ordem.coluna === chave && (
                        <span className="bcirc-tabela__seta">
                          {ordem.desc ? '▼' : '▲'}
                        </span>
                      )}
                    </button>
                  </th>
                ))}
                <th className="bcirc-col-acoes" />
              </tr>
            </thead>
            <tbody>
              {itens.map((item, i) => {
                const dias = diasDeAtraso(item)
                const leitor = leitorDe(item)
                const lendingId = idDoEmprestimo(item)
                const holdingId = idDoExemplar(item)
                const chave = `devolver:${lendingId ?? holdingId}`
                const multa = campo(item, 'multa')
                return (
                  <tr key={lendingId ?? `atraso-${i}`} className="bcirc-linha--atraso">
                    <td>
                      <span className="bcirc-obra">{nomeDoLeitor(leitor)}</span>
                      <span className="bcirc-obra__sub">
                        {idDoLeitor(leitor) != null ? `nº ${idDoLeitor(leitor)}` : ''}
                        {multa ? ` · ${moeda(multa)}` : ''}
                      </span>
                    </td>
                    <td>
                      <span className="bcirc-obra">{tituloDaObra(item)}</span>
                      <span className="bcirc-obra__sub mono">{tomboDoItem(item)}</span>
                    </td>
                    <td className="bcirc-data">
                      {dataBr(campo(item, 'previsto_para', 'expected_return_date'))}
                    </td>
                    <td>
                      <span className="bcirc-dias">{dias}</span>
                    </td>
                    <td className="bcirc-col-acoes">
                      <div className="bcirc-cel-acoes">
                        {idDoLeitor(leitor) != null && (
                          <Botao
                            variante="secundario"
                            tamanho="pequeno"
                            onClick={() => aoAbrirLeitor(idDoLeitor(leitor))}
                          >
                            Ficha
                          </Botao>
                        )}
                        {(lendingId != null || holdingId != null) && (
                          <Botao
                            variante="primario"
                            tamanho="pequeno"
                            onClick={() => aoDevolver({ lendingId, holdingId }, item)}
                            disabled={desabilitado || ocupado === chave}
                          >
                            {ocupado === chave ? '…' : 'Devolver'}
                          </Botao>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
