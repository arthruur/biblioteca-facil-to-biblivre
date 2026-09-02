import { useState } from 'react'
import { api } from '../../api/client'
import { Aviso, Botao, Campo, IconeBanco, IconeCheck, Modal } from '../../components'

/**
 * Conexão com o Postgres do BibLivre.
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
      setErro(e.message || 'Não foi possível conectar ao banco de dados.')
    } finally {
      setConectando(false)
    }
  }

  return (
    <Modal
      titulo="Conexão com o PostgreSQL do BibLivre"
      aoFechar={aoFechar}
      rodape={
        <>
          <Botao variante="fantasma" onClick={aoFechar}>
            {sucesso ? 'Concluir' : 'Cancelar'}
          </Botao>
          <Botao variante="primario" onClick={conectar} disabled={conectando}>
            {conectando ? 'Conectando…' : 'Testar e Conectar'}
          </Botao>
        </>
      }
    >
      <Aviso icone={<IconeBanco tamanho={18} />}>
        A senha vive apenas na memória temporária do servidor — nunca é gravada em disco.
        Com a conexão ativa, o sistema verifica se o livro já existe no acervo e evita
        duplicatas.
      </Aviso>

      <div className="grade-form" style={{ marginTop: 'var(--e4)' }}>
        <Campo rotulo="Host / Endereço" {...campo('host')} placeholder="localhost" />
        <Campo rotulo="Porta" {...campo('port')} inputMode="numeric" placeholder="5432" />
        <Campo rotulo="Banco de Dados" {...campo('dbname')} placeholder="biblivre4" />
        <Campo rotulo="Usuário" {...campo('user')} placeholder="biblivre" />
        <Campo
          rotulo="Schema"
          {...campo('schema')}
          ajuda="Padrão: single"
          placeholder="single"
        />
        <Campo
          rotulo="Senha do Postgres"
          type="password"
          {...campo('senha')}
          onKeyDown={(e) => e.key === 'Enter' && conectar()}
          autoFocus
        />
      </div>

      {erro && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Aviso tom="erro" icone="⚠" titulo="Falha na conexão">
            {erro}
          </Aviso>
        </div>
      )}

      {sucesso && (
        <div style={{ marginTop: 'var(--e4)' }}>
          <Aviso tom="existente" icone={<IconeCheck tamanho={18} />} titulo="Conectado com sucesso!">
            {sucesso.obras?.toLocaleString('pt-BR')} obras e{' '}
            {sucesso.exemplares?.toLocaleString('pt-BR')} exemplares encontrados no acervo.{' '}
            {sucesso.fila?.avaliados > 0 && (
              <>
                A fila foi reavaliada contra o acervo: {sucesso.fila.no_acervo} de{' '}
                {sucesso.fila.avaliados}{' '}
                {sucesso.fila.no_acervo === 1 ? 'item já estava' : 'itens já estavam'} catalogados.
              </>
            )}
          </Aviso>
        </div>
      )}
    </Modal>
  )
}
