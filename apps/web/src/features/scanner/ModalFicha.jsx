import { useState } from 'react'
import { Aviso, Botao, Campo, IconeCheck, IconeLivro, Modal, Stepper } from '../../components'

/**
 * Ficha completa de um item do lote.
 */
export function ModalFicha({ item, aoFechar, aoSalvar, aoRemover }) {
  const [cdd, setCdd] = useState(item.cdd || '')
  const [cutter, setCutter] = useState(item.cutter || '')
  const [quantidade, setQuantidade] = useState(Number(item.quantidade) || 1)

  const noAcervo = item.acervo?.existe
  const meta = [item.ano, item.paginas && `${item.paginas} p.`, item.editora]
    .filter(Boolean)
    .join(' · ')

  const fecharSalvando = () => {
    aoSalvar({ cdd: cdd.trim(), cutter: cutter.trim(), quantidade })
    aoFechar()
  }

  return (
    <Modal
      titulo={item.titulo || 'Ficha do Livro'}
      aoFechar={fecharSalvando}
      rodape={
        <>
          <Botao
            variante="perigo"
            onClick={() => {
              aoRemover(item.isbn)
              aoFechar()
            }}
          >
            Tirar do lote
          </Botao>
          <Botao variante="primario" onClick={fecharSalvando}>
            Pronto
          </Botao>
        </>
      }
    >
      {noAcervo && (
        <Aviso
          tom="existente"
          icone={<IconeCheck tamanho={18} />}
          titulo="Este livro já está cadastrado no acervo"
        >
          Obra #{item.acervo.record_id} · {item.acervo.exemplares} exemplar(es)
          existentes hoje. Não criará registro novo — {quantidade}{' '}
          {quantidade === 1 ? 'exemplar adicional entrará' : 'exemplares adicionais entrarão'} nesta obra.
        </Aviso>
      )}

      <div className="ficha__topo" style={{ marginTop: noAcervo ? 'var(--e4)' : 0 }}>
        {item.capa ? (
          <img className="ficha__capa" src={item.capa} alt="" loading="lazy" />
        ) : (
          <div className="ficha__capa ficha__capa--vazia" aria-hidden="true">
            <IconeLivro tamanho={32} />
          </div>
        )}
        <div style={{ minWidth: 0 }}>
          <p className="ficha__titulo">{item.titulo || '— sem título informado —'}</p>
          {item.subtitulo && <p className="ficha__autor">{item.subtitulo}</p>}
          <p className="ficha__autor">{item.autor || 'Autor não informado'}</p>
          <p className="ficha__meta">
            {meta || 'Nenhum metadado veio das bases externas'}
          </p>
        </div>
      </div>

      {item.descricao && <p className="ficha__descricao">{item.descricao}</p>}

      <div className="ficha__exemplares">
        <div>
          <p className="ficha__exemplares-rotulo">Quantidade de Exemplares</p>
          <p className="ficha__exemplares-ajuda">
            {noAcervo
              ? 'Quantas cópias entram na obra já existente'
              : 'Quantas cópias físicas deste título'}
          </p>
        </div>
        <Stepper valor={quantidade} aoMudar={setQuantidade} grande />
      </div>

      <div className="ficha__dados">
        <Campo
          rotulo="CDD"
          value={cdd}
          onChange={(e) => setCdd(e.target.value)}
          placeholder="Ex: 869.3"
          inputMode="decimal"
        />
        <Campo
          rotulo="Cutter"
          value={cutter}
          onChange={(e) => setCutter(e.target.value)}
          placeholder="Ex: A848d"
        />
      </div>

      <div className="ficha__dados">
        <Dado rotulo="ISBN" valor={item.isbn} mono />
        <Dado rotulo="Idioma" valor={item.idioma} />
        <Dado rotulo="Fonte do metadado" valor={item.fonte} />
      </div>
    </Modal>
  )
}

function Dado({ rotulo, valor, mono }) {
  return (
    <div className="campo">
      <span className="campo__rotulo">{rotulo}</span>
      <span className={mono ? 'mono' : undefined} style={{ fontSize: 'var(--txt-sm)' }}>
        {valor || '—'}
      </span>
    </div>
  )
}
