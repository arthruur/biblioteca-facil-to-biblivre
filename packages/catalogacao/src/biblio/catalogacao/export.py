"""
Exportacao para o BibLivre 5, com dedup por ISBN.

A regra que move este modulo: **um ISBN que ja esta no acervo nao vira ficha
nova**. Antes de gerar qualquer MARC, cada item da fila e confrontado com o
indice de ISBN do banco (`acervo.py`) e cai num de dois caminhos:

  novo      -> registro bibliografico (biblio_records) + N exemplares
  existente -> so N exemplares (biblio_holdings) no record_id que ja existe

Os arquivos `obras_<ts>.mrc` e `exemplares_<ts>.csv` continuam sendo gerados
para conferencia — o MRC so com as obras novas, o CSV com todos os exemplares,
marcando de qual caminho cada linha veio.
"""

import csv
from datetime import datetime
from pathlib import Path

from biblio.biblivre import acervo, exemplares, marc, obras
from biblio.biblivre.marc import chave_obra, montar_registro

from .config import EXPORT_DIR

CABECALHO_CSV = [
    "caminho", "id_origem", "numacervo", "record_id", "ordem_exemplar", "tombo",
    "exemplar_origem", "volume", "localizacao", "data_aquisicao", "isbn", "titulo",
]


def _item_para_linha(item: dict, numacervo: int) -> dict:
    """Mapeia item do lote/fila (Google Books/BrasilAPI/OpenLibrary) para linha do CSV."""
    return {
        "numacervo": str(numacervo),
        "titulo": item.get("titulo") or "",
        "subtitulo": item.get("subtitulo") or "",
        "autor_principal": item.get("autor") or "",
        "editora": item.get("editora") or "",
        "local_publicacao": "",
        "ano_edicao": (item.get("ano") or "")[:4],
        "volume": item.get("volume") or "",
        "edicao": item.get("edicao") or "",
        "isbn": (item.get("isbn") or "").replace("-", ""),
        "cdd": item.get("cdd") or "",
        "cdu": item.get("cdu") or "",
        "cutter": item.get("cutter") or "",
        "paginas": (item.get("paginas") or "").replace(" p.", "").strip(),
        "notas": item.get("notas") or item.get("descricao") or "",
        "assuntos": "",
        "autores_secundarios": "",
        "idioma": item.get("idioma") or "por",
        "tombo": "",
        "exemplar": "1",
        "localizacao": item.get("localizacao") or "",
        "data_aquisicao": datetime.now().strftime("%Y-%m-%d"),
    }


