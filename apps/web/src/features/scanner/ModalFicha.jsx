import { useState } from 'react'
import { Aviso, Botao, Campo, Modal, Stepper } from '../../components'

/**
 * Ficha completa de um item do lote.
 *
 * É o único lugar da tela do celular que pede atenção, e por isso só abre a
 * toque. As edições valem para este lote (CDD e Cutter, que o lookup externo
 * quase nunca traz) e a quantidade de exemplares.
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
      titulo={item.titulo || 'Sem metadados'}
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
        <Aviso tom="existente" icone="✓" titulo="Este livro já está no acervo">
          Obra #{item.acervo.record_id} · {item.acervo.exemplares} exemplar(es)
          hoje. Não vai virar ficha nova — {quantidade}{' '}
          {quantidade === 1 ? 'exemplar entra' : 'exemplares entram'} nessa obra.
        </Aviso>
      )}

      <div className="ficha__topo" style={{ marginTop: noAcervo ? 'var(--e4)' : 0 }}>
        {item.capa ? (
          <img className="ficha__capa" src={item.capa} alt="" loading="lazy" />
        ) : (
          <div className="ficha__capa ficha__capa--vazia" aria-hidden="true">
            📕
          </div>
        )}
        <div style={{ minWidth: 0 }}>
          <p className="ficha__titulo">{item.titulo || '— sem metadados —'}</p>
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
          <p className="ficha__exemplares-rotulo">Exemplares</p>
          <p className="ficha__exemplares-ajuda">
            {noAcervo
              ? 'Quantas cópias entram na obra que já existe'
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
          placeholder="869.3"
          inputMode="decimal"
        />
        <Campo
          rotulo="Cutter"
          value={cutter}
          onChange={(e) => setCutter(e.target.value)}
          placeholder="A848d"
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
