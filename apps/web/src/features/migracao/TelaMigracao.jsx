import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import {
  Aviso,
  Botao,
  Campo,
  EstadoVazio,
  FaixaIndicadores,
  IconeBanco,
  IconeCheck,
  IconeExportar,
  IconeLivro,
  IconeRecarregar,
  IconeRemover,
  Moldura,
  Selo,
} from '../../components'
import { ModalGravarMigracao } from './ModalGravarMigracao'
import './migracao.css'

/*
 * Migração de acervo legado — a tela do primeiro dia.
 *
 * A catalogação por ISBN é o trabalho de todo dia, item a item. Esta tela é o
 * oposto: roda uma vez por biblioteca, traz o acervo inteiro de um sistema que
 * vai ser desligado e escreve dezenas de milhares de linhas de uma vez. As
 * duas gravam no mesmo BibLivre, e por isso moram no mesmo app — mas o ritmo
 * aqui é outro, e a tela reflete isso.
 *
 * Três passos, separados de propósito, na ordem em que a decisão acontece:
 *
 *   1. enviar o backup       — só lê o arquivo e mostra o que veio dentro
 *   2. conferir              — não toca no banco; produz o relatório completo
 *   3. gravar                — uma transação, com confirmação explícita
 *
 * O passo 2 existe porque o 3 não tem desfazer. Ele é o mesmo dry-run que os
 * CLIs de `scripts/` imprimem no terminal, só que em números na tela.
 *
 * Só existe no PC, como a fila: quem migra está sentado, com o backup na mão e
 * tempo para ler um relatório antes de decidir.
 */

const INTERVALO_LACO = 1500

// Espelham `biblio.migracao.Opcoes` — os padrões de verdade estão lá, e o
// servidor manda os que valem em `estado.opcoes` assim que há execução.
const PADRAO = {
  acervo: true,
  leitores: true,
  circulacao: true,
  incluir_excluidos: false,
  prefixo_tombo: '',
  ano_tombo: null,
  biblioteca: '',
  campos_extras: 'novos',
  offset_id: 0,
  email_obrigatorio: false,
  apenas_abertos: false,
  incluir_movimentacoes_excluidas: false,
  sem_reservas: false,
  reservas_desde: 2026,
  permitir_existentes: false,
}

const ETAPAS = [
  ['acervo', 'Acervo', 'Obras (biblio_records) e exemplares (biblio_holdings)'],
  ['leitores', 'Leitores', 'users + users_values, preservando o número do leitor'],
  ['circulacao', 'Circulação', 'Empréstimos, multas e reservas'],
]

const fmt = (n) => (Number(n) || 0).toLocaleString('pt-BR')
const mb = (n) => `${(Number(n) / 1048576).toFixed(1)} MB`