def _proximo_numacervo(export_dir: Path, base: int = 900000) -> int:
    """Continua a numeracao de origem dos exports anteriores (nao colide com a migracao)."""
    maior = base
    for arq in export_dir.glob("exemplares_*.csv"):
        try:
            with open(arq, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    try:
                        n = int(r.get("numacervo") or 0)
                    except ValueError:
                        continue
                    if n > maior:
                        maior = n
        except Exception:
            continue
    return maior + 1 if maior > base else base


def classificar(itens: list[dict], usar_banco: bool = True) -> tuple[list[dict], list[dict]]:
    """
    Separa os itens em (novos, existentes), reconsultando o acervo na hora.

    Reconsultar importa: entre o bipe no celular e o export podem ter passado
    horas, e alguem pode ter catalogado o mesmo titulo pela tela do BibLivre
    nesse meio-tempo.
    """
    buscar = None
    if usar_banco:
        try:
            # Indice vazio = banco indisponivel (ou acervo vazio). Nos dois casos
            # nao ha o que comparar, e vale mais respeitar a marca que o item ja
            # traz do que declarar tudo "novo" por falta de conexao.
            if acervo.indice(forcar=True):
                buscar = acervo.buscar
        except Exception:
            buscar = None

    novos: list[dict] = []
    existentes: list[dict] = []
    for item in itens:
        achado = buscar(item.get("isbn")) if buscar else None
        if achado is None and (item.get("acervo") or {}).get("existe") and not buscar:
            # Sem banco agora, mas o item foi marcado quando havia: respeita a marca.
            achado = {"record_id": item["acervo"]["record_id"],
                      "titulo": item["acervo"].get("titulo", ""),
                      "exemplares": item["acervo"].get("exemplares", 0),
                      "id_origem": item["acervo"].get("id_origem", "")}
        if achado:
            existentes.append({**item, "acervo": {"existe": True, **achado}})
        else:
            novos.append({**item, "acervo": None})
    return novos, existentes


def exportar_itens(itens: list[dict], executar: bool = False,
                   db_args: dict | None = None) -> dict:
    """
    Gera os arquivos de conferencia e, com executar=True, grava no BibLivre.

    Devolve status, contagens, caminhos e a lista de ids da fila efetivamente
    gravados (para o chamador marcar como exportados).
    """
    if not itens:
        return {"status": "vazio", "mensagem": "Nada para exportar"}

    export_dir = EXPORT_DIR
    export_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    novos, existentes = classificar(itens)

    # --- obras novas: uma linha por exemplar, agrupadas em obra pelo conteudo ---
    numacervo = _proximo_numacervo(export_dir)
    linhas_novas: list[dict] = []
    origem_por_item: list[tuple[dict, int]] = []
    for it in novos:
        qtd = max(1, int(it.get("quantidade") or it.get("exemplares") or 1))
        primeiro = numacervo
        for _ in range(qtd):
            linhas_novas.append(_item_para_linha(it, numacervo))
            numacervo += 1
        origem_por_item.append((it, primeiro))

    grupos: dict[str, list[dict]] = {}
    for linha in linhas_novas:
        grupos.setdefault(chave_obra(linha), []).append(linha)
    # Ordem estavel: a mesma em que os registros entram no MRC e no banco
    grupos_ordenados = sorted(grupos.values(), key=lambda g: min(int(x["numacervo"]) for x in g))

    mrc_path = export_dir / f"obras_{ts}.mrc"
    csv_path = export_dir / f"exemplares_{ts}.csv"

    marc.escrever_mrc((montar_registro(g) for g in grupos_ordenados), mrc_path)

    exemplares_novos = len(linhas_novas)
    exemplares_existentes = sum(
        max(1, int(i.get("quantidade") or i.get("exemplares") or 1)) for i in existentes)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f_ex:
        ex_writer = csv.writer(f_ex)
        ex_writer.writerow(CABECALHO_CSV)
        for grupo in grupos_ordenados:
            origem = min(int(g["numacervo"]) for g in grupo)
            for i, g in enumerate(sorted(grupo, key=lambda x: int(x["numacervo"])), start=1):
                ex_writer.writerow(["novo", f"(BF){origem}", g["numacervo"], "", i,
                                    g["tombo"], g["exemplar"], g["volume"],
                                    g["localizacao"], g["data_aquisicao"],
                                    g["isbn"], g["titulo"]])
        for it in existentes:
            rec_id = it["acervo"]["record_id"]
            qtd = max(1, int(it.get("quantidade") or it.get("exemplares") or 1))
            for i in range(1, qtd + 1):
                ex_writer.writerow(["existente", it["acervo"].get("id_origem", ""), "",
                                    rec_id, i, "", "1", it.get("volume") or "",
                                    it.get("localizacao") or "",
                                    datetime.now().strftime("%Y-%m-%d"),
                                    it.get("isbn") or "", it.get("titulo") or ""])

    resultado: dict = {
        "status": "ok",
        "obras_novas": len(grupos_ordenados),
        "obras_existentes": len(existentes),
        "exemplares_novos": exemplares_novos,
        "exemplares_existentes": exemplares_existentes,
        "exemplares": exemplares_novos + exemplares_existentes,
        "detalhe_existentes": [
            {"isbn": i.get("isbn"), "titulo": i.get("titulo"),
             "record_id": i["acervo"]["record_id"],
             "exemplares_atuais": i["acervo"].get("exemplares", 0),
             "acrescentar": max(1, int(i.get("quantidade") or 1))}
            for i in existentes
        ],
        "mrc": str(mrc_path),
        "csv": str(csv_path),
        "ids": [i.get("id") for i in itens if i.get("id")],
    }
    resumo = (f"{len(grupos_ordenados)} obra(s) nova(s) + "
              f"{len(existentes)} ja no acervo; "
              f"{exemplares_novos + exemplares_existentes} exemplar(es).")
    resultado["mensagem"] = resumo

    if not executar:
        resultado["mensagem"] += " Marque 'Inserir no Biblivre' e informe a senha para gravar."
        return resultado

    senha = (db_args or {}).get("senha") or (db_args or {}).get("password")
    if not senha:
        resultado["status"] = "senha_requerida"
        resultado["erro_insercao"] = "Senha do Postgres nao informada"
        resultado["mensagem"] += " Arquivos gerados; a gravacao precisa da senha."
        return resultado

    try:
        resultado.update(_gravar(grupos_ordenados, origem_por_item, existentes, mrc_path, db_args))
    except Exception as e:
        resultado["status"] = "gerado_sem_inserir"
        resultado["erro_insercao"] = str(e)
        resultado["ids"] = []
        resultado["mensagem"] += (f" Falha ao gravar: {e}. MRC/CSV ja estao em disco — "
                                  "da para rodar o CLI de obras a mao.")
    return resultado


def _gravar(grupos_ordenados, origem_por_item, existentes, mrc_path, db_args) -> dict:
    """Insere obras e exemplares numa transacao so."""
    cfg = {**(db_args or {})}
    schema = cfg.get("schema") or "single"
    con = acervo.conectar(cfg)
    try:
        registros = marc.ler_mrc(mrc_path)
        if len(registros) != len(grupos_ordenados):
            raise RuntimeError(
                f"MRC tem {len(registros)} registro(s) para {len(grupos_ordenados)} grupo(s)")

        record_id_por_numacervo: dict[int, int] = {}
        inseridos = 0
        if registros:
            ids_novos = obras.inserir(con, registros)
            inseridos = len(ids_novos)
            for rec_id, grupo in zip(ids_novos, grupos_ordenados):
                for linha in grupo:
                    record_id_por_numacervo[int(linha["numacervo"])] = rec_id

        # Exemplares: obras novas (record_id recem-criado) + obras que ja existiam
        pedidos = []
        for item, primeiro_numacervo in origem_por_item:
            rec_id = record_id_por_numacervo.get(primeiro_numacervo)
            if rec_id is None:
                continue
            pedidos.append({
                "record_id": rec_id, "novo": True,
                "quantidade": max(1, int(item.get("quantidade") or 1)),
                "isbn": item.get("isbn") or "", "titulo": item.get("titulo") or "",
                "numacervo": primeiro_numacervo,
                "localizacao": item.get("localizacao") or "",
                "volume": item.get("volume") or "",
            })
        for item in existentes:
            pedidos.append({
                "record_id": item["acervo"]["record_id"], "novo": False,
                "quantidade": max(1, int(item.get("quantidade") or 1)),
                "isbn": item.get("isbn") or "", "titulo": item.get("titulo") or "",
                "localizacao": item.get("localizacao") or "",
                "volume": item.get("volume") or "",
            })

        info_ex = exemplares.inserir_para_obras(con, pedidos, schema=schema)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        try:
            con.close()
        except Exception:
            pass

    acervo.invalidar()

    partes = []
    if inseridos:
        partes.append(f"{inseridos} obra(s) nova(s) em biblio_records")
    if existentes:
        partes.append(f"{len(existentes)} obra(s) reaproveitada(s) do acervo")
    partes.append(f"{info_ex['inseridos']} exemplar(es) em biblio_holdings")
    aviso = (" Rode Administracao -> Manutencao -> Reindexar para as obras novas "
             "aparecerem na busca."
             if inseridos else " Nenhuma obra nova: reindex nao e necessario.")

    return {
        "status": "ok",
        "inseridos": inseridos,
        "exemplares_inseridos": info_ex["inseridos"],
        "tombos": info_ex["tombos"][:50],
        "reindex_necessario": bool(inseridos),
        "mensagem": "Gravado: " + ", ".join(partes) + "." + aviso,
    }
