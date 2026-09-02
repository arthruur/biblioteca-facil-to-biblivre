import { Selo } from '../../components'

/**
 * O destino de um item no BibLivre. É a informação mais importante da tela.
 *
 * Três estados, e a diferença entre eles é o que o usuário precisa entender
 * antes de gravar:
 *
 *   obra nova       nasce ficha em biblio_records + N exemplares. Exige reindex.
 *   +N exemplares   nenhum registro novo; só holdings no record_id existente.
 *   não verificado  o banco estava fora. Na gravação isto vira "obra nova" —
 *                   por isso é alerta, e nunca silencioso.
 */
export function Destino({ item, conectado }) {
  const acervo = item.acervo
  const qtd = Number(item.quantidade) || 1

  if (acervo?.existe) {
    return (
      <>
        <Selo tom="existente">
          +{qtd} {qtd === 1 ? 'exemplar' : 'exemplares'}
        </Selo>
        <p className="destino__detalhe">
          obra #{acervo.record_id} · tem {acervo.exemplares}
        </p>
      </>
    )
  }

  if (!conectado) {
    return (
      <>
        <Selo tom="alerta">não verificado</Selo>
        <p className="destino__detalhe">banco desconectado</p>
      </>
    )
  }

  return (
    <>
      <Selo tom="nova">obra nova</Selo>
      <p className="destino__detalhe">
        vira ficha + {qtd} {qtd === 1 ? 'exemplar' : 'exemplares'}
      </p>
    </>
  )
}

const ROTULOS = {
  pendente: { tom: 'neutro', texto: 'pendente' },
  revisado: { tom: 'acento', texto: 'revisado' },
  exportado: { tom: 'existente', texto: 'exportado' },
  ignorado: { tom: 'neutro', texto: 'ignorado' },
}

export function Situacao({ status }) {
  const { tom, texto } = ROTULOS[status] || ROTULOS.pendente
  return <Selo tom={tom}>{texto}</Selo>
}
