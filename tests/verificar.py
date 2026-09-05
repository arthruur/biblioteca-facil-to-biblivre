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
     formato que o BibLivre espera;
  4. a migração pela tela vai do `.bkp` ao commit — com um backup sintético
     (`amostra_bkp.py`) e um banco de mentira (`banco_falso.py`), porque um
     botão que grava dezenas de milhares de linhas não pode ter como única
     verificação "rodou uma vez em campo".

Usa uma pasta de dados temporária, então pode rodar com o servidor de pé.
"""

import csv
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# `amostra_bkp` e `banco_falso` são deste diretório: o backup sintético e o
# banco de mentira que a verificação da migração usa.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Antes de qualquer import de `biblio.*`: sem isto o `.env` da maquina entra no
# ambiente, a checagem de ISBN liga sozinha e os casos de "obra nova" passam a
# consultar o acervo real — o teste deixaria de ser reproduzivel.
os.environ["BIBLIO_SEM_ENV"] = "1"
for _chave in ("PGPASSWORD", "BIBLIVRE_DB_SENHA"):
    os.environ.pop(_chave, None)

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
    from biblio.catalogacao import config, fila as fila_mod, lotes

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
    lotes.semear({
        "isbn": "9786559870530", "titulo": "2041", "autor": "Kai-Fu Lee",
        "fonte": "teste",
    }, dispositivo="celular-de-teste")
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

    # Multi-aparelho: cada celular tem a sua bandeja, e enviar uma nao leva a
    # outra. Roda com a fila ja vazia para nao mexer nas contagens acima.
    lotes.zerar()
    lotes.semear({"isbn": "9786559870530", "titulo": "2041", "fonte": "teste"},
                 dispositivo="celular-da-ana")
    lotes.semear({"isbn": "9788535914849", "titulo": "Sapiens",
                  "fonte": "teste"}, dispositivo="celular-do-balcao")
    painel = c.get("/api/lotes").json()
    checar("cada aparelho tem sua bandeja", len(painel["dispositivos"]) == 2,
           painel)
    checar("painel soma os dois aparelhos", painel["titulos"] == 2)
    checar("enviar um aparelho nao leva o outro",
           c.post("/api/lotes/celular-do-balcao/enviar").json()["enviados"] == 1)
    checar("bandeja do aparelho nao enviado fica intacta",
           c.get("/api/lote", headers={"X-Dispositivo": "celular-da-ana"})
           .json()["total"] == 1)
    checar("renomear aparelho pega",
           c.put("/api/lotes/celular-da-ana", json={"nome": "Celular da Ana"})
           .json()["nome"] == "Celular da Ana")
    checar("versao do painel sobe a cada mudanca",
           c.get("/api/lotes").json()["versao"] > painel["versao"])
    checar("bipe do celular nao vai para o lote do balcao",
           c.get("/api/lote", headers={"X-Dispositivo": "balcao"})
           .json()["total"] == 0)

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


# ------------------------------------------------- Migração pela tela

def _esperar(execucao, segundos=60):
    """A conferência roda numa thread; a tela busca em laço, o teste também."""
    limite = time.time() + segundos
    while execucao.ocupado() and time.time() < limite:
        time.sleep(0.05)
    return execucao.estado()


def verificar_migracao_pela_tela():
    """
    Do `.bkp` ao commit, com um backup sintético e um banco de mentira.

    A migração virou botão de tela, e um botão que grava dezenas de milhares de
    linhas no PostgreSQL da biblioteca precisa de mais garantia do que "rodou
    uma vez em campo". Backup real não entra no repositório (tem dado pessoal),
    então `tests/amostra_bkp.py` escreve um com a mesma forma, e
    `tests/banco_falso.py` responde ao que a carga pergunta — ver os dois
    módulos para o que este teste NÃO cobre.
    """
    from fastapi.testclient import TestClient

    from biblio.api.main import app
    from biblio.migracao import execucao, pipeline

    from amostra_bkp import amostra
    from banco_falso import BancoFalso

    secao("Migração pela tela — .bkp → conferência → gravação")
    c = TestClient(app)
    backup = amostra()

    checar("estado vazio antes de qualquer envio",
           c.get("/api/migracao").json()["fase"] == "vazio")
    checar("conferir sem backup é 409",
           c.post("/api/migracao/conferir", json={}).status_code == 409)

    r = c.post("/api/migracao/backup",
               files={"arquivo": ("acervo.bkp", backup, "application/octet-stream")})
    enviado = r.json()
    checar("backup aceito e extraído",
           r.status_code == 200 and enviado["fase"] == "pronto", enviado)
    checar("inventário lista as 11 tabelas da amostra",
           len(enviado["tabelas"]) == 11, len(enviado.get("tabelas", [])))
    checar("cabeçalho do .dat traz a descrição da tabela",
           any(t["descricao"] == "Cadastro do Acervo"
               for t in enviado["tabelas"]))

    # §7.2 vale aqui também: nada escreve sem confirmação explícita.
    checar("gravar sem confirmação é recusado",
           c.post("/api/migracao/executar", json={}).status_code == 400)
    checar("gravar sem conferência é recusado",
           c.post("/api/migracao/executar",
                  json={"confirmado": True}).status_code == 409)

    c.post("/api/migracao/conferir", json={})
    estado = _esperar(execucao)
    checar("conferência termina sem erro",
           estado["fase"] == "conferido", estado.get("erro"))
    checar("todos os passos fecharam",
           all(p["status"] in ("ok", "pulado") for p in estado["passos"]),
           [(p["chave"], p["status"]) for p in estado["passos"]])

    rel = estado["relatorio"]
    checar("registro excluído na origem fica de fora",
           rel["acervo"]["registros_origem"] == 4, rel["acervo"])
    checar("4 exemplares viram 3 obras (cópias juntas, volumes separados)",
           rel["acervo"]["obras"] == 3 and rel["acervo"]["exemplares"] == 4)
    checar("leitor desativado entra como inativo",
           rel["leitores"]["ativos"] == 1 and rel["leitores"]["inativos"] == 1)
    checar("data de nascimento impossível é descartada",
           rel["leitores"]["nascimentos_invalidos"] == 1)
    checar("circulação casa os dois empréstimos",
           rel["circulacao"]["emprestimos"] == 2
           and rel["circulacao"]["abertos"] == 1
           and not rel["circulacao"]["descartes"], rel["circulacao"])
    checar("sem banco, a conferência avisa o que não verificou",
           rel["destino"] is None and any("Postgres" in a for a in rel["avisos"]))
    checar("arquivos de conferência em disco",
           {a["nome"] for a in estado["artefatos"]}
           >= {"obras.mrc", "exemplares.csv"}, estado["artefatos"])
    checar("download só aceita artefato conhecido",
           c.get("/api/migracao/arquivos/../estado.json").status_code in (404, 400))
    checar("download do MRC responde",
           c.get("/api/migracao/arquivos/obras.mrc").status_code == 200)

    # A gravação em si, contra o banco de mentira: é o caminho que não dá para
    # exercitar pela API sem um PostgreSQL de pé.
    pasta = Path(estado["pasta"])
    banco = BancoFalso()
    r = pipeline.gravar(pasta, pipeline.Opcoes(), banco)
    checar("grava 3 obras e 4 exemplares",
           r["obras"] == 3 and r["exemplares"] == 4, r)
    checar("uma transação só, commitada no fim",
           banco.commits == 1 and banco.rollbacks == 0)
    checar("o exemplar acha a obra pelo 035 $a",
           [a[0] for _, a in banco.holdings] == [1, 1, 2, 3],
           [a[0] for _, a in banco.holdings])
    checar("tombos no formato do BibLivre",
           [a[5] for _, a in banco.holdings][0] == "Bib.2026.1")
    checar("9 campos novos com tradução nos 3 idiomas",
           len(r["campos_criados"]) == 9 and len(banco.traducoes) == 27)
    checar("empréstimo aponta para o exemplar certo",
           banco.emprestimos[0][1] == 1 and banco.emprestimos[1][1] == 3,
           banco.emprestimos)
    checar("multa e reserva entram com o vínculo",
           len(banco.multas) == 1 and banco.reservas[0][0] == 3)
    checar("mapas de conferência escritos depois do commit",
           (pasta / "exemplares_mapa.csv").exists()
           and (pasta / "leitores_mapa.csv").exists())
    checar("reindex e restart do Tomcat aparecem como próximo passo",
           any("Reindexar" in p for p in r["proximos_passos"])
           and any("Tomcat" in p for p in r["proximos_passos"]))

    # Falha no meio: a promessa é "ou entra tudo, ou não entra nada".
    quebrado = BancoFalso()
    quebrado.escrever = _explodir
    try:
        pipeline.gravar(pasta, pipeline.Opcoes(), quebrado)
        checar("falha no meio da carga levanta", False)
    except Exception:
        checar("falha no meio da carga levanta", True)
    checar("falha desfaz a transação e não commita",
           quebrado.rollbacks == 1 and quebrado.commits == 0)

    # Gravar duas vezes a mesma etapa duplicaria um acervo inteiro. A checagem
    # de base ocupada pega isso quando há banco; esta não depende de banco
    # nenhum, e é a que vale no caminho comum (conferência sem senha).
    with execucao._lock:
        execucao._estado["gravadas"] = ["acervo"]
    repetida = c.post("/api/migracao/executar", json={"confirmado": True})
    checar("etapa já gravada não grava de novo",
           repetida.status_code == 409, repetida.json())

    checar("descartar apaga a pasta da execução",
           c.delete("/api/migracao").status_code == 200 and not pasta.exists())


def _explodir(*_args, **_kwargs):
    raise RuntimeError("banco caiu no meio da carga")


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
    verificar_migracao_pela_tela()
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
