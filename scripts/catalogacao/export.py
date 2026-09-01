"""Exportacao integrada para Biblivre 5 via pipeline existente (gerar_marc -> inserir_obras)."""

import csv
import io
import tempfile
from datetime import datetime
from pathlib import Path

from pymarc import MARCWriter

from .config import DATA_DIR

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gerar_marc import montar_registro  # type: ignore


def _item_para_linha(item: dict, numacervo: int) -> dict:
    """Mapeia item do carrinho/fila (Google Books/Open Library) para linha do CSV consolidado."""
    # gerar_marc espera estes campos — preenchemos o essencial, resto vazio
    return {
        "numacervo": str(numacervo),
        "titulo": item.get("titulo") or "",
        "subtitulo": item.get("subtitulo") or "",
        "autor_principal": item.get("autor") or "",
        "editora": item.get("editora") or "",
        "local_publicacao": "",
        "ano_edicao": (item.get("ano") or "")[:4],
        "volume": "",
        "edicao": item.get("edicao") or "",
        "isbn": (item.get("isbn") or "").replace("-", ""),
        "cdd": item.get("cdd") or "",
        "cdu": item.get("cdu") or "",
        "cutter": item.get("cutter") or "",
        "paginas": (item.get("paginas") or "").replace(" p.", "").strip(),
        "notas": item.get("descricao") or "",
        "assuntos": "",
        "autores_secundarios": "",
        "idioma": item.get("idioma") or "por",
        # Campos de exemplar (para exemplares.csv)
        "tombo": "",
        "exemplar": "1",
        "localizacao": "",
        "data_aquisicao": datetime.now().strftime("%Y-%m-%d"),
    }


