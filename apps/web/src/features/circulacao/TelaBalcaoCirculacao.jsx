import { EstadoVazio, IconeLivro } from '../../components'

/*
 * PLACEHOLDER DO ANDAIME — o dono deste arquivo é o pacote A7
 * (docs/PLANO_AGENTES.html) e substitui tudo aqui dentro.
 *
 * O que a tela definitiva é: uma barra de comando sempre com foco, que aceita
 * tombo, ISBN ou número de leitor e manda para `/api/circulacao/resolver` — é
 * assim que o leitor de código de barras USB funciona, digitando e apertando
 * Enter. Em volta dela: atendimento, ficha do leitor e atrasos.
 *
 * `conexao` chega por prop porque sem banco a tela precisa DIZER isso e
 * desabilitar as ações, em vez de degradar em silêncio — a mesma postura da
 * pílula do acervo.
 */
export function TelaBalcaoCirculacao({ conexao, aoAbrirBanco }) {
  return (
    <EstadoVazio
      icone={<IconeLivro tamanho={28} />}
      titulo="Balcão de circulação — em construção"
      acao={
        conexao && !conexao.conectado && aoAbrirBanco ? (
          <button className="btn btn--secundario" onClick={aoAbrirBanco}>
            Conectar ao PostgreSQL
          </button>
        ) : null
      }
    >
      Empréstimo, devolução, renovação, ficha do leitor e atrasos. Esta tela é o
      pacote A7 do plano de agentes; o contrato das rotas já está de pé em{' '}
      <code>/api/circulacao</code>.
    </EstadoVazio>
  )
}
