import { useCallback, useEffect, useState } from 'react'
import { api, definirDispositivo } from '../api/client'

const CHAVE_ID = 'biblio.dispositivo.id'
const CHAVE_NOME = 'biblio.dispositivo.nome'

/**
 * A partir daqui a tela é a do PC, não a do celular.
 *
 * Não é um breakpoint de layout: é a fronteira entre dois aplicativos
 * diferentes. Abaixo dela a pessoa está de pé na estante com uma mão livre e a
 * tela é a câmera; acima, está sentada e a tela é a fila (ou o painel dos
 * aparelhos que estão bipando). Reflowar uma na outra foi o erro que esta
 * constante existe para não repetir.
 */
const PC_MINIMO = 900

function medir() {
  if (typeof window === 'undefined') return false
  return window.matchMedia(`(min-width: ${PC_MINIMO}px)`).matches
}

/** `true` quando a tela é a do PC. Reage a redimensionar e a girar o aparelho. */
export function useEhPc() {
  const [ehPc, setEhPc] = useState(medir)

  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${PC_MINIMO}px)`)
    const aoMudar = (e) => setEhPc(e.matches)
    mq.addEventListener('change', aoMudar)
    setEhPc(mq.matches)
    return () => mq.removeEventListener('change', aoMudar)
  }, [])

  return ehPc
}

function novoId() {
  if (crypto?.randomUUID) return crypto.randomUUID()
  // Navegador antigo, ou contexto sem `crypto.randomUUID`: o id só precisa ser
  // distinto entre os aparelhos de uma biblioteca, não globalmente único.
  return `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function lerLocal(chave) {
  try {
    return window.localStorage.getItem(chave)
  } catch {
    // Modo privado, ou site data bloqueado: o aparelho ainda funciona, só não
    // se lembra do próprio nome entre sessões.
    return null
  }
}

function gravarLocal(chave, valor) {
  try {
    window.localStorage.setItem(chave, valor)
  } catch {
    /* idem */
  }
}

/**
 * Identidade deste aparelho.
 *
 * O id nasce na primeira visita e vive no `localStorage`: é o que faz o painel
 * do PC reconhecer "o celular da Ana" como o mesmo aparelho depois de a tela
 * recarregar. O nome é opcional — sem ele o painel mostra "Aparelho a3f19c",
 * que funciona mas não ajuda quem está olhando três celulares.
 *
 * Só o celular chama isto. O PC não é um aparelho que bipa: as chamadas dele
 * saem sem identidade e, se ele digitar um ISBN à mão, o item cai no lote do
 * balcão.
 */
export function useDispositivo({ ativo = true } = {}) {
  const [id] = useState(() => {
    if (!ativo) return null
    const guardado = lerLocal(CHAVE_ID)
    if (guardado) return guardado
    const novo = novoId()
    gravarLocal(CHAVE_ID, novo)
    return novo
  })
  const [nome, setNome] = useState(() => (ativo ? lerLocal(CHAVE_NOME) || '' : ''))

  // Antes de qualquer chamada: o cliente da API precisa do id para montar o
  // cabeçalho, e o primeiro bipe pode sair antes do primeiro render terminar.
  useEffect(() => {
    definirDispositivo(id)
    return () => definirDispositivo(null)
  }, [id])

  const batizar = useCallback(
    async (novoNome) => {
      const limpo = (novoNome || '').trim()
      setNome(limpo)
      gravarLocal(CHAVE_NOME, limpo)
      if (!id) return
      try {
        await api.lotes.renomear(id, limpo)
      } catch {
        // Nome é conveniência: se o servidor não aceitou agora, o aparelho
        // continua bipando e o painel mostra o id. Não vale um aviso na tela.
      }
    },
    [id]
  )

  // O painel do PC só descobre um aparelho quando ele fala. Sem isto, um
  // celular que abriu a tela e ainda não bipou nada seria invisível — e é
  // justamente nesse momento que o bibliotecário quer confirmar que pareou.
  useEffect(() => {
    if (!id) return
    let vivo = true
    const anunciar = () => {
      api.lote.listar().catch(() => {})
      if (nome) api.lotes.renomear(id, nome).catch(() => {})
    }
    anunciar()
    const t = setInterval(() => vivo && anunciar(), 45000)
    return () => {
      vivo = false
      clearInterval(t)
    }
  }, [id, nome])

  return { id, nome, batizar }
}
