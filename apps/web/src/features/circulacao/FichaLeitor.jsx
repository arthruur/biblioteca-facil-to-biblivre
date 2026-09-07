import { useMemo, useState } from 'react'
import { Botao, EstadoVazio, IconeLivro, IconeRecarregar, Selo } from '../../components'

/**
 * Ficha do leitor — a região 2 do balcão de circulação.
 *
 * É a tela que hoje obriga a abrir o BibLivre para responder "o que essa
 * pessoa está com a gente?". Três blocos, nessa ordem, que é a ordem da
 * pergunta no balcão:
 *
 *   1. EM ABERTO   — o que está fora, com data prevista e destaque de atraso.
 *                    É aqui que estão as ações por item (renovar, devolver).
 *   2. MULTAS      — só aparece quando existe, porque multa zerada não é
 *                    informação, é ruído.
 *   3. HISTÓRICO   — o que já voltou, paginado no cliente.
 *
 * PAGINAÇÃO NO CLIENTE, E POR QUÊ
 * -------------------------------
 * `GET /api/circulacao/leitor/{id}` devolve `emprestimos` numa lista só
 * (docs/PLANO_AGENTES.html §4.2) — não há parâmetro de página no contrato.
 * Então quem separa aberto de devolvido e quem pagina é esta tela. Se o
 * histórico de um leitor antigo crescer a ponto de pesar, o caminho certo é
 * acrescentar paginação na rota (A8) e não inventar outra rota aqui.
 *
 * NADA ACONTECE SOZINHO
 * ---------------------
 * Este é o PC: todo botão é uma decisão explícita do bibliotecário. O
 * componente não chama a API — ele avisa o pai (`aoRenovar`, `aoDevolver`), que
 * é quem tem a sessão, o tratamento de 409 e o recibo.
 */

const POR_PAGINA = 8

/* ------------------------------------------------------------------ *
 * Utilitários de leitura da ficha.
 *
 * Ficam exportados porque a tela do balcão (TelaBalcaoCirculacao.jsx) lê os
 * mesmos campos nos mesmos formatos — os dois arquivos são do pacote A7, então
 * isto é reuso dentro do pacote, não dependência entre pacotes.
 *
 * São tolerantes de propósito: o pacote A3 ainda está sendo escrito e a §4.1
 * do plano fixa as assinaturas, não o nome de cada chave do dicionário. Aceitar
 * dois ou três nomes plausíveis custa uma linha e evita que a tela apareça
 * vazia por causa de um sinônimo.
 * ------------------------------------------------------------------ */

/** O primeiro valor presente entre várias chaves possíveis. */
export function campo(objeto, ...chaves) {
  if (!objeto) return undefined
  for (const chave of chaves) {
    const v = objeto[chave]
    if (v !== undefined && v !== null && v !== '') return v
  }
  return undefined
}

export function nomeDoLeitor(leitor) {
  const n = campo(leitor, 'nome', 'name', 'nome_completo')
  if (n) return String(n)
  const id = campo(leitor, 'id', 'user_id')
  return id ? `Leitor #${id}` : 'Leitor sem nome'
}

export function idDoLeitor(leitor) {
  const id = campo(leitor, 'id', 'user_id')
  return id === undefined ? null : Number(id)
}

export function tituloDaObra(item) {
  return campo(item, 'titulo', 'title', 'obra') || 'sem título'
}

/** `Bib.2026.687` — o tombo é a identidade do exemplar (§1.1 do plano). */
export function tomboDoItem(item) {
  return campo(item, 'tombo', 'accession_number') || '—'
}

export function dataBr(iso) {
  if (!iso) return '—'
  const texto = String(iso)
  const so = texto.slice(0, 10)
  const [ano, mes, dia] = so.split('-')
  if (ano && mes && dia) return `${dia}/${mes}/${ano}`
  const t = Date.parse(texto)
  return Number.isNaN(t) ? texto : new Date(t).toLocaleDateString('pt-BR')
}

