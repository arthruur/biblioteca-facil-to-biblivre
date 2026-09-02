"""
Verificação de fumaça do monorepo — roda sem banco, sem rede e sem câmera.

    python tests/verificar.py

Não é uma suíte completa: é o que impede uma reorganização de arquivos de
quebrar em silêncio o que já estava validado em campo. Cobre as três coisas
que doeriam mais se regredissem:

  1. as rotas que as telas consomem (docs/SPEC_UI.md §6) respondem e mantêm o
     contrato — inclusive o alias /api/carrinho, que ainda tem cliente;
  2. a fila sobrevive a reinício (é trabalho de gente, não cache);
  3. o MARC gerado agrupa por obra, separa volumes e monta o exemplar no
     formato que o BibLivre espera.

Usa uma pasta de dados temporária, então pode rodar com o servidor de pé.
"""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
os.environ["BIBLIO_DATA_DIR"] = tempfile.mkdtemp(prefix="biblio_teste_")
DADOS = Path(os.environ["BIBLIO_DATA_DIR"])

falhas: list[str] = []


def checar(rotulo, condicao, extra=""):
    print(("  ok   " if condicao else "  FALHA") + f"  {rotulo}"
          + (f"   {extra}" if extra and not condicao else ""))
    if not condicao:
        falhas.append(rotulo)


def secao(titulo):
    print(f"\n{titulo}")


# ---------------------------------------------------------------- API

def verificar_api():
    from fastapi.testclient import TestClient

    from biblio.api.main import app, preparar
    from biblio.biblivre import conexao, marc
    from biblio.catalogacao import config, fila as fila_mod

    secao("API — rotas, contrato e persistência")
    preparar()
    c = TestClient(app)

    checar("saúde responde", c.get("/api/saude").json()["status"] == "ok")
    checar("info do sistema tem server_url",
           "server_url" in c.get("/api/sistema/info").json())

    # Sem banco o sistema funciona, mas nunca finge que verificou.
    checar("acervo responde sem banco", c.get("/api/acervo/status").status_code == 200)
    checar("GET /api/db não devolve a senha",
           "senha" not in c.get("/api/db").json().get("config", {}))
    checar("ISBN não verificado não é 'existe'",
           c.get("/api/acervo/isbn/9786559870530").json()["existe"] is False)
    checar("credencial ruim vira 400, não 500",
           c.post("/api/db", json={"senha": "x", "host": "127.0.0.1", "port": 1})
           .status_code == 400)

    # Lote: injetado direto para não depender das APIs externas de ISBN.
    config.carrinho.append({
        "isbn": "9786559870530", "titulo": "2041", "autor": "Kai-Fu Lee",
        "quantidade": 1, "exemplares": 1, "acervo": None, "fonte": "teste",
    })
    checar("lote lista o item", c.get("/api/lote").json()["total"] == 1)
    checar("ISBN vazio é recusado",
           c.post("/api/lote", json={"isbn": ""}).status_code == 400)
    checar("stepper do lote grava",
           c.put("/api/lote/9786559870530", json={"quantidade": 3})
           .json()["quantidade"] == 3)
    checar("alias /api/carrinho ainda responde",
           c.get("/api/carrinho").json()["total"] == 1)
    checar("lote vai para a fila",
           c.post("/api/lote/enviar").json()["enviados"] == 1)

    fila = c.get("/api/fila").json()
    checar("item chegou na fila", fila["total"] == 1)
    item_id = fila["itens"][0]["id"]
    checar("quantidade preservada no envio", fila["itens"][0]["quantidade"] == 3)

    s = c.get("/api/fila/stats").json()
    checar("indicadores batem",
           s["a_exportar"] == 1 and s["exemplares"] == 3 and s["obras_novas"] == 1, s)

    checar("item inexistente é 404", c.get("/api/fila/nao-existe").status_code == 404)
    checar("edição de campo grava",
           c.put(f"/api/fila/{item_id}", json={"titulo": "2041 editado"})
           .json()["item"]["titulo"] == "2041 editado")
    checar("ação em lote marca revisado",
           c.post("/api/fila/acoes", json={"ids": [item_id], "acao": "revisado"})
           .json()["afetados"] == 1)
    checar("filtro por status", c.get("/api/fila?status=revisado").json()["total"] == 1)
    checar("busca acha", c.get("/api/fila?busca=editado").json()["total"] == 1)
    checar("busca sem resultado é 0", c.get("/api/fila?busca=zzzz").json()["total"] == 0)

    # A garantia §7.6: a fila é trabalho pendente, não cache.
    fila_mod.fila.clear()
    recarregados = fila_mod.carregar_do_disco()
    checar("fila sobrevive a reinício",
           recarregados == 1 and fila_mod.fila[0]["titulo"] == "2041 editado")

    # Export sem executar: gera arquivos e não encosta no acervo.
    d = c.post("/api/fila/exportar-biblivre", json={"executar": False}).json()
    checar("dry-run reporta 1 obra nova e 3 exemplares",
           d["status"] == "ok" and d["obras_novas"] == 1 and d["exemplares"] == 3, d)
    checar("MRC em disco", Path(d["mrc"]).exists())
    checar("CSV em disco", Path(d["csv"]).exists())
    checar("dry-run não marca como exportado",
           c.get(f"/api/fila/{item_id}").json()["status"] == "revisado")

    regs = marc.ler_mrc(d["mrc"])
    checar("MRC tem o registro", len(regs) == 1)
    checar("020 $a traz o ISBN", regs[0]["020"]["a"] == "9786559870530")
    checar("245 traz o título editado", "2041 editado" in str(regs[0].get("245")))
    checar("035 $a marca a origem", regs[0]["035"]["a"].startswith("(BF)"))

    # §7.2: gravação sem senha não acontece em silêncio.
    conexao.definir_db({"senha": "x"})
    conexao._db["senha"] = ""
    checar("gravar sem senha não grava",
           c.post("/api/fila/exportar-biblivre", json={"executar": True})
           .json()["status"] in ("senha_requerida", "gerado_sem_inserir"))

    checar("remoção apaga o arquivo",
           c.delete(f"/api/fila/{item_id}").status_code == 200
           and not list((DADOS / "fila").glob("fila_*.json")))

    # O frontend só existe depois do build; a API tem de subir de qualquer jeito.
    raiz = c.get("/")
    checar("/ responde (bundle ou aviso de build)",
           raiz.status_code in (200, 503), raiz.status_code)


