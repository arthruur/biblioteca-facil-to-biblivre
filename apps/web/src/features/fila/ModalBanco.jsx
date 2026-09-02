import { useState } from 'react'
import { api } from '../../api/client'
import { Aviso, Botao, Campo, Modal } from '../../components'

/**
 * Conexão com o Postgres do BibLivre.
 *
 * Conectar não é só ligar um cabo: ao dar certo, a fila inteira é reavaliada
 * contra o acervo e itens que pareciam "obra nova" podem virar "+N
 * exemplares". Por isso o resultado diz quantos mudaram — é a informação que
 * muda a decisão de quem estava prestes a exportar.
 */
export function ModalBanco({ estadoInicial, aoFechar, aoConectar }) {
  const cfg = estadoInicial?.config || {}
  const [dados, setDados] = useState({
    host: cfg.host || 'localhost',
    port: cfg.port || 5432,
    dbname: cfg.dbname || 'biblivre4',
    user: cfg.user || 'biblivre',
    schema: cfg.schema || 'single',
    senha: '',
  })
  const [conectando, setConectando] = useState(false)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState(null)

  const campo = (k) => ({
    value: dados[k],
    onChange: (e) => setDados((d) => ({ ...d, [k]: e.target.value })),
  })

  const conectar = async () => {
    if (!dados.senha) {
      setErro('Informe a senha do Postgres.')
      return
    }
    setConectando(true)
    setErro('')
    try {
      const r = await api.db.conectar({ ...dados, port: Number(dados.port) })
      setSucesso(r)
      aoConectar(r)
    } catch (e) {
      setErro(e.message || 'Não foi possível conectar.')
    } finally {
      setConectando(false)
    }
  }

  return (
    <Modal
      titulo="Conexão com o BibLivre"
      aoFechar={aoFechar}
      rodape={
        <>
          <Botao variante="fantasma" onClick={aoFechar}>
            {sucesso ? 'Fechar' : 'Cancelar'}
          </Botao>
          <Botao variante="primario" onClick={conectar} disabled={conectando}>
            {conectando ? 'Conectando…' : 'Conectar'}
          </Botao>
        </>
      }
    >
      <Aviso icone="🔒">
        A senha vive só na memória do servidor — nunca vai para disco. Sem
        conexão o sistema funciona igual, mas trata <strong>todo</strong> livro
        como obra nova, e o risco vira duplicata no acervo.
      </Aviso>

      <div className="grade-form" style={{ marginTop: 'var(--e4)' }}>
        <Campo rotulo="Host" {...campo('host')} />
        <Campo rotulo="Porta" {...campo('port')} inputMode="numeric" />
        <Campo rotulo="Banco" {...campo('dbname')} />
        <Campo rotulo="Usuário" {...campo('user')} />
        <Campo
          rotulo="Schema"
          {...campo('schema')}
          ajuda="single, na instalação padrão"
        />
        <Campo
          rotulo="Senha"
          type="password"
          {...campo('senha')}
          onKeyDown={(e) => e.key === 'Enter' && conectar()}
          autoFocus
        />
      </div>

      {erro && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Aviso tom="erro" icone="⚠" titulo="Não conectou">
            {erro}
          </Aviso>
        </div>
      )}

      {sucesso && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Aviso tom="existente" icone="✓" titulo="Conectado">
            {sucesso.obras?.toLocaleString('pt-BR')} obras e{' '}
            {sucesso.exemplares?.toLocaleString('pt-BR')} exemplares no acervo.{' '}
            {sucesso.fila?.avaliados > 0 && (
              <>
                A fila foi reavaliada: {sucesso.fila.no_acervo} de{' '}
                {sucesso.fila.avaliados}{' '}
                {sucesso.fila.no_acervo === 1
                  ? 'item já está'
                  : 'itens já estão'}{' '}
                no acervo.
              </>
            )}
          </Aviso>
        </div>
      )}
    </Modal>
  )
}