export function TelaMigracao({ conexao, aoAbrirBanco }) {
  const [estado, setEstado] = useState(null)
  const [opcoes, setOpcoes] = useState(PADRAO)
  const [erro, setErro] = useState('')
  const [ocupadoLocal, setOcupadoLocal] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const entradaArquivo = useRef(null)

  const puxar = useCallback(async (signal) => {
    try {
      const novo = await api.migracao.estado(signal)
      setEstado(novo)
      return novo
    } catch {
      /* a tela mostra o que já tem; o próximo ciclo reconcilia */
      return null
    }
  }, [])

  useEffect(() => {
    const controle = new AbortController()
    puxar(controle.signal)
    return () => controle.abort()
  }, [puxar])

  // O laço só existe enquanto o servidor está trabalhando: conferência e
  // gravação levam minutos, e é durante eles que os passos mudam de estado.
  useEffect(() => {
    if (!estado?.ocupado) return undefined
    const t = setInterval(() => puxar(), INTERVALO_LACO)
    return () => clearInterval(t)
  }, [estado?.ocupado, puxar])

  // As opções do servidor mandam: elas sobreviveram a um F5 e a um restart.
  useEffect(() => {
    if (estado?.opcoes) setOpcoes((atual) => ({ ...atual, ...estado.opcoes }))
  }, [estado?.id])

  const mudar = (chave) => (valor) => setOpcoes((o) => ({ ...o, [chave]: valor }))

  const enviarBackup = async (arquivo) => {
    if (!arquivo) return
    setErro('')
    setOcupadoLocal(true)
    try {
      setEstado(await api.migracao.enviarBackup(arquivo))
    } catch (e) {
      setErro(e.message || 'Não foi possível ler o backup.')
    } finally {
      setOcupadoLocal(false)
    }
  }

  const conferir = async () => {
    setErro('')
    setOcupadoLocal(true)
    try {
      setEstado(await api.migracao.conferir({ opcoes }))
    } catch (e) {
      setErro(e.message || 'Não foi possível iniciar a conferência.')
    } finally {
      setOcupadoLocal(false)
    }
  }

  const gravar = async ({ senha }) => {
    setErro('')
    setOcupadoLocal(true)
    try {
      setEstado(
        await api.migracao.executar({ opcoes, db: senha ? { senha } : null })
      )
      setConfirmando(false)
    } catch (e) {
      setErro(e.message || 'Não foi possível iniciar a gravação.')
    } finally {
      setOcupadoLocal(false)
    }
  }

  const descartar = async () => {
    setErro('')
    try {
      await api.migracao.descartar()
      setEstado(await api.migracao.estado())
    } catch (e) {
      setErro(e.message || 'Não foi possível descartar a execução.')
    }
  }

  const fase = estado?.fase || 'vazio'
  const trabalhando = !!estado?.ocupado || ocupadoLocal
  const relatorio = estado?.relatorio
  const impedimentos = relatorio?.impedimentos || []
  // Também se pode gravar depois de um erro: a transação foi desfeita por
  // inteiro, então o relatório na tela continua descrevendo o mesmo banco. É o
  // caso de quem só esqueceu a senha do Postgres.
  const jaGravadas = (estado?.gravadas || []).filter((e) => opcoes[e])
  const podeGravar =
    (fase === 'conferido' || (fase === 'erro' && !!relatorio)) &&
    impedimentos.length === 0 &&
    jaGravadas.length === 0 &&
    !trabalhando

  return (
    <div className="migracao">
      <header className="migracao__topo">
        <div>
          <h1 className="migracao__titulo">Migração de acervo</h1>
          <p className="migracao__sub">
            Traz um acervo inteiro do Biblioteca Fácil para o BibLivre 5 — obras,
            exemplares, leitores e circulação. Roda uma vez, e o que ela grava
            não tem desfazer pela tela.
          </p>
        </div>
        {fase !== 'vazio' && (
          <Botao
            variante="fantasma"
            onClick={descartar}
            disabled={trabalhando}
            icone={<IconeRemover tamanho={15} />}
            title="Apaga o backup enviado e os arquivos de conferência"
          >
            Descartar
          </Botao>
        )}
      </header>

      {erro && (
        <Aviso tom="erro" icone="⚠" titulo="Não deu">
          <span className="mono">{erro}</span>
        </Aviso>
      )}

      {fase === 'erro' && estado?.erro && (
        <Aviso tom="erro" icone="⚠" titulo="A execução parou">
          <span className="mono">{estado.erro}</span>
        </Aviso>
      )}

      {fase === 'vazio' ? (
        <Envio
          ocupado={ocupadoLocal}
          entrada={entradaArquivo}
          aoEscolher={enviarBackup}
        />
      ) : (
        <>
          <Backup estado={estado} />

          <Opcoes
            valores={opcoes}
            aoMudar={mudar}
            travado={trabalhando}
            gravadas={estado.gravadas || []}
          />

          <div className="migracao__acoes">
            <Botao
              variante="secundario"
              onClick={conferir}
              disabled={trabalhando}
              icone={<IconeRecarregar tamanho={15} />}
            >
              {fase === 'conferindo'
                ? 'Conferindo…'
                : relatorio
                  ? 'Conferir de novo'
                  : 'Conferir'}
            </Botao>
            <Botao
              variante="primario"
              onClick={() => setConfirmando(true)}
              disabled={!podeGravar}
              icone={<IconeExportar tamanho={15} />}
              title={
                podeGravar
                  ? 'Abre a confirmação da carga'
                  : 'Rode a conferência e resolva os impedimentos primeiro'
              }
            >
              {fase === 'gravando' ? 'Gravando…' : 'Gravar no BibLivre'}
            </Botao>
            {!conexao?.conectado && (
              <Botao
                variante="fantasma"
                onClick={aoAbrirBanco}
                icone={<IconeBanco tamanho={15} />}
              >
                Conectar ao Postgres
              </Botao>
            )}
          </div>

          {(fase === 'conferindo' || fase === 'gravando') && (
            <Passos passos={estado.passos} />
          )}

          {impedimentos.length > 0 && (
            <Aviso tom="erro" icone="⚠" titulo="Impedimentos — a gravação está barrada">
              <ul className="lista-recados">
                {impedimentos.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </Aviso>
          )}

          {relatorio && <Relatorio relatorio={relatorio} artefatos={estado.artefatos} />}

          {estado?.resultado && <Resultado resultado={estado.resultado} />}
        </>
      )}

      {confirmando && (
        <ModalGravarMigracao
          relatorio={relatorio}
          conectado={!!conexao?.conectado}
          ocupado={trabalhando}
          aoFechar={() => setConfirmando(false)}
          aoConfirmar={gravar}
        />
      )}
    </div>
  )
}

/* --- Envio do backup --- */

function Envio({ ocupado, entrada, aoEscolher }) {
  const [sobre, setSobre] = useState(false)

  return (
    <Moldura
      className={`envio ${sobre ? 'envio--sobre' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setSobre(true)
      }}
      onDragLeave={() => setSobre(false)}
      onDrop={(e) => {
        e.preventDefault()
        setSobre(false)
        aoEscolher(e.dataTransfer.files?.[0])
      }}
    >
      <EstadoVazio
        icone={<IconeLivro tamanho={26} />}
        titulo={ocupado ? 'Lendo o backup…' : 'Arraste o arquivo .bkp aqui'}
        acao={
          <>
            <input
              ref={entrada}
              type="file"
              accept=".bkp"
              className="so-leitor-de-tela"
              onChange={(e) => aoEscolher(e.target.files?.[0])}
            />
            <Botao
              variante="primario"
              onClick={() => entrada.current?.click()}
              disabled={ocupado}
            >
              Escolher arquivo
            </Botao>
          </>
        }
      >
        É o backup que o próprio Biblioteca Fácil gera. Ele fica no servidor
        enquanto a migração dura e some quando você clicar em “Descartar” — tem
        nome, CPF e endereço de leitores dentro.
      </EstadoVazio>
    </Moldura>
  )
}

/* --- O que veio dentro do backup --- */

function Backup({ estado }) {
  const tabelas = estado.tabelas || []
  return (
    <Moldura className="bloco">
      <div className="bloco__cabecalho">
        <h2 className="bloco__titulo">Backup enviado</h2>
        <span className="bloco__meta mono">
          {estado.arquivo} · {mb(estado.tamanho)} · {tabelas.length} tabelas
        </span>
      </div>
      <div className="rolagem-x">
        <table className="tabela-tabelas">
          <thead>
            <tr>
              <th>Tabela</th>
              <th>Descrição</th>
              <th className="num">Registros</th>
              <th>Layout</th>
            </tr>
          </thead>
          <tbody>
            {tabelas.map((t) => (
              <tr key={t.arquivo}>
                <td className="mono">{t.arquivo}</td>
                <td>{t.descricao}</td>
                <td className="num numero">{fmt(t.registros)}</td>
                <td>
                  <Selo tom={t.layout_valido ? 'existente' : 'alerta'}>
                    {t.layout_valido ? 'válido' : 'suspeito'}
                  </Selo>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Moldura>
  )
}

/* --- Opções --- */

function Opcoes({ valores, aoMudar, travado, gravadas }) {
  const [abertas, setAbertas] = useState(false)
  const repetidas = (gravadas || []).filter((e) => valores[e])

  return (
    <Moldura className="bloco">
      <div className="bloco__cabecalho">
        <h2 className="bloco__titulo">O que migrar</h2>
        <button
          type="button"
          className="bloco__link"
          onClick={() => setAbertas((a) => !a)}
        >
          {abertas ? 'Esconder ajustes' : 'Ajustes finos'}
        </button>
      </div>

      <div className="etapas">
        {ETAPAS.map(([chave, titulo, desc]) => (
          <label
            key={chave}
            className={`etapa ${valores[chave] ? 'etapa--ativa' : ''}`}
          >
            <input
              type="checkbox"
              checked={!!valores[chave]}
              disabled={travado}
              onChange={(e) => aoMudar(chave)(e.target.checked)}
            />
            <span className="etapa__corpo">
              <span className="etapa__titulo">{titulo}</span>
              <span className="etapa__desc">{desc}</span>
            </span>
          </label>
        ))}
      </div>

      {repetidas.length > 0 && (
        <Aviso tom="erro" icone="⚠" titulo="Etapa já gravada nesta execução">
          {repetidas.join(', ')} já entrou no banco. Gravar de novo duplicaria o
          cadastro — desmarque, ou descarte esta execução e comece outra.
        </Aviso>
      )}

      {valores.circulacao && !valores.leitores && (
        <Aviso tom="alerta" icone="⚠" titulo="Circulação sem leitores">
          O empréstimo aponta para um leitor. Sem migrar leitores agora, a
          circulação só funciona se eles já tiverem entrado numa execução
          anterior — é dela que sai o mapa que liga um ao outro.
        </Aviso>
      )}

      {abertas && (
        <div className="ajustes">
          <Chave
            rotulo="Incluir registros excluídos no sistema antigo"
            ajuda="A exclusão no Biblioteca Fácil é lógica: o registro continua no backup."
            valor={valores.incluir_excluidos}
            aoMudar={aoMudar('incluir_excluidos')}
            travado={travado}
          />
          <Chave
            rotulo="Só empréstimos em aberto"
            ajuda="Sem isto vem o histórico completo, devolvidos inclusive."
            valor={valores.apenas_abertos}
            aoMudar={aoMudar('apenas_abertos')}
            travado={travado}
          />
          <Chave
            rotulo="Incluir movimentações apagadas na origem"
            valor={valores.incluir_movimentacoes_excluidas}
            aoMudar={aoMudar('incluir_movimentacoes_excluidas')}
            travado={travado}
          />
          <Chave
            rotulo="Não migrar reservas"
            valor={valores.sem_reservas}
            aoMudar={aoMudar('sem_reservas')}
            travado={travado}
          />
          <Chave
            rotulo="Prosseguir com a base já ocupada"
            ajuda="Perigoso: a migração é carga de base nova. Só marque se souber por quê."
            tom="alerta"
            valor={valores.permitir_existentes}
            aoMudar={aoMudar('permitir_existentes')}
            travado={travado}
          />

          <div className="grade-form">
            <Campo
              rotulo="Prefixo do tombo"
              value={valores.prefixo_tombo || ''}
              disabled={travado}
              onChange={(e) => aoMudar('prefixo_tombo')(e.target.value)}
              ajuda="Vazio: usa o configurado no próprio BibLivre."
            />
            <Campo
              rotulo="Reservas a partir do ano"
              inputMode="numeric"
              value={valores.reservas_desde ?? ''}
              disabled={travado}
              onChange={(e) =>
                aoMudar('reservas_desde')(Number(e.target.value) || 0)
              }
              ajuda="0 traz todas as pendentes, inclusive as de anos atrás."
            />
            <Campo
              rotulo="Biblioteca depositária"
              value={valores.biblioteca || ''}
              disabled={travado}
              onChange={(e) => aoMudar('biblioteca')(e.target.value)}
              ajuda="541 $a do exemplar. Vazio: não preenche."
            />
          </div>
        </div>
      )}
    </Moldura>
  )
}

function Chave({ rotulo, ajuda, valor, aoMudar, travado, tom }) {
  return (
    <label className={`chave ${tom ? `chave--${tom}` : ''}`}>
      <input
        type="checkbox"
        checked={!!valor}
        disabled={travado}
        onChange={(e) => aoMudar(e.target.checked)}
      />
      <span>
        <span className="chave__rotulo">{rotulo}</span>
        {ajuda && <span className="chave__ajuda">{ajuda}</span>}
      </span>
    </label>
  )
}

/* --- Progresso --- */

function Passos({ passos }) {
  return (
    <Moldura className="bloco">
      <ol className="passos">
        {(passos || []).map((p) => (
          <li key={p.chave} className={`passo passo--${p.status}`}>
            <span className="passo__marca" aria-hidden="true">
              {p.status === 'ok' ? <IconeCheck tamanho={13} /> : null}
            </span>
            <span className="passo__rotulo">{p.rotulo}</span>
            {p.detalhe && <span className="passo__detalhe">{p.detalhe}</span>}
          </li>
        ))}
      </ol>
    </Moldura>
  )
}

/* --- Relatório da conferência --- */

function Relatorio({ relatorio, artefatos }) {
  const { acervo, leitores, circulacao, destino, avisos = [] } = relatorio

  const indicadores = [
    acervo && { n: fmt(acervo.obras), rotulo: 'obras', tom: 'nova',
                nota: 'Registros bibliográficos que nascem' },
    acervo && { n: fmt(acervo.exemplares), rotulo: 'exemplares',
                nota: 'Um por cópia física, com tombo próprio' },
    leitores && { n: fmt(leitores.total), rotulo: 'leitores',
                  nota: `${fmt(leitores.ativos)} ativos, ${fmt(leitores.inativos)} inativos` },
    circulacao && { n: fmt(circulacao.emprestimos), rotulo: 'empréstimos',
                    nota: `${fmt(circulacao.abertos)} em aberto` },
    circulacao && { n: fmt(circulacao.reservas), rotulo: 'reservas' },
  ].filter(Boolean)

  return (
    <>
      <FaixaIndicadores itens={indicadores} />

      {avisos.length > 0 && (
        <Aviso tom="alerta" icone="⚠" titulo="O que a conferência não garantiu">
          <ul className="lista-recados">
            {avisos.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Aviso>
      )}

      <div className="cartoes">
        {acervo && (
          <Cartao titulo="Acervo">
            <Linha rotulo="Registros no sistema antigo" valor={fmt(acervo.registros_origem)} />
            <Linha rotulo="Obras distintas" valor={fmt(acervo.obras)} />
            <Linha rotulo="Obras com 2+ exemplares" valor={fmt(acervo.obras_2_ou_mais)} />
            <Linha rotulo="Maior grupo" valor={`${fmt(acervo.maior_grupo)} cópias`} />
            <Linha rotulo="Com autor" valor={fmt(acervo.com_autor)} />
            <Linha rotulo="Com ISBN" valor={fmt(acervo.com_isbn)} />
            <Linha rotulo="Com CDD" valor={fmt(acervo.com_cdd)} />
          </Cartao>
        )}

        {leitores && (
          <Cartao titulo="Leitores">
            <Linha rotulo="Valores de campo" valor={fmt(leitores.valores)} />
            <Linha
              rotulo="Faixa de ids"
              valor={`${fmt(leitores.id_inicial)}–${fmt(leitores.id_final)}`}
            />
            <Linha rotulo="Endereço com número separado" valor={fmt(leitores.endereco_separado)} />
            <Linha rotulo="Nascimentos descartados" valor={fmt(leitores.nascimentos_invalidos)} />
            {destino?.campos_a_criar?.length > 0 && (
              <Linha
                rotulo="Campos a criar no BibLivre"
                valor={destino.campos_a_criar.length}
                nota={destino.campos_a_criar.join(', ')}
              />
            )}
          </Cartao>
        )}

        {circulacao && (
          <Cartao titulo="Circulação">
            <Linha rotulo="Movimentações na origem" valor={fmt(circulacao.movimentacoes_origem)} />
            <Linha rotulo="Devolvidos" valor={fmt(circulacao.devolvidos)} />
            <Linha rotulo="Multas" valor={fmt(circulacao.multas)} />
            <Linha rotulo="Excluídas na origem" valor={fmt(circulacao.excluidos_na_origem)} />
            {Object.entries(circulacao.descartes || {}).map(([motivo, n]) => (
              <Linha key={motivo} rotulo={`Descartadas: ${motivo.replace(/_/g, ' ')}`}
                     valor={fmt(n)} tom="alerta" />
            ))}
          </Cartao>
        )}

        {destino && (
          <Cartao titulo="No BibLivre, agora">
            <Linha rotulo="Registros bibliográficos" valor={fmt(destino.obras)} />
            <Linha rotulo="Exemplares" valor={fmt(destino.exemplares)} />
            <Linha rotulo="Usuários" valor={fmt(destino.leitores)} />
            <Linha rotulo="Empréstimos" valor={fmt(destino.emprestimos)} />
            <Linha
              rotulo="Prefixo do tombo"
              valor={destino.prefixo_tombo}
              nota={`de ${destino.origem_prefixo}`}
            />
          </Cartao>
        )}
      </div>

      {artefatos?.length > 0 && (
        <p className="migracao__arquivos">
          Arquivos de conferência:{' '}
          {artefatos.map((a, i) => (
            <span key={a.nome}>
              {i > 0 && ' · '}
              <a className="mono" href={api.migracao.urlArquivo(a.nome)}>
                {a.nome}
              </a>
            </span>
          ))}
        </p>
      )}
    </>
  )
}

function Cartao({ titulo, children }) {
  return (
    <Moldura className="cartao">
      <h3 className="cartao__titulo">{titulo}</h3>
      <dl className="cartao__lista">{children}</dl>
    </Moldura>
  )
}

function Linha({ rotulo, valor, nota, tom }) {
  return (
    <div className={`linha ${tom ? `linha--${tom}` : ''}`}>
      <dt>
        {rotulo}
        {nota && <span className="linha__nota">{nota}</span>}
      </dt>
      <dd className="numero">{valor}</dd>
    </div>
  )
}

/* --- Depois de gravar --- */

function Resultado({ resultado }) {
  return (
    <Moldura className="bloco bloco--sucesso">
      <div className="bloco__cabecalho">
        <h2 className="bloco__titulo">
          <IconeCheck tamanho={16} /> Migração concluída
        </h2>
        <span className="bloco__meta mono">{resultado.terminado_em}</span>
      </div>

      <div className="previa previa--fluida">
        <div className="previa__celula previa__celula--nova">
          <span className="previa__numero numero">{fmt(resultado.obras)}</span>
          <span className="microrrotulo">obras</span>
        </div>
        <div className="previa__celula">
          <span className="previa__numero numero">{fmt(resultado.exemplares)}</span>
          <span className="microrrotulo">exemplares</span>
        </div>
        <div className="previa__celula">
          <span className="previa__numero numero">{fmt(resultado.leitores)}</span>
          <span className="microrrotulo">leitores</span>
        </div>
        <div className="previa__celula">
          <span className="previa__numero numero">{fmt(resultado.emprestimos)}</span>
          <span className="microrrotulo">empréstimos</span>
        </div>
      </div>

      {resultado.avisos?.length > 0 && (
        <Aviso tom="alerta" icone="⚠" titulo="Ficou de fora">
          <ul className="lista-recados">
            {resultado.avisos.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Aviso>
      )}

      {/* O que a tela não consegue fazer sozinha: reindexar é ação do BibLivre
          e o restart do Tomcat é da máquina. Dizer isso aqui é a diferença
          entre um acervo que aparece na busca e um que "sumiu". */}
      <ol className="proximos">
        {(resultado.proximos_passos || []).map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ol>
    </Moldura>
  )
}