# ---------------------------------------------- MARC e exemplares

COLUNAS = ["numacervo", "titulo", "subtitulo", "autor_principal",
           "autores_secundarios", "editora", "local_publicacao", "ano_edicao",
           "edicao", "volume", "exemplar", "tombo", "isbn", "paginas", "cdd",
           "cdu", "cutter", "idioma", "tipo_item", "classificacao", "assuntos",
           "localizacao", "notas", "data_aquisicao", "excluido_em", "chave_obra"]


def _linha(num, titulo, volume="", isbn=""):
    d = dict.fromkeys(COLUNAS, "")
    d.update(numacervo=str(num), titulo=titulo, autor_principal="ASSIS, MACHADO DE",
             editora="Globo", local_publicacao="Rio de Janeiro", ano_edicao="2022",
             volume=volume, exemplar="1", isbn=isbn, paginas="480", cdd="869.3",
             cutter="A848d", idioma="PORTUGUES", data_aquisicao="2026-01-15",
             localizacao="Estante A")
    return d


def verificar_migracao():
    from biblio.biblivre import exemplares, marc
    from biblio.legado import tabela

    secao("Migração — agrupamento por obra e formato do exemplar")

    entrada = DADOS / "consolidado.csv"
    with open(entrada, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        # Duas cópias do mesmo livro + dois volumes de uma coleção.
        w.writerow(_linha(100, "Dom Casmurro", isbn="9786559870530"))
        w.writerow(_linha(101, "Dom Casmurro", isbn="9786559870530"))
        w.writerow(_linha(102, "Palavra Aberta", volume="1"))
        w.writerow(_linha(103, "Palavra Aberta", volume="2"))

    linhas = marc.ler_csv_consolidado(entrada)
    grupos = marc.agrupar_por_obra(linhas)
    registros = [marc.montar_registro(g) for g in grupos]

    checar("4 exemplares viram 3 obras", len(grupos) == 3, len(grupos))
    dom = [r for r in registros if "Dom Casmurro" in str(r.get("245"))]
    checar("cópias do mesmo livro viram 1 ficha", len(dom) == 1)
    checar("as 2 cópias ficam no mesmo grupo",
           len(max(grupos, key=len)) == 2)

    palavra = [r for r in registros if "Palavra Aberta" in str(r.get("245"))]
    checar("volumes distintos NÃO são fundidos", len(palavra) == 2, len(palavra))
    checar("volume aparece no 245 $n",
           all(p.get("245").get("n", "").startswith("v.") for p in palavra))

    checar("090 leva CDD e Cutter (o exemplar herda)",
           dom[0]["090"]["a"] == "869.3" and dom[0]["090"]["b"] == "A848d")
    checar("041 traz o idioma", dom[0]["041"]["a"] == "por")
    checar("260 traz local, editora e ano",
           dom[0]["260"]["a"] == "Rio de Janeiro"
           and dom[0]["260"]["b"] == "Globo" and dom[0]["260"]["c"] == "2022")
    checar("100 ind1=1 quando o nome começa pelo sobrenome",
           dom[0]["100"].indicator1 == "1")

    mrc = DADOS / "obras.mrc"
    csv_ex = DADOS / "exemplares.csv"
    checar("escreve o MRC", marc.escrever_mrc(registros, mrc) == 3)
    checar("escreve 1 linha por exemplar",
           marc.escrever_csv_exemplares(grupos, csv_ex) == 4)
    checar("MRC relido bate", len(marc.ler_mrc(mrc)) == 3)

    rec, loc_d = exemplares.montar_exemplar(
        {"volume": "", "ordem_exemplar": 2, "data_aquisicao": "2026-01-15",
         "localizacao": "Estante A", "numacervo": "100", "tombo": ""},
        {"a": "869.3", "b": "A848d"}, "Bib.2026.7")
    checar("exemplar: 949 $a é o tombo", rec["949"]["a"] == "Bib.2026.7")
    checar("exemplar: 090 $d é ex.N", rec["090"]["d"] == "ex.2" and loc_d == "ex.2")
    checar("exemplar: 852 $c é a localização", rec["852"]["c"] == "Estante A")
    checar("exemplar: leader de holdings", rec.leader[6] == "u")

    tombos, _, invalidos = exemplares.gerar_tombos(
        [{"data_aquisicao": "2026-01-15", "numacervo": "1"},
         {"data_aquisicao": "2026-03-02", "numacervo": "2"},
         {"data_aquisicao": "1899-01-01", "numacervo": "3"}], "Bib")
    checar("tombos contam por ano", tombos[:2] == ["Bib.2026.1", "Bib.2026.2"], tombos)
    checar("data impossível não emite tombo em 1899", len(invalidos) == 1)

    checar("data do Biblioteca Fácil vira ISO",
           tabela.data_para_iso(739252) == "2025-01-01"
           and tabela.data_para_iso(0) == "")


# ------------------------------------------------------------ CLIs

def verificar_clis():
    secao("CLIs de migração — continuam de pé")
    for nome in ("extrair_bkp", "extrair_tabela", "consolidar", "gerar_marc",
                 "inserir_obras", "inserir_exemplares", "inserir_leitores",
                 "inserir_emprestimos", "servidor"):
        r = subprocess.run([sys.executable, f"scripts/{nome}.py", "--help"],
                           capture_output=True, text=True, cwd=RAIZ,
                           encoding="utf-8", errors="replace")
        checar(f"scripts/{nome}.py", r.returncode == 0,
               (r.stderr or r.stdout)[-400:])


def main():
    print(f"dados de teste em {DADOS}")
    verificar_api()
    verificar_migracao()
    verificar_clis()

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): {falhas}")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
