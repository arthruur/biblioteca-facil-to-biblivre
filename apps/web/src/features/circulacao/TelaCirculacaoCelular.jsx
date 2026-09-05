import { EstadoVazio, IconeLivro } from '../../components'

/*
 * PLACEHOLDER DO ANDAIME — o dono deste arquivo é o pacote A6
 * (docs/PLANO_AGENTES.html) e substitui tudo aqui dentro.
 *
 * Existe agora só para que a rota `/circulacao` compile e para marcar, em
 * código, as duas coisas que a tela definitiva precisa resolver:
 *
 * 1. O CELULAR NÃO TEM BARRA DE NAVEGAÇÃO. A captura é a tela única dele hoje,
 *    e o título é da própria tela. Com uma segunda tela no celular, alguém
 *    precisa poder ir e voltar — `aoNavegar` chega por prop justamente para
 *    isso, e a decisão de como oferecer (cabeçalho? gesto? um botão no rodapé?)
 *    é da tela, não do App.
 * 2. AQUI O BIPE ESPERA. Na captura o celular nunca bloqueia; no empréstimo
 *    ele aguarda a confirmação do servidor, porque dizer "levou" antes do
 *    commit é mentir para quem está na frente do balcão.
 */
export function TelaCirculacaoCelular({ aoNavegar }) {
  return (
    <EstadoVazio
      icone={<IconeLivro tamanho={28} />}
      titulo="Circulação — em construção"
      acao={
        aoNavegar && (
          <button className="btn btn--secundario" onClick={() => aoNavegar('captura')}>
            Voltar para a captura
          </button>
        )
      }
    >
      Emprestar e devolver bipando o tombo. Esta tela é o pacote A6 do plano de
      agentes; o contrato das rotas já está de pé em <code>/api/circulacao</code>.
    </EstadoVazio>
  )
}
