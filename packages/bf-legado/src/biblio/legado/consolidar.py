"""
Cruza Acervo + Autores + Editoras + Idiomas + Tipos + Classificação num único
CSV, já com os nomes de coluna que serão usados na geração do MARC21.

    from biblio.legado.consolidar import consolidar
    df = consolidar("saida/")

CHAVES E RELACIONAMENTOS (todos confirmados contra os dados reais)
-------------------------------------------------------------------
    T09_ACER.NUMACERVO      PK do item de acervo
    T09_ACER.NUMEDITORA  -> T06_EDIT.NUMEDITORA
    T09_ACER.NUMIDIOMA   -> T14_IDIO.NUMIDIOMA
    T09_ACER.NUMTIPOITEM -> T08_TIPO.NUMTIPOITEM
    T09_ACER.NUMCLASSIFIC-> T07_CLAS.NUMCLASSIFIC
    T10_AUAC (Autores nas Obras) é a tabela N:N entre acervo e autores:
        T10_NUMACERVO -> T09_ACER.NUMACERVO
        T10_NUMAUTOR  -> T05_AUTO.NUMAUTOR

T10_SEQUENCIA é um sequencial GLOBAL da tabela de vínculos (não reinicia por
obra), então não existe um campo explícito de "ordem do autor". Usamos a
ordem crescente de SEQUENCIA como ordem de entrada: o primeiro vínculo
cadastrado vira o autor principal (MARC 100) e os demais viram autores
secundários (MARC 700). Isso é uma heurística, não um dado do sistema.

EXEMPLARES: o Biblioteca Fácil grava CADA EXEMPLAR FÍSICO como um registro
separado do acervo (16.258 registros para 13.696 obras distintas; há títulos
com até 62 cópias). A coluna `chave_obra` agrupa os registros que descrevem a
mesma obra, para quem quiser gerar 1 registro bibliográfico + N exemplares em
vez de 16.258 registros bibliográficos duplicados.

EXCLUSAO: é um campo de data, não um booleano — 0 significa "ativo" e
qualquer data significa "excluído naquele dia" (exclusão lógica). Por padrão
os registros excluídos ficam de fora; use --incluir-excluidos para mantê-los.
"""

import pandas as pd

from . import tabela as bf


def _df(pasta, arquivo):
    tab = bf.carregar(pasta, arquivo)
    if not tab.validar():
        raise SystemExit(
            f"{arquivo}: layout do cabeçalho não valida — "
            f"verifique se o .dat foi extraído corretamente"
        )
    return pd.DataFrame(list(tab.registros()))


def _mapa(pasta, arquivo, col_id, col_valor, col_excl):
    """Dicionário {id: valor} de uma tabela de apoio, sem os excluídos."""
    df = _df(pasta, arquivo)
    df = df[df[col_excl] == 0]
    return dict(zip(df[col_id], df[col_valor].str.strip()))


def consolidar(pasta, incluir_excluidos=False) -> pd.DataFrame:
    acervo = _df(pasta, "T09_ACER.dat")
    vinculos = _df(pasta, "T10_AUAC.dat")

    autores = _mapa(pasta, "T05_AUTO.dat",
                    "T05_NUMAUTOR", "T05_AUTOR", "T05_EXCLUSAO")
    editoras = _mapa(pasta, "T06_EDIT.dat",
                     "T06_NUMEDITORA", "T06_EDITORA", "T06_EXCLUSAO")
    idiomas = _mapa(pasta, "T14_IDIO.dat",
                    "T14_NUMIDIOMA", "T14_IDIOMA", "T14_EXCLUSAO")
    tipos = _mapa(pasta, "T08_TIPO.dat",
                  "T08_NUMTIPOITEM", "T08_TIPOITEM", "T08_EXCLUSAO")
    classif = _mapa(pasta, "T07_CLAS.dat",
                    "T07_NUMCLASSIFIC", "T07_CLASSIFICACAO", "T07_EXCLUSAO")

    edit = _df(pasta, "T06_EDIT.dat")
    edit = edit[edit["T06_EXCLUSAO"] == 0]
    local_editora = dict(
        zip(edit["T06_NUMEDITORA"], edit["T06_LOCALIZACAO"].str.strip())
    )

    if not incluir_excluidos:
        acervo = acervo[acervo["T09_EXCLUSAO"] == 0]

    # Autores por obra, na ordem em que foram vinculados (SEQUENCIA crescente).
    vinculos = vinculos.sort_values("T10_SEQUENCIA")
    vinculos["nome"] = vinculos["T10_NUMAUTOR"].map(autores)
    vinculos = vinculos.dropna(subset=["nome"])
    por_obra = vinculos.groupby("T10_NUMACERVO")["nome"].apply(list)

    lista_autores = acervo["T09_NUMACERVO"].map(por_obra)
    lista_autores = lista_autores.apply(lambda v: v if isinstance(v, list) else [])

    out = pd.DataFrame({
        "numacervo": acervo["T09_NUMACERVO"],
        "titulo": acervo["T09_TITULO"].str.strip(),
        "subtitulo": acervo["T09_SUBTITULO"].str.strip(),
        "autor_principal": lista_autores.apply(lambda v: v[0] if v else ""),
        "autores_secundarios": lista_autores.apply(lambda v: "; ".join(v[1:])),
        "editora": acervo["T09_NUMEDITORA"].map(editoras).fillna(""),
        "local_publicacao": acervo["T09_NUMEDITORA"].map(local_editora).fillna(""),
        "ano_edicao": acervo["T09_ANOEDICAO2"].str.strip(),
        "edicao": acervo["T09_EDICAO"].str.strip(),
        "volume": acervo["T09_VOLUME"].str.strip(),
        "exemplar": acervo["T09_EXEMPLAR"].str.strip(),
        "tombo": acervo["T09_TOMBO"],
        "isbn": acervo["T09_ISBN"].str.strip(),
        "paginas": acervo["T09_PAGINAS"],
        "cdd": acervo["T09_CDD"].str.strip(),
        "cdu": acervo["T09_CDU"].str.strip(),
        "cutter": acervo["T09_CUTTER"].str.strip(),
        "idioma": acervo["T09_NUMIDIOMA"].map(idiomas).fillna(""),
        "tipo_item": acervo["T09_NUMTIPOITEM"].map(tipos).fillna(""),
        "classificacao": acervo["T09_NUMCLASSIFIC"].map(classif).fillna(""),
        "assuntos": acervo[[f"T09_PALAVRAS{i}" for i in range(1, 6)]].apply(
            lambda r: "; ".join(x.strip() for x in r if x.strip()), axis=1
        ),
        "localizacao": acervo["T09_LOCAL"].str.strip(),
        "notas": acervo[["T09_OBS1", "T09_OBS2"]].apply(
            lambda r: " ".join(x.strip() for x in r if x.strip()), axis=1
        ),
        "data_aquisicao": acervo["T09_AQUISICAO"].map(bf.data_para_iso),
        "excluido_em": acervo["T09_EXCLUSAO"].map(bf.data_para_iso),
    })

    # Chave para agrupar exemplares da mesma obra num único registro
    # bibliográfico, se for essa a escolha na hora de gerar o MARC.
    out["chave_obra"] = (
        out["titulo"].str.casefold() + "|"
        + out["subtitulo"].str.casefold() + "|"
        + out["editora"].str.casefold() + "|"
        + out["ano_edicao"]
    )

    return out.sort_values("numacervo").reset_index(drop=True)