def exportar_itens(itens: list[dict], executar: bool = False, db_args: dict | None = None) -> dict:
    """
    Gera obras.mrc + exemplares.csv a partir dos itens e, se executar=True,
    insere direto no Biblivre via inserir_obras/inserir_exemplares.

    Retorna dict com status, caminhos e contagens.
    """
    if not itens:
        return {"status": "vazio", "mensagem": "Nada para exportar"}

    export_dir = DATA_DIR / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # numacervo base alto para nao colidir com migracao (14k existentes)
    base = 900000
    # Descobrir proximo disponivel varrendo exports anteriores
    try:
        existentes = list(export_dir.glob("exemplares_*.csv"))
        if existentes:
            max_n = base
            for f in existentes:
                try:
                    with open(f, encoding="utf-8-sig") as fh:
                        for r in csv.DictReader(fh):
                            n = int(r.get("numacervo") or 0)
                            if n > max_n:
                                max_n = n
                except Exception:
                    pass
            base = max_n + 1
    except Exception:
        pass

    # Expandir quantidade: mesmo ISBN com N exemplares vira N linhas (mesma obra, N holdings)
    linhas: list[dict] = []
    n = base
    for it in itens:
        qtd = int(it.get("quantidade") or it.get("exemplares") or 1)
        for _ in range(max(1, qtd)):
            linhas.append(_item_para_linha(it, n))
            n += 1

    # Agrupar por obra (mesma chave do gerar_marc) — cada ISBN distinto vira obra
    import gerar_marc as _gm  # type: ignore

    grupos: dict[str, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(_gm.chave_obra(linha), []).append(linha)

    mrc_path = export_dir / f"obras_{ts}.mrc"
    csv_path = export_dir / f"exemplares_{ts}.csv"

    n_ex = 0
    with open(mrc_path, "wb") as f_mrc, open(csv_path, "w", encoding="utf-8-sig", newline="") as f_ex:
        writer = MARCWriter(f_mrc)
        ex_writer = csv.writer(f_ex)
        ex_writer.writerow(["id_origem", "numacervo", "ordem_exemplar", "tombo", "exemplar_origem", "volume", "localizacao", "data_aquisicao", "titulo"])
        for grupo in sorted(grupos.values(), key=lambda g: int(g[0]["numacervo"])):
            writer.write(montar_registro(grupo))
            origem = min(int(g["numacervo"]) for g in grupo)
            for i, g in enumerate(sorted(grupo, key=lambda x: int(x["numacervo"])), start=1):
                ex_writer.writerow([f"(BF){origem}", g["numacervo"], i, g["tombo"], g["exemplar"], g["volume"], g["localizacao"], g["data_aquisicao"], g["titulo"]])
                n_ex += 1
        writer.close()

    resultado: dict = {
        "status": "ok",
        "obras": len(grupos),
        "exemplares": n_ex,
        "mrc": str(mrc_path),
        "csv": str(csv_path),
        "mensagem": f"{len(grupos)} obra(s), {n_ex} exemplar(es) gerados.",
    }

    if not executar:
        resultado["mensagem"] += " Para gravar no Biblivre, chame com executar=true e senha."
        return resultado

    # Exigir senha via frontend — nunca pedir no terminal (getpass bloqueia o servidor)
    senha = (db_args or {}).get("senha") or (db_args or {}).get("password")
    if not senha:
        resultado["status"] = "senha_requerida"
        resultado["erro_insercao"] = "Senha do Postgres nao informada"
        resultado["mensagem"] += " MRC/CSV gerados, mas insercao requer senha. Informe no frontend."
        return resultado

    # Insercao automatica via inserir_obras / inserir_exemplares
    try:
        from inserir_obras import set_cf001, set_cf005, set_cf008, conectar, INSERT_SQL, MATERIAL, DATABASE, USUARIO_PADRAO  # type: ignore
        from pymarc import MARCReader

        # Args de conexao
        import argparse

        # Usa defaults do inserir_obras (localhost/biblivre/biblivre4) ou db_args
        class Args:
            host = (db_args or {}).get("host", "localhost")
            port = (db_args or {}).get("port", 5432)
            dbname = (db_args or {}).get("dbname", "biblivre4")
            user = (db_args or {}).get("user", "biblivre")
            senha = (db_args or {}).get("senha") or (db_args or {}).get("password")
            schema = (db_args or {}).get("schema", "single")
            database = DATABASE
            usuario = USUARIO_PADRAO

        args = Args()
        with open(mrc_path, "rb") as f:
            registros = list(MARCReader(f, to_unicode=True, force_utf8=True))

        con = conectar(args)  # type: ignore
        try:
            with con.cursor() as cur:
                cur.execute("SELECT last_value, is_called FROM biblio_records_id_seq")
                last_value, is_called = cur.fetchone()
            id_inicial = last_value + 1 if is_called else last_value
            agora = datetime.now()
            valores = []
            for offset, rec in enumerate(registros):
                rec_id = id_inicial + offset
                set_cf001(rec, rec_id)
                set_cf005(rec, agora)
                set_cf008(rec, agora)
                iso = rec.as_marc().decode("utf-8")
                valores.append((rec_id, iso, MATERIAL, args.database, args.usuario))

            # Consome sequence e insere
            with con.cursor() as cur:
                cur.execute("SELECT nextval('biblio_records_id_seq') FROM generate_series(1, %s)", (len(valores),))
                ids_reais = [r[0] for r in cur.fetchall()]
            if ids_reais != [v[0] for v in valores]:
                raise RuntimeError("Sequence divergiu durante gravacao")

            from psycopg2.extras import execute_batch

            with con.cursor() as cur:
                execute_batch(cur, INSERT_SQL, valores, page_size=500)
            con.commit()

            # Exemplares: insere holdings via inserir_exemplares usando o CSV gerado
            try:
                import subprocess, sys, os

                env = os.environ.copy()
                # passa senha via env para nao expor em ps, se nao houver db_args usa PGPASSWORD ja existente
                if senha:
                    env["PGPASSWORD"] = senha
                cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "inserir_exemplares.py"), str(csv_path), "--executar", "--permitir-existentes"]
                if senha and "--senha" in open(str(Path(__file__).resolve().parents[1] / "inserir_exemplares.py"), encoding="utf-8").read():
                    cmd += ["--senha", senha]
                subprocess.run(cmd, check=False, env=env)
            except Exception:
                pass

            resultado["inseridos"] = len(valores)
            resultado["mensagem"] += f" Inseridos {len(valores)} registro(s) em biblio_records (reindex necessario)."
        finally:
            try:
                con.close()
            except Exception:
                pass
    except Exception as e:
        resultado["status"] = "gerado_sem_inserir"
        resultado["erro_insercao"] = str(e)
        resultado["mensagem"] += f" Falha ao inserir automaticamente: {e}. MRC/CSV ja gerados — rode inserir_obras.py manualmente."

    return resultado
