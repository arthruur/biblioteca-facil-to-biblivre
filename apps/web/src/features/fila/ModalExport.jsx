import { useState } from 'react'
import { Aviso, Botao, Campo, Modal } from '../../components'

/**
 * Confirmação obrigatória antes de qualquer escrita no acervo.
 *
 * A garantia da spec (§7.2): nenhuma gravação sem que a tela mostre **antes**
 * quantas fichas nascem e quantas são reaproveitadas. Os dois modos têm
 * rótulos deliberadamente diferentes — "gerar arquivos" e "gravar agora" não
 * podem parecer o mesmo botão.
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

  const noAcervo = itens.filter((i) => i.acervo?.existe)
  const novas = itens.filter((i) => !i.acervo?.existe)
  const exemplares = itens.reduce((s, i) => s + (Number(i.quantidade) || 1), 0)

  const precisaSenha = modo === 'gravar' && !conectado && !senha

  return (
    <Modal
      titulo="Exportar para o BibLivre"
      largo
      aoFechar={aoFechar}
      fecharNoFundo={false}
      rodape={
        <>
          <Botao variante="fantasma" onClick={aoFechar} disabled={ocupado}>
            Cancelar
          </Botao>
          <Botao
            variante={modo === 'gravar' ? 'primario' : 'secundario'}
            onClick={() => aoConfirmar({ executar: modo === 'gravar', senha })}
            disabled={ocupado || precisaSenha}
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
        <Aviso icone="☑" titulo="Só o que está selecionado">
          {itens.length} {itens.length === 1 ? 'item selecionado' : 'itens selecionados'} —
          o resto da fila não entra neste export.
        </Aviso>
      )}

      {!conectado && (
        <div style={{ marginTop: temSelecao ? 'var(--e3)' : 0 }}>
          <Aviso tom="alerta" icone="⚠" titulo="Banco desconectado">
            Nenhum ISBN foi verificado contra o acervo. Se gravar assim,{' '}
            <strong>todos os {itens.length} itens entram como obra nova</strong> —
            inclusive livros que a biblioteca já tem. Conecte antes, ou informe a
            senha abaixo.
          </Aviso>
        </div>
      )}

      <div className="export__numeros">
        <div className="export__numero export__numero--nova">
          <strong>{novas.length}</strong>
          <span>{novas.length === 1 ? 'obra nova' : 'obras novas'}</span>
        </div>
        <div className="export__numero export__numero--existente">
          <strong>{noAcervo.length}</strong>
          <span>já no acervo</span>
        </div>
        <div className="export__numero">
          <strong>{exemplares}</strong>
          <span>exemplares no total</span>
        </div>
      </div>

      {noAcervo.length > 0 && (
        <>
          <p
            className="campo__rotulo"
            style={{ marginBottom: 'var(--e2)' }}
          >
            Não vão virar ficha nova
          </p>
          <ul className="export__lista">
            {noAcervo.map((i) => (
              <li key={i.id}>
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {i.titulo || i.isbn}
                </span>
                <code>
                  #{i.acervo.record_id} +{Number(i.quantidade) || 1}
                </code>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="export__modo">
        <button
          className="export__opcao"
          aria-pressed={modo === 'arquivos'}
          onClick={() => setModo('arquivos')}
        >
          <strong>Gerar arquivos</strong>
          <span>
            Só escreve o .mrc e o .csv em data/export. Nada entra no acervo.
          </span>
        </button>
        <button
          className="export__opcao"
          aria-pressed={modo === 'gravar'}
          onClick={() => setModo('gravar')}
        >
          <strong>Gravar agora</strong>
          <span>
            Escreve no BibLivre numa transação só. Não existe gravar metade.
          </span>
        </button>
      </div>

      {modo === 'gravar' && !conectado && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Campo
            rotulo="Senha do Postgres"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            ajuda="Necessária porque o banco não está conectado nesta sessão."
            autoFocus
          />
        </div>
      )}

      {modo === 'gravar' && novas.length > 0 && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Aviso tom="nova" icone="↻">
            {novas.length === 1 ? 'Uma obra nova nasce' : `${novas.length} obras novas nascem`}{' '}
            neste export — depois de gravar será preciso reindexar (Administração
            → Manutenção → Reindexar) para elas aparecerem na busca.
          </Aviso>
        </div>
      )}
    </Modal>
  )
}
