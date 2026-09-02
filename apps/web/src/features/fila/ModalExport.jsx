import { useState } from 'react'
import { Aviso, Botao, Campo, IconeCheck, Modal } from '../../components'

const MODOS = [
  [
    'gravar',
    'Gravar agora no BibLivre',
    'Insere direto no PostgreSQL numa transação só: ou entra tudo, ou não entra nada.',
  ],
  [
    'arquivos',
    'Só gerar os arquivos',
    'Escreve o .mrc e o .csv na pasta de dados e não toca no banco.',
  ],
]

/**
 * Confirmação obrigatória antes de qualquer escrita no acervo.
 *
 * A prévia vem primeiro e em número grande: quantas fichas nascem, quantas
 * obras só ganham exemplar, quantos exemplares no total. Depois dela vem a
 * lista nominal dos que entram como exemplar — é a única forma de a pessoa
 * conferir que a deduplicação acertou antes de a transação rodar.
 */
export function ModalExport({
  itens,
  conectado,
  temSelecao,
  aoFechar,
  aoConfirmar,
  ocupado,
}) {
  const [modo, setModo] = useState('gravar')
  const [senha, setSenha] = useState('')

  const lista = itens || []
  const noAcervo = lista.filter((i) => i.acervo?.existe)
  const novas = lista.filter((i) => !i.acervo?.existe)
  const exemplares = lista.reduce((s, i) => s + (Number(i.quantidade) || 1), 0)

  const precisaSenha = modo === 'gravar' && !conectado && !senha

  return (
    <Modal
      titulo="Confirmar gravação no BibLivre"
      largo
      aoFechar={aoFechar}
      fecharNoFundo={false}
      rodape={
        <>
          <Botao variante="secundario" onClick={aoFechar} disabled={ocupado}>
            Cancelar
          </Botao>
          <Botao
            variante={modo === 'gravar' ? 'primario' : 'secundario'}
            onClick={() => aoConfirmar({ executar: modo === 'gravar', senha })}
            disabled={ocupado || precisaSenha || !lista.length}
          >
            {ocupado
              ? 'Processando…'
              : modo === 'gravar'
                ? 'Gravar agora'
                : 'Gerar arquivos'}
          </Botao>
        </>
      }
    >
      {temSelecao && (
        <Aviso icone={<IconeCheck tamanho={15} />} titulo="Exportando só a seleção">
          {lista.length} {lista.length === 1 ? 'item selecionado' : 'itens selecionados'} —
          o restante da fila não entra nesta gravação.
        </Aviso>
      )}

      <div className="previa">
        <div className="previa__celula previa__celula--nova">
          <span className="previa__numero numero">{novas.length}</span>
          <span className="microrrotulo">
            {novas.length === 1 ? 'obra nova' : 'obras novas'}
          </span>
        </div>
        <div className="previa__celula previa__celula--existente">
          <span className="previa__numero numero">{noAcervo.length}</span>
          <span className="microrrotulo">já no acervo</span>
        </div>
        <div className="previa__celula">
          <span className="previa__numero numero">{exemplares}</span>
          <span className="microrrotulo">
            {exemplares === 1 ? 'exemplar' : 'exemplares'}
          </span>
        </div>
      </div>

      {!conectado && (
        <Aviso tom="alerta" icone="⚠" titulo="Banco desconectado">
          Nenhum ISBN foi verificado contra o acervo. Se gravar agora,{' '}
          <strong style={{ display: 'inline' }}>todos</strong> os {lista.length} itens
          entram como obra nova — inclusive os que a biblioteca já tem. Conecte antes,
          ou informe a senha do Postgres abaixo.
        </Aviso>
      )}

      {noAcervo.length > 0 && (
        <div>
          <p className="microrrotulo" style={{ marginBottom: 6 }}>
            Entram como exemplar em obra existente
          </p>
          <ul className="export-lista">
            {noAcervo.map((i) => (
              <li key={i.id}>
                <span className="export-lista__titulo">{i.titulo || i.isbn}</span>
                <code className="export-lista__destino mono">
                  #{i.acervo.record_id} +{Number(i.quantidade) || 1} ex
                </code>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="modos">
        {MODOS.map(([valor, titulo, desc]) => (
          <button
            key={valor}
            type="button"
            className={`modos__opcao ${modo === valor ? 'modos__opcao--ativa' : ''}`}
            aria-pressed={modo === valor}
            onClick={() => setModo(valor)}
          >
            <span className="modos__titulo">{titulo}</span>
            <span className="modos__desc">{desc}</span>
          </button>
        ))}
      </div>

      {modo === 'gravar' && !conectado && (
        <Campo
          rotulo="Senha do PostgreSQL"
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          ajuda="Vive só na memória do processo do servidor; nunca vai para disco."
          autoFocus
        />
      )}

      <p className="export-nota">
        Uma transação só: ou entra tudo, ou não entra nada. Os arquivos{' '}
        <code className="mono">obras_*.mrc</code> e{' '}
        <code className="mono">exemplares_*.csv</code> são escritos em disco nos dois
        modos.
        {modo === 'gravar' && novas.length > 0 && (
          <>
            {' '}
            {novas.length === 1 ? 'A obra nova exige' : 'As obras novas exigem'}{' '}
            reindexar no BibLivre (Administração → Manutenção → Reindexar) para
            aparecer na busca pública.
          </>
        )}
      </p>
    </Modal>
  )
}
