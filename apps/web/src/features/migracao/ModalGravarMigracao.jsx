import { useState } from 'react'
import { Aviso, Botao, Campo, Modal } from '../../components'

const fmt = (n) => (Number(n) || 0).toLocaleString('pt-BR')

/**
 * A última porta antes da carga.
 *
 * O modal do export diário mostra a prévia e pede a senha; aqui é preciso mais
 * do que isso, e o motivo é o tamanho: são dezenas de milhares de linhas numa
 * base de produção, e a tela não tem desfazer. Então o número aparece de novo,
 * por extenso, e a caixa de ciência precisa ser marcada — não para punir quem
 * já decidiu, mas para que ninguém chegue aqui de raspão e clique.
 */
export function ModalGravarMigracao({
  relatorio,
  conectado,
  ocupado,
  aoFechar,
  aoConfirmar,
}) {
  const [senha, setSenha] = useState('')
  const [ciente, setCiente] = useState(false)

  const acervo = relatorio?.acervo
  const leitores = relatorio?.leitores
  const circulacao = relatorio?.circulacao
  const avisos = relatorio?.avisos || []
  const precisaSenha = !conectado && !senha

  return (
    <Modal
      titulo="Confirmar a migração para o BibLivre"
      largo
      aoFechar={aoFechar}
      fecharNoFundo={false}
      rodape={
        <>
          <Botao variante="secundario" onClick={aoFechar} disabled={ocupado}>
            Cancelar
          </Botao>
          <Botao
            variante="primario"
            onClick={() => aoConfirmar({ senha })}
            disabled={ocupado || precisaSenha || !ciente}
          >
            {ocupado ? 'Gravando…' : 'Gravar agora'}
          </Botao>
        </>
      }
    >
      <div className="previa previa--fluida">
        {acervo && (
          <>
            <div className="previa__celula previa__celula--nova">
              <span className="previa__numero numero">{fmt(acervo.obras)}</span>
              <span className="microrrotulo">obras</span>
            </div>
            <div className="previa__celula">
              <span className="previa__numero numero">{fmt(acervo.exemplares)}</span>
              <span className="microrrotulo">exemplares</span>
            </div>
          </>
        )}
        {leitores && (
          <div className="previa__celula">
            <span className="previa__numero numero">{fmt(leitores.total)}</span>
            <span className="microrrotulo">leitores</span>
          </div>
        )}
        {circulacao && (
          <div className="previa__celula">
            <span className="previa__numero numero">{fmt(circulacao.emprestimos)}</span>
            <span className="microrrotulo">empréstimos</span>
          </div>
        )}
      </div>

      {avisos.length > 0 && (
        <Aviso tom="alerta" icone="⚠" titulo="Confira antes">
          <ul className="lista-recados">
            {avisos.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Aviso>
      )}

      {!conectado && (
        <Campo
          rotulo="Senha do PostgreSQL"
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          ajuda="Vive só na memória do processo do servidor; nunca vai para disco."
          autoFocus
        />
      )}

      <label className="ciencia">
        <input
          type="checkbox"
          checked={ciente}
          onChange={(e) => setCiente(e.target.checked)}
        />
        <span>
          Entendi que isto grava direto no banco do BibLivre e que a tela não
          desfaz. Se algo falhar no meio, a transação inteira é revertida — mas
          uma carga concluída só se desfaz restaurando um backup do PostgreSQL.
        </span>
      </label>

      <p className="export-nota">
        Uma transação só, do primeiro registro bibliográfico à última reserva.
        Depois de gravar ainda faltam dois passos fora daqui: reindexar a base
        no BibLivre e reiniciar o Tomcat — a tela repete os dois no fim.
      </p>
    </Modal>
  )
}
