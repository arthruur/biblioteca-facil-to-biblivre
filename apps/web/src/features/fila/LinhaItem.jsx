import { useState } from 'react'
import {
  Botao,
  Campo,
  IconeCheck,
  IconeEditar,
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

        <td>
          {item.capa ? (
            <img className="mini-capa" src={item.capa} alt="" loading="lazy" />
          ) : (
            <span className="mini-capa mini-capa--vazia hachura" aria-hidden="true" />
          )}
        </td>

        <td>
          <p className={`obra__titulo${semTitulo ? ' obra__titulo--vazio' : ''}`}>
            {semTitulo ? 'sem metadados' : item.titulo}
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

        <td>
          {exportado ? (
            <span className="mono">{item.quantidade}</span>
          ) : (
            <Stepper
              valor={item.quantidade}
              aoMudar={(q) => aoMudarQuantidade(item.id, q)}
            />
          )}
        </td>

        <td>
          <Situacao status={item.status} />
        </td>

        <td>
          {!exportado && (
            <div className="acoes-linha">
              <Botao
                variante="secundario"
                className="btn--icone"
                onClick={() => aoEditar(editando ? null : item.id)}
                title="Editar campos da obra"
                aria-label="Editar campos"
              >
                <IconeEditar tamanho={13} />
              </Botao>
              <Botao
                variante="secundario"
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
                  <IconePendente tamanho={13} />
                ) : (
                  <IconeCheck tamanho={13} />
                )}
              </Botao>
              <Botao
                variante="secundario"
                className="btn--icone"
                onClick={() => aoRemover(item)}
                title="Remover da fila"
                aria-label="Remover da fila"
              >
                <IconeRemover tamanho={13} />
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
    <div className="editor__caixa">
      <div className="editor__cabecalho">
        <span className="editor__titulo">Editar item</span>
        <span className="editor__dica">
          Alterar o ISBN reconsulta o acervo — o destino pode mudar na hora.
        </span>
      </div>

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
        <Botao
          variante="primario"
          onClick={() => {
            aoSalvar(item.id, rascunho)
            aoFechar()
          }}
        >
          Salvar
        </Botao>
        <Botao variante="secundario" onClick={aoFechar}>
          Cancelar (Esc)
        </Botao>
        <span className="editor__previa">
          {isbnMudou
            ? 'ISBN alterado: o destino será reconsultado ao salvar.'
            : 'Estes campos vão para o MARC gerado no export.'}
        </span>
      </div>
    </div>
  )
}
