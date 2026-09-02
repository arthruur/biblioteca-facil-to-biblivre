import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

/**
 * Janela em que o mesmo ISBN é ignorado.
 *
 * O decodificador entrega o mesmo código muitas vezes por segundo enquanto o
 * livro está enquadrado. Sem esta janela, um livro parado na frente da câmera
 * viraria vinte exemplares. Dois segundos é o tempo que leva para trocar o
 * livro da mão — quem realmente tem duas cópias bipa a segunda depois disso.
 */
const JANELA_REPETICAO = 2000

/**
 * O lote: a bandeja do scanner.
 *
 * Volátil de propósito (docs/SPEC_UI.md §1). O estado local é otimista — o
 * card aparece no mesmo frame do bipe e os metadados chegam depois — porque a
 * tela não pode esperar a rede entre dois livros.
 */
export function useLote({ aoAvisar }) {
  const [itens, setItens] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [enviando, setEnviando] = useState(false)
  const ultimoBipe = useRef(new Map())

  const totalExemplares = itens.reduce(
    (s, i) => s + (Number(i.quantidade) || 1),
    0
  )

  useEffect(() => {
    let vivo = true
    api.lote
      .listar()
      .then((d) => vivo && setItens(d.itens || []))
      .catch(() => {})
      .finally(() => vivo && setCarregando(false))
    return () => {
      vivo = false
    }
  }, [])

  const vibrar = () => navigator.vibrate?.(60)

  const adicionar = useCallback(
    async (isbn) => {
      const agora = Date.now()
      const anterior = ultimoBipe.current.get(isbn)
      if (anterior && agora - anterior < JANELA_REPETICAO) return
      ultimoBipe.current.set(isbn, agora)

      vibrar()
      let jaTinha = false

      // Otimista: mexe na tela antes de falar com o servidor.
      setItens((atuais) => {
        const idx = atuais.findIndex((i) => i.isbn === isbn)
        if (idx === -1) {
          return [
            ...atuais,
            {
              isbn,
              titulo: '',
              autor: '',
              fonte: '',
              quantidade: 1,
              exemplares: 1,
              buscando: true,
            },
          ]
        }
        jaTinha = true
        const copia = [...atuais]
        const q = (Number(copia[idx].quantidade) || 1) + 1
        copia[idx] = { ...copia[idx], quantidade: q, exemplares: q }
        return copia
      })

      try {
        const resposta = await api.lote.adicionar(isbn)
        setItens((atuais) => {
          const idx = atuais.findIndex((i) => i.isbn === isbn)
          if (idx === -1) return atuais
          const copia = [...atuais]
          const vindo = resposta.item || {}
          copia[idx] = {
            ...copia[idx],
            ...vindo,
            // O servidor é a fonte da verdade da contagem: ele já resolveu
            // corridas entre dois bipes do mesmo código.
            quantidade: resposta.quantidade || vindo.quantidade || copia[idx].quantidade,
            buscando: false,
          }
          copia[idx].exemplares = copia[idx].quantidade
          return copia
        })
        return { jaTinha, item: resposta.item }
      } catch (e) {
        // O card fica na tela mesmo assim: o bipe aconteceu, e perder o
        // registro por causa de rede seria pior que um card sem metadado.
        setItens((atuais) =>
          atuais.map((i) =>
            i.isbn === isbn ? { ...i, buscando: false, offline: true } : i
          )
        )
        aoAvisar?.(`Sem resposta do servidor (${e.message}) — o lote continua aqui`, 'erro')
        return { jaTinha, erro: e }
      }
    },
    [aoAvisar]
  )

  const mudarQuantidade = useCallback(async (isbn, quantidade) => {
    setItens((atuais) =>
      atuais.map((i) =>
        i.isbn === isbn ? { ...i, quantidade, exemplares: quantidade } : i
      )
    )
    try {
      await api.lote.quantidade(isbn, quantidade)
    } catch {
      /* a tela já mostra o valor novo; o envio reconcilia */
    }
  }, [])

  const atualizarCampos = useCallback((isbn, campos) => {
    setItens((atuais) =>
      atuais.map((i) => (i.isbn === isbn ? { ...i, ...campos } : i))
    )
  }, [])

  const remover = useCallback(async (isbn) => {
    setItens((atuais) => atuais.filter((i) => i.isbn !== isbn))
    ultimoBipe.current.delete(isbn)
    try {
      await api.lote.remover(isbn)
    } catch {
      /* removido da tela; o servidor reconcilia no próximo listar */
    }
  }, [])

  const limpar = useCallback(async () => {
    setItens([])
    ultimoBipe.current.clear()
    try {
      await api.lote.limpar()
    } catch {
      /* idem */
    }
  }, [])

  const enviar = useCallback(async () => {
    if (!itens.length) return null
    setEnviando(true)
    try {
      const d = await api.lote.enviar()
      setItens([])
      ultimoBipe.current.clear()
      return d
    } finally {
      setEnviando(false)
    }
  }, [itens.length])

  return {
    itens,
    carregando,
    enviando,
    totalExemplares,
    adicionar,
    mudarQuantidade,
    atualizarCampos,
    remover,
    limpar,
    enviar,
  }
}
