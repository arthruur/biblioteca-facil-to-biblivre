import { useState } from 'react'
import {
  Aviso,
  Botao,
  Campo,
  IconeCheck,
  IconeExportar,
  IconeRecarregar,
  Modal,
} from '../../components'

/**
 * Confirmação obrigatória antes de qualquer escrita no acervo.
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

  const noAcervo = (itens || []).filter((i) => i.acervo?.existe)
  const novas = (itens || []).filter((i) => !i.acervo?.existe)
  const exemplares = (itens || []).reduce(
    (s, i) => s + (Number(i.quantidade) || 1),
    0
  )

  const precisaSenha = modo === 'gravar' && !conectado && !senha

  return (
    <Modal
      titulo="Exportar Acervo para o BibLivre"
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
            disabled={ocupado || precisaSenha || !itens?.length}
          >
            {ocupado
              ? 'Processando gravação…'
              : modo === 'gravar'
                ? 'Gravar agora no BibLivre'
                : 'Gerar arquivos MARC21 / CSV'}
          </Botao>
        </>
      }
    >
      {temSelecao && (
        <Aviso icone={<IconeCheck tamanho={16} />} titulo="Exportando seleção ativa">
          {itens.length} {itens.length === 1 ? 'item selecionado' : 'itens selecionados'} —
          o restante da fila não entrará nesta gravação.
        </Aviso>
      )}

      {!conectado && (
        <div style={{ marginTop: temSelecao ? 'var(--e3)' : 0 }}>
          <Aviso tom="alerta" icone="⚠" titulo="Banco PostgreSQL não conectado">
            Nenhum ISBN foi verificado previamente contra o acervo. Se gravar agora,{' '}
            <strong>todos os {itens.length} itens entrarão como obra nova</strong> —
            inclusive livros que a biblioteca já possa ter. Conecte antes, ou informe a
            senha do Postgres abaixo.
          </Aviso>
        </div>
      )}

      <div className="export__numeros">
        <div className="export__numero export__numero--nova">
          <strong>{novas.length}</strong>
          <span>{novas.length === 1 ? 'obra nova (novo registro)' : 'obras novas (novos registros)'}</span>
        </div>
        <div className="export__numero export__numero--existente">
          <strong>{noAcervo.length}</strong>
          <span>já no acervo (acrescenta exemplares)</span>
        </div>
        <div className="export__numero">
          <strong>{exemplares}</strong>
          <span>exemplares no total</span>
        </div>
      </div>

      {noAcervo.length > 0 && (
        <div style={{ marginTop: 'var(--e3)', marginBottom: 'var(--e3)' }}>
          <p
            className="campo__rotulo"
            style={{ marginBottom: 'var(--e2)' }}
          >
            Livros já existentes (não duplicarão ficha)
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
                <code className="mono">
                  #{i.acervo.record_id} +{Number(i.quantidade) || 1} ex
                </code>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="export__modo">
        <button
          type="button"
          className="export__opcao"
          aria-pressed={modo === 'gravar'}
          onClick={() => setModo('gravar')}
        >
          <strong>🚀 Gravar agora no BibLivre</strong>
          <span>
            Insere diretamente no PostgreSQL numa transação segura. Nada é gravado pela metade.
          </span>
        </button>

        <button
          type="button"
          className="export__opcao"
          aria-pressed={modo === 'arquivos'}
          onClick={() => setModo('arquivos')}
        >
          <strong>📄 Gerar arquivos (.mrc + .csv)</strong>
          <span>
            Apenas exporta os arquivos MARC21 e CSV na pasta de dados, sem alterar o banco de dados.
          </span>
        </button>
      </div>

      {modo === 'gravar' && !conectado && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Campo
            rotulo="Senha do PostgreSQL"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            ajuda="Necessária para autorizar a gravação direta no banco."
            autoFocus
          />
        </div>
      )}

      {modo === 'gravar' && novas.length > 0 && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Aviso tom="nova" icone={<IconeRecarregar tamanho={16} />}>
            {novas.length === 1 ? '1 obra nova nasce' : `${novas.length} obras novas nascem`}{' '}
            neste export — após a gravação, lembre-se de reindexar no BibLivre (Administração
            → Manutenção → Reindexar) para que apareçam na busca pública.
          </Aviso>
        </div>
      )}
    </Modal>
  )
}
