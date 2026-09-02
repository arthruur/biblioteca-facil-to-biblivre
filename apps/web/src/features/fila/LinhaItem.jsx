import { useState } from 'react'
import {
  Botao,
  Campo,
  IconeCheck,
  IconeEditar,
  IconeLivro,
  IconePendente,
  IconeRemover,
  Stepper,
} from '../../components'
import { Destino, Situacao } from './Destino'

/** Os 12 campos que a revisão pode corrigir (docs/SPEC_UI.md §4). */
const CAMPOS = [
  ['titulo', 'Título'],
  ['subtitulo', 'Subtítulo'],
  ['autor', 'Autor'],
  ['editora', 'Editora'],
  ['ano', 'Ano'],
  ['edicao', 'Edição'],
  ['paginas', 'Páginas'],
  ['idioma', 'Idioma'],
  ['isbn', 'ISBN'],
  ['cdd', 'CDD'],
  ['cutter', 'Cutter'],
  ['localizacao', 'Localização'],
]

export function LinhaItem({
  item,
  conectado,
  selecionado,
  editando,
  aoSelecionar,
  aoEditar,
  aoSalvar,
  aoMudarQuantidade,
  aoAlternarRevisado,
  aoRemover,
}) {
  const exportado = item.status === 'exportado'
  const semTitulo = !(item.titulo || '').trim()

  return (
    <>
      <tr
        className={[
          selecionado && 'linha--selecionada',
          exportado && 'linha--exportado',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <td className="col-check">
          <input
            type="checkbox"
            checked={selecionado}
            onChange={() => aoSelecionar(item.id)}
            aria-label={`Selecionar ${item.titulo || item.isbn}`}
          />
        </td>

        <td className="col-capa">
          {item.capa ? (
            <img className="mini-capa" src={item.capa} alt="" loading="lazy" />
          ) : (
            <span className="mini-capa mini-capa--vazia" aria-hidden="true">
              <IconeLivro tamanho={18} />
            </span>
          )}
        </td>

        <td>
          <p className={`obra__titulo${semTitulo ? ' obra__titulo--vazio' : ''}`}>
            {semTitulo ? '— sem metadados —' : item.titulo}
          </p>
          <p className="obra__linha2">
            {[item.autor, item.editora, item.ano].filter(Boolean).join(' · ') ||
              'nenhum metadado veio das bases externas'}
          </p>
        </td>

        <td>
          <span className="obra__isbn mono">{item.isbn || '—'}</span>
          {item.fonte && <p className="obra__fonte">{item.fonte}</p>}
        </td>

        <td>
          <Destino item={item} conectado={conectado} />
        </td>

        <td className="col-ex">
          {exportado ? (
            <span className="mono">{item.quantidade}</span>
          ) : (
            <Stepper
              valor={item.quantidade}
              aoMudar={(q) => aoMudarQuantidade(item.id, q)}
            />
          )}
        </td>

        <td className="col-situacao">
          <Situacao status={item.status} />
        </td>

        <td className="col-acoes">
          {!exportado && (
            <div className="acoes-linha">
              <Botao
                variante="fantasma"
                className="btn--icone"
                onClick={() => aoEditar(editando ? null : item.id)}
                title="Editar campos da obra"
                aria-label="Editar campos"
              >
                <IconeEditar tamanho={14} />
              </Botao>
              <Botao
                variante="fantasma"
                className="btn--icone"
                onClick={() => aoAlternarRevisado(item)}
                title={
                  item.status === 'revisado'
                    ? 'Voltar para pendente'
                    : 'Marcar como revisado'
                }
                aria-label={
                  item.status === 'revisado'
                    ? 'Voltar para pendente'
                    : 'Marcar como revisado'
                }
              >
                {item.status === 'revisado' ? (
                  <IconePendente tamanho={14} />
                ) : (
                  <IconeCheck tamanho={14} />
                )}
              </Botao>
              <Botao
                variante="fantasma"
                className="btn--icone"
                onClick={() => aoRemover(item)}
                title="Remover da fila"
                aria-label="Remover da fila"
              >
                <IconeRemover tamanho={14} />
              </Botao>
            </div>
          )}
        </td>
      </tr>

      {editando && (
        <tr className="editor">
          <td colSpan={8}>
            <Editor item={item} aoSalvar={aoSalvar} aoFechar={() => aoEditar(null)} />
          </td>
        </tr>
      )}
    </>
  )
}

function Editor({ item, aoSalvar, aoFechar }) {
  const [rascunho, setRascunho] = useState(() =>
    Object.fromEntries(CAMPOS.map(([c]) => [c, item[c] ?? '']))
  )

  const isbnMudou = (rascunho.isbn || '') !== (item.isbn || '')

  return (
    <div>
      <div className="editor__grade">
        {CAMPOS.map(([campo, rotulo], i) => (
          <Campo
            key={campo}
            autoFocus={i === 0}
            rotulo={rotulo}
            value={rascunho[campo]}
            onChange={(e) =>
              setRascunho((r) => ({ ...r, [campo]: e.target.value }))
            }
            largo={campo === 'titulo' || campo === 'subtitulo'}
          />
        ))}
      </div>
      <div className="editor__rodape">
        <p className="editor__dica">
          {isbnMudou
            ? 'O ISBN mudou — ao salvar, o destino é reconsultado no acervo e pode virar outro.'
            : 'Estes campos vão para o MARC gerado no export.'}
        </p>
        <div style={{ display: 'flex', gap: 'var(--e2)' }}>
          <Botao variante="fantasma" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao
            variante="primario"
            onClick={() => {
              aoSalvar(item.id, rascunho)
              aoFechar()
            }}
          >
            Salvar alterações
          </Botao>
        </div>
      </div>
    </div>
  )
}