export function moeda(valor) {
  const n = Number(valor)
  if (!Number.isFinite(n)) return 'R$ 0,00'
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

/**
 * Dias de atraso de um empréstimo em aberto.
 *
 * Prefere o que o servidor calculou (`atraso_dias`): a data de hoje que vale é
 * a do banco, não a do relógio deste PC. O cálculo local é só o plano B, para o
 * caso de a rota não mandar o campo.
 */
export function diasDeAtraso(item, hoje = new Date()) {
  const doServidor = campo(item, 'atraso_dias', 'dias_atraso', 'dias')
  if (doServidor !== undefined) return Math.max(0, Number(doServidor) || 0)
  const previsto = campo(item, 'previsto_para', 'expected_return_date', 'previsto')
  if (!previsto) return 0
  const t = Date.parse(String(previsto).slice(0, 10))
  if (Number.isNaN(t)) return 0
  const dia = 24 * 60 * 60 * 1000
  const inicioHoje = Date.parse(
    `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}-${String(
      hoje.getDate()
    ).padStart(2, '0')}`
  )
  return Math.max(0, Math.floor((inicioHoje - t) / dia))
}

/** Empréstimo sem data de devolução é empréstimo em aberto. */
export function estaEmAberto(item) {
  return !campo(item, 'devolvido_em', 'devolucao_em', 'return_date')
}

export function idDoEmprestimo(item) {
  const id = campo(item, 'lending_id', 'id', 'emprestimo_id')
  return id === undefined ? null : Number(id)
}

export function idDoExemplar(item) {
  const id = campo(item, 'holding_id', 'exemplar_id')
  return id === undefined ? null : Number(id)
}

/* ------------------------------------------------------------------ */

export function FichaLeitor({
  ficha,
  carregando = false,
  desabilitado = false,
  ocupado = '',
  aoRenovar,
  aoDevolver,
  aoAtualizar,
  aoEncerrar,
}) {
  const [pagina, setPagina] = useState(0)

  const leitor = ficha?.leitor || null
  const situacao = ficha?.situacao || null
  const emprestimos = useMemo(() => ficha?.emprestimos || [], [ficha])

  const abertos = useMemo(() => emprestimos.filter(estaEmAberto), [emprestimos])
  const historico = useMemo(
    () => emprestimos.filter((e) => !estaEmAberto(e)),
    [emprestimos]
  )

  const paginas = Math.max(1, Math.ceil(historico.length / POR_PAGINA))
  const paginaAtual = Math.min(pagina, paginas - 1)
  const visiveis = historico.slice(
    paginaAtual * POR_PAGINA,
    paginaAtual * POR_PAGINA + POR_PAGINA
  )

  const multas = Number(campo(situacao, 'multas', 'multa') || 0)

  if (carregando && !ficha) {
    return (
      <section className="bcirc-bloco moldura">
        <span className="microrrotulo">Ficha do leitor</span>
        <p className="bcirc-bloco__vazio">Carregando a ficha…</p>
      </section>
    )
  }

  if (!ficha) {
    return (
      <section className="bcirc-bloco moldura">
        <span className="microrrotulo">Ficha do leitor</span>
        <EstadoVazio
          icone={<IconeLivro tamanho={26} />}
          titulo="Nenhum leitor em atendimento"
        >
          Bipe a carteirinha, digite o número do leitor na barra de comando ou
          busque pelo nome. A ficha aparece aqui com o que está em aberto, o que
          está atrasado e o histórico.
        </EstadoVazio>
      </section>
    )
  }

  return (
    <section className="bcirc-bloco moldura">
      <div className="bcirc-bloco__cabecalho">
        <span className="microrrotulo">Ficha do leitor</span>
        <div className="bcirc-bloco__acoes">
          {aoAtualizar && (
            <Botao
              variante="fantasma"
              tamanho="pequeno"
              onClick={aoAtualizar}
              disabled={carregando}
              title="Reler a ficha no banco"
            >
              <IconeRecarregar
                tamanho={12}
                className={carregando ? 'animacao-girar' : ''}
              />
              Atualizar
            </Botao>
          )}
          {aoEncerrar && (
            <Botao variante="fantasma" tamanho="pequeno" onClick={aoEncerrar}>
              Encerrar atendimento
            </Botao>
          )}
        </div>
      </div>

      <div className="bcirc-leitor">
        <span className="bcirc-leitor__nome">{nomeDoLeitor(leitor)}</span>
        <span className="bcirc-leitor__meta">
          {[
            idDoLeitor(leitor) ? `nº ${idDoLeitor(leitor)}` : null,
            campo(leitor, 'matricula', 'documento'),
            campo(leitor, 'tipo', 'tipo_nome', 'user_type'),
            campo(leitor, 'email'),
            campo(leitor, 'telefone', 'fone'),
          ]
            .filter(Boolean)
            .join(' · ') || 'sem outros dados no cadastro'}
        </span>
        <SelosDaSituacao situacao={situacao} abertos={abertos.length} />
      </div>

      {/* 1. EM ABERTO */}
      <div>
        <span className="microrrotulo">Em aberto</span>
        {abertos.length === 0 ? (
          <p className="bcirc-bloco__vazio">
            Nada em aberto — este leitor está com a conta limpa.
          </p>
        ) : (
          <div className="bcirc-tabela-wrap">
            <table className="bcirc-tabela">
              <thead>
                <tr>
                  <th>Obra</th>
                  <th>Levou em</th>
                  <th>Previsto</th>
                  <th>Situação</th>
                  <th className="bcirc-col-acoes" />
                </tr>
              </thead>
              <tbody>
                {abertos.map((item, i) => (
                  <LinhaAberto
                    key={idDoEmprestimo(item) ?? `aberto-${i}`}
                    item={item}
                    desabilitado={desabilitado}
                    ocupado={ocupado}
                    aoRenovar={aoRenovar}
                    aoDevolver={aoDevolver}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 2. MULTAS */}
      {multas > 0 && (
        <div>
          <span className="microrrotulo">Multas</span>
          <p className="bcirc-bloco__vazio">
            <strong>{moeda(multas)}</strong> em aberto. O acerto da multa é feito
            no BibLivre — esta tela mostra o valor, não recebe pagamento.
          </p>
        </div>
      )}

      {/* 3. HISTÓRICO */}
      <div>
        <span className="microrrotulo">Histórico</span>
        {historico.length === 0 ? (
          <p className="bcirc-bloco__vazio">
            Nenhuma devolução registrada para este leitor.
          </p>
        ) : (
          <>
            <div className="bcirc-tabela-wrap">
              <table className="bcirc-tabela">
                <thead>
                  <tr>
                    <th>Obra</th>
                    <th>Levou em</th>
                    <th>Devolveu em</th>
                    <th>Atraso</th>
                    <th>Multa</th>
                  </tr>
                </thead>
                <tbody>
                  {visiveis.map((item, i) => {
                    const atraso = Number(
                      campo(item, 'atraso_dias', 'dias_atraso') || 0
                    )
                    const multa = Number(campo(item, 'multa', 'valor_multa') || 0)
                    return (
                      <tr key={idDoEmprestimo(item) ?? `hist-${i}`}>
                        <td>
                          <span className="bcirc-obra">{tituloDaObra(item)}</span>
                          <span className="bcirc-obra__sub mono">
                            {tomboDoItem(item)}
                          </span>
                        </td>
                        <td className="bcirc-data">
                          {dataBr(campo(item, 'emprestado_em', 'created', 'saida'))}
                        </td>
                        <td className="bcirc-data">
                          {dataBr(
                            campo(item, 'devolvido_em', 'devolucao_em', 'return_date')
                          )}
                        </td>
                        <td>
                          {atraso > 0 ? (
                            <span className="bcirc-dias">
                              {atraso} {atraso === 1 ? 'dia' : 'dias'}
                            </span>
                          ) : (
                            <span className="bcirc-obra__sub">em dia</span>
                          )}
                        </td>
                        <td className="bcirc-data">
                          {multa > 0 ? moeda(multa) : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {paginas > 1 && (
              <div className="bcirc-pagina">
                <Botao
                  variante="fantasma"
                  tamanho="pequeno"
                  onClick={() => setPagina(Math.max(0, paginaAtual - 1))}
                  disabled={paginaAtual === 0}
                >
                  ← anteriores
                </Botao>
                <span className="bcirc-pagina__contagem">
                  {paginaAtual + 1} de {paginas} · {historico.length} devoluções
                </span>
                <Botao
                  variante="fantasma"
                  tamanho="pequeno"
                  onClick={() => setPagina(Math.min(paginas - 1, paginaAtual + 1))}
                  disabled={paginaAtual >= paginas - 1}
                >
                  seguintes →
                </Botao>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}

/**
 * A situação em quatro selos.
 *
 * `pode_levar: false` sem impedimento nomeado ainda assim precisa aparecer —
 * é a diferença entre "a tela não sabe" e "a tela sabe e não avisou".
 */
function SelosDaSituacao({ situacao, abertos }) {
  if (!situacao) {
    return (
      <div className="bcirc-leitor__selos">
        <Selo tom="alerta">situação não informada</Selo>
      </div>
    )
  }

  const emAberto = Number(campo(situacao, 'abertos', 'em_aberto') ?? abertos ?? 0)
  const atrasados = Number(campo(situacao, 'atrasados') || 0)
  const multas = Number(campo(situacao, 'multas', 'multa') || 0)
  const limite = campo(situacao, 'limite')
  const podeLevar = situacao.pode_levar

  return (
    <div className="bcirc-leitor__selos">
      <Selo tom={emAberto ? 'acento' : 'neutro'}>
        {emAberto} em aberto{limite ? ` de ${limite}` : ''}
      </Selo>
      <Selo tom={atrasados ? 'erro' : 'existente'}>
        {atrasados ? `${atrasados} atrasado${atrasados === 1 ? '' : 's'}` : 'sem atraso'}
      </Selo>
      <Selo tom={multas > 0 ? 'alerta' : 'neutro'}>
        {multas > 0 ? `${moeda(multas)} de multa` : 'sem multa'}
      </Selo>
      {podeLevar === false && <Selo tom="erro">não pode levar</Selo>}
    </div>
  )
}

function LinhaAberto({ item, desabilitado, ocupado, aoRenovar, aoDevolver }) {
  const atraso = diasDeAtraso(item)
  const lendingId = idDoEmprestimo(item)
  const holdingId = idDoExemplar(item)
  const chaveRenovar = `renovar:${lendingId}`
  const chaveDevolver = `devolver:${lendingId ?? holdingId}`

  return (
    <tr className={atraso > 0 ? 'bcirc-linha--atraso' : undefined}>
      <td>
        <span className="bcirc-obra">{tituloDaObra(item)}</span>
        <span className="bcirc-obra__sub mono">{tomboDoItem(item)}</span>
      </td>
      <td className="bcirc-data">
        {dataBr(campo(item, 'emprestado_em', 'created', 'saida'))}
      </td>
      <td className="bcirc-data">
        {dataBr(campo(item, 'previsto_para', 'expected_return_date', 'previsto'))}
      </td>
      <td>
        {atraso > 0 ? (
          <span className="bcirc-dias">
            {atraso} {atraso === 1 ? 'dia' : 'dias'} de atraso
          </span>
        ) : (
          <Selo tom="existente">em dia</Selo>
        )}
      </td>
      <td className="bcirc-col-acoes">
        <div className="bcirc-cel-acoes">
          {aoRenovar && lendingId != null && (
            <Botao
              variante="secundario"
              tamanho="pequeno"
              onClick={() => aoRenovar(lendingId, item)}
              disabled={desabilitado || ocupado === chaveRenovar}
              title="Estender o prazo deste empréstimo"
            >
              {ocupado === chaveRenovar ? '…' : 'Renovar'}
            </Botao>
          )}
          {aoDevolver && (lendingId != null || holdingId != null) && (
            <Botao
              variante="primario"
              tamanho="pequeno"
              onClick={() => aoDevolver({ lendingId, holdingId }, item)}
              disabled={desabilitado || ocupado === chaveDevolver}
            >
              {ocupado === chaveDevolver ? '…' : 'Devolver'}
            </Botao>
          )}
        </div>
      </td>
    </tr>
  )
}
