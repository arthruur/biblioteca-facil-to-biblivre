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
     verificação "rodou uma vez em campo";
  5. o BALCÃO: sessão do operador, empréstimo (com cada impedimento do §4.3
     em um caso), aviso confirmável, devolução com multa e reserva pendente,
     renovação, e o rollback de uma falha no meio da gravação — pelo mesmo
     argumento do item 4, mais forte: aqui o erro não é "importou errado", é
     "emprestou o livro errado para a pessoa errada";
  6. a conferência da base (`verificacao.conferir`), inclusive acusando
     defeito injetado — conferência que nunca acusa nada não prova que
     acusaria;
  7. o canal HTTP com o BibLivre (`web`), contra um `http.server` local: login,
     reindex que não bloqueia, progresso e sessão expirada;
  8. e as rotas de manutenção que transformam aquilo em botão — todas pedindo
     sessão, o disparo voltando na hora, o progresso em rota separada e a
     senha do admin nunca de volta na resposta.

Usa uma pasta de dados temporária, então pode rodar com o servidor de pé.
"""

import csv
import datetime as dt
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
# BIBLIVRE_WEB_* entram na lista pelo mesmo motivo: `web._cfg` nasce do
# ambiente, e com a URL da máquina dentro dele o caso "não configurado" da
# seção do canal HTTP nasceria configurado — e sondaria a instalação de
# verdade.
for _chave in ("PGPASSWORD", "BIBLIVRE_DB_SENHA", "BIBLIVRE_WEB_URL",
               "BIBLIVRE_WEB_USUARIO", "BIBLIVRE_WEB_SENHA"):
    os.environ.pop(_chave, None)

os.environ["BIBLIO_DATA_DIR"] = tempfile.mkdtemp(prefix="biblio_teste_")
DADOS = Path(os.environ["BIBLIO_DATA_DIR"])

falhas: list[str] = []


def checar(rotulo, condicao, extra=""):
    # `flush` porque o caso de falha proposital da circulação imprime um
    # traceback no stderr (que não tem buffer): sem descarregar cada linha, a
    # saída redirecionada para arquivo mostraria o traceback no meio de outra
    # seção, e quem lê o log procuraria defeito onde não há.
    print(("  ok   " if condicao else "  FALHA") + f"  {rotulo}"
          + (f"   {extra}" if extra and not condicao else ""), flush=True)
    if not condicao:
        falhas.append(rotulo)


def secao(titulo):
    print(f"\n{titulo}", flush=True)


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
    with open(pasta / "exemplares.csv", encoding="utf-8-sig", newline="") as f:
        numacervos = [str(int(l["numacervo"])) for l in csv.DictReader(f)]
    checar("o tombo é o NUMACERVO do Biblioteca Fácil",
           [a[5] for _, a in banco.holdings] == numacervos,
           [a[5] for _, a in banco.holdings])
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

    gerado = BancoFalso()
    pipeline.gravar(pasta, pipeline.Opcoes(tombo_numacervo=False), gerado)
    checar("com o tombo gerado, volta o formato do BibLivre",
           gerado.holdings[0][1][5] == "Bib.2026.1", gerado.holdings[0][1][5])

    # Um backup depois do outro. Sem substituir, o NUMACERVO repetido bate no
    # UNIQUE do tombo antes de gravar exemplar nenhum.
    try:
        pipeline.gravar(pasta, pipeline.Opcoes(), banco)
        barrou = False
    except RuntimeError as e:
        barrou = "substituir" in str(e)
    checar("segundo backup sem substituir é barrado e desfeito",
           barrou and banco.rollbacks == 1)

    r2 = pipeline.gravar(pasta, pipeline.Opcoes(substituir=True), banco)
    checar("substituir apaga a carga anterior antes de gravar",
           r2["apagados"].get("biblio_holdings") == 4
           and r2["apagados"].get("users") == 2, r2["apagados"])
    checar("depois da recarga a base tem um backup só, não dois",
           len(banco.registros) == 3 and len(banco.holdings) == 4
           and len(banco.usuarios) == 2 and len(banco.emprestimos) == 2,
           (len(banco.registros), len(banco.holdings), len(banco.usuarios),
            len(banco.emprestimos)))
    checar("o mesmo livro mantém o mesmo tombo na recarga",
           [a[5] for _, a in banco.holdings] == numacervos)
    checar("o empréstimo recarregado aponta para o exemplar novo",
           {e[1] for e in banco.emprestimos} <= {h for h, _ in banco.holdings},
           banco.emprestimos)

    try:
        pipeline.gravar(pasta, pipeline.Opcoes(substituir=True, leitores=False),
                        BancoFalso())
        so_um_lado = False
    except RuntimeError as e:
        so_um_lado = "três etapas" in str(e)
    checar("substituir só o acervo é recusado (empréstimo aponta para leitor)",
           so_um_lado)
    rel_sem_banco = pipeline.analisar(pasta, pipeline.Opcoes(substituir=True))
    checar("substituir sem Postgres na conferência é impedimento",
           any("substituir" in i for i in rel_sem_banco["impedimentos"]),
           rel_sem_banco["impedimentos"])

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
    trocada = c.post("/api/migracao/executar",
                     json={"confirmado": True, "opcoes": {"substituir": True}})
    checar("substituir marcado depois da conferência exige conferir de novo",
           trocada.status_code == 409 and "mudou" in str(trocada.json()),
           trocada.json())

    checar("descartar apaga a pasta da execução",
           c.delete("/api/migracao").status_code == 200 and not pasta.exists())


def _explodir(*_args, **_kwargs):
    raise RuntimeError("banco caiu no meio da carga")


# ------------------------------------------------------------ CLIs

def verificar_clis():
    secao("CLIs de migração — continuam de pé")
    for nome in ("extrair_bkp", "extrair_tabela", "consolidar", "gerar_marc",
                 "inserir_obras", "inserir_exemplares", "inserir_leitores",
                 "inserir_emprestimos", "conferir", "servidor"):
        r = subprocess.run([sys.executable, f"scripts/{nome}.py", "--help"],
                           capture_output=True, text=True, cwd=RAIZ,
                           encoding="utf-8", errors="replace")
        checar(f"scripts/{nome}.py", r.returncode == 0,
               (r.stderr or r.stdout)[-400:])



# ------------------------------------------------------ Balcão de circulação
#
# Daqui para baixo é circulação: sessão do operador, empréstimo, devolução,
# renovação, conferência da base e o canal HTTP com o BibLivre. O argumento é o
# mesmo das seções de cima, mais forte: aqui o erro não é "importou errado", é
# "emprestou o livro errado para a pessoa errada", e quem descobre é o leitor
# no balcão.
#
# Tudo roda contra `banco_falso.BancoBalcao` — sem Postgres, sem rede e sem
# BibLivre instalado. O que ele NÃO prova está escrito no topo dele: o SQL em
# si só é provado contra a instalação da biblioteca.

ISBN_DOM = "9786559870530"          # o mesmo das seções de cima
SENHA_BALCAO = "segredo-do-balcao"
OPERADOR_ID = 7                     # `logins.id` do balcão, não o admin 1


def _marc_de(record_id: int, titulo: str, autor: str, isbn: str = "") -> str:
    """
    O `iso2709` da coluna `biblio_records.iso2709`, montado pelo MARC de
    verdade.

    Título e autor do balcão não saem de coluna — saem do campo 245/100 do
    MARC (não existe coluna para eles). Então o banco de mentira precisa
    guardar MARC de verdade, senão a tela mostraria título vazio e o teste não
    veria.
    """
    from biblio.biblivre import marc

    linha = dict.fromkeys(COLUNAS, "")
    linha.update(numacervo=str(record_id), titulo=titulo, autor_principal=autor,
                 editora="Globo", local_publicacao="Rio de Janeiro",
                 ano_edicao="2022", isbn=isbn, idioma="PORTUGUES",
                 paginas="480", cdd="869.3", cutter="A848d")
    return marc.carimbar(marc.montar_registro([linha]), record_id)


def _cenario():
    """
    A biblioteca de mentira: 6 obras, 12 exemplares, 8 leitores e 2 logins.

    Cada leitor existe para provocar UMA resposta do `LendingBO` — inativo,
    bloqueado, no limite, em atraso, com multa —, e cada exemplar um estado do
    acervo: livre, emprestado, marcado como indisponível.
    """
    from banco_falso import BancoBalcao

    from biblio.biblivre import operador

    banco = BancoBalcao()
    # O que o instalador semeia: "Leitor" (3 itens, 15 dias) e "Funcionário".
    # A multa por dia é 0,50 aqui de propósito — na instalação real ela é 0,00
    # e NENHUMA multa é gravada; com 0,00 o cálculo de multa nunca seria
    # exercitado, então o cenário põe valor e o teste cobre os dois casos.
    banco.tipo(1, "Leitor", limite=3, dias=15, multa_dia=0.50)
    banco.tipo(2, "Funcionário", limite=99, dias=365, multa_dia=0.0)

    banco.obra(1, "Dom Casmurro", "ASSIS, MACHADO DE",
               _marc_de(1, "Dom Casmurro", "ASSIS, MACHADO DE", ISBN_DOM))
    banco.exemplar(11, 1, "Bib.2026.1")
    banco.exemplar(12, 1, "Bib.2026.2")
    banco.exemplar(13, 1, "Bib.2026.3", disponibilidade="unavailable")

    banco.obra(2, "Sapiens", "HARARI, YUVAL NOAH",
               _marc_de(2, "Sapiens", "HARARI, YUVAL NOAH"))
    banco.exemplar(21, 2, "Bib.2026.4")
    banco.exemplar(22, 2, "Bib.2026.11")

    banco.obra(3, "O Cortiço", "AZEVEDO, ALUISIO",
               _marc_de(3, "O Cortiço", "AZEVEDO, ALUISIO"))
    banco.exemplar(31, 3, "Bib.2026.5")

    banco.obra(4, "Vidas Secas", "RAMOS, GRACILIANO",
               _marc_de(4, "Vidas Secas", "RAMOS, GRACILIANO"))
    for hid, tombo in ((41, "Bib.2026.6"), (42, "Bib.2026.7"), (43, "Bib.2026.8")):
        banco.exemplar(hid, 4, tombo)

    banco.obra(5, "Iracema", "ALENCAR, JOSE DE",
               _marc_de(5, "Iracema", "ALENCAR, JOSE DE"))
    banco.exemplar(51, 5, "Bib.2026.9")

    banco.obra(6, "Memórias Póstumas", "ASSIS, MACHADO DE",
               _marc_de(6, "Memórias Póstumas", "ASSIS, MACHADO DE"))
    banco.exemplar(61, 6, "Bib.2026.10")
    banco.exemplar(62, 6, "Bib.2026.12")

    banco.leitor(101, "Ana Paula Souza", matricula="2023-101")
    banco.leitor(102, "Bruno Inativo", status="inactive")
    banco.leitor(103, "Carla Bloqueada", status="blocked")
    banco.leitor(104, "Davi No Limite")
    banco.leitor(105, "Elza Atrasada")
    banco.leitor(106, "Fábio Funcionário", tipo=2)
    banco.leitor(107, "Gina Devedora")
    # Tipo "Funcionário", com `fine_value` 0,00 — que é o valor dos DOIS tipos
    # na instalação de verdade. É o caso que prova que atraso sem valor
    # configurado não grava multa nenhuma.
    banco.leitor(108, "Heitor Sem Multa", tipo=2)

    hoje = dt.date.today()
    banco.emprestimo(12, 101, hoje + dt.timedelta(days=5))          # id 1
    for hid in (41, 42, 43):                                        # ids 2,3,4
        banco.emprestimo(hid, 104, hoje + dt.timedelta(days=3))
    banco.emprestimo(31, 105, hoje - dt.timedelta(days=10))         # id 5 (atrasado)
    banco.emprestimo(51, 107, hoje - dt.timedelta(days=4))          # id 6 (atrasado)
    banco.emprestimo(61, 106, hoje + dt.timedelta(days=30))         # id 7
    banco.emprestimo(62, 108, hoje - dt.timedelta(days=7))          # id 8 (atrasado)
    banco.multa(107, 6, 2.0)                                        # multa em aberto

    # Reserva viva da Ana para Sapiens: é o aviso `reserva_de_outro_leitor`
    # quando outro leitor leva o exemplar 21, e a "reserva pendente" que a
    # devolução dele precisa mostrar.
    banco.reserva(2, 101, expira=dt.datetime.now() + dt.timedelta(days=3))

    banco.login("admin", operador.HASH_ADMIN_PADRAO, 1, nome="Administrador")
    banco.login("balcao", operador.hash_senha(SENHA_BALCAO), OPERADOR_ID,
                nome="Fulana do Balcão",
                permissoes=[operador.PERMISSAO_EMPRESTAR])
    return banco


def _ligar(banco):
    """
    Põe o banco de mentira no lugar de `conexao.conectar` e devolve o desfazer.

    É o único ponto de contato: os routers abrem a transação chamando
    `conexao.conectar()` (`sessao._transacao`), então trocar o atributo do
    módulo é o bastante para o balcão inteiro rodar sem Postgres.
    """
    from biblio.biblivre import conexao

    original = conexao.conectar
    conexao.conectar = lambda *_a, **_k: banco.abrir()

    def desligar():
        conexao.conectar = original
    return desligar


def _entrar(cliente, usuario="balcao", senha=SENHA_BALCAO):
    return cliente.post("/api/sessao", json={"usuario": usuario, "senha": senha})


# ------------------------------------------------------- sessão do operador


def verificar_sessao_operador():
    """
    Item 1 do pacote: quem está no balcão.

    `created_by` só vale alguma coisa se o operador for de verdade (§1.4 do
    plano), e é este 401 que garante que um celular no wi-fi da biblioteca não
    grava empréstimo.
    """
    from fastapi.testclient import TestClient

    from biblio.api.main import app
    from biblio.biblivre import operador

    secao("Balcão — sessão do operador")
    banco = _cenario()
    desligar = _ligar(banco)
    operador.esquecer_tudo()
    c = TestClient(app)
    try:
        checar("hash_senha bate com o par do instalador (admin/abracadabra)",
               operador.hash_senha(operador.SENHA_PADRAO)
               == operador.HASH_ADMIN_PADRAO)
        checar("senha em branco é recusada por hash_senha",
               _levanta(operador.hash_senha, " "))

        r = _entrar(c, senha="chute")
        checar("senha errada não abre sessão",
               r.status_code == 401 and r.json()["codigo"] == "sem_operador",
               r.json())
        checar("usuário inexistente responde igual à senha errada",
               _entrar(c, usuario="ninguem", senha="x").status_code == 401)
        checar("corpo vazio é 401 e não 500",
               c.post("/api/sessao", json={}).status_code == 401)
        checar("nenhuma sessão ficou de pé depois das recusas",
               len(operador.ativas()) == 0)

        r = _entrar(c)
        dados = r.json()
        checar("login certo abre sessão", r.status_code == 200 and dados["token"],
               dados)
        checar("a sessão traz o operador de verdade",
               dados["operador"]["id"] == OPERADOR_ID
               and dados["operador"]["login"] == "balcao", dados["operador"])
        checar("a senha não volta em lugar nenhum da resposta",
               SENHA_BALCAO not in r.text and "senha" not in dados["operador"])
        checar("login do balcão não é o do instalador (senha_padrao=False)",
               dados["senha_padrao"] is False)
        token = dados["token"]

        admin = _entrar(c, usuario="admin", senha=operador.SENHA_PADRAO).json()
        checar("admin com a senha pública do instalador vem sinalizado",
               admin["senha_padrao"] is True)

        atual = c.get("/api/sessao", headers={"X-Sessao": token}).json()
        checar("GET /api/sessao devolve quem está logado",
               atual["operador"]["id"] == OPERADOR_ID)
        checar("GET /api/sessao não repete o token", "token" not in atual)
        checar("token inventado é 401",
               c.get("/api/sessao", headers={"X-Sessao": "nao-existe"})
               .status_code == 401)

        # A garantia que sustenta o §1.4: gravação sem sessão não acontece.
        pedido = {"holding_id": 11, "user_id": 101}
        sem = c.post("/api/circulacao/emprestimos", json=pedido)
        checar("gravação sem cabeçalho X-Sessao é 401",
               sem.status_code == 401 and sem.json()["codigo"] == "sem_operador")
        com_lixo = c.post("/api/circulacao/emprestimos", json=pedido,
                          headers={"X-Sessao": "token-inventado"})
        checar("gravação com token inválido é 401", com_lixo.status_code == 401)
        checar("nenhuma das duas gravou linha em lendings",
               len(banco.emprestimos) == 8, len(banco.emprestimos))
        checar("consulta também pede sessão (a ficha é dado pessoal)",
               c.get("/api/circulacao/leitor/101").status_code == 401)

        checar("sair é 200 e idempotente",
               c.delete("/api/sessao", headers={"X-Sessao": token}).status_code == 200
               and c.delete("/api/sessao", headers={"X-Sessao": token})
               .status_code == 200)
        checar("token encerrado não serve mais",
               c.post("/api/circulacao/emprestimos", json=pedido,
                      headers={"X-Sessao": token}).status_code == 401)
    finally:
        desligar()
        operador.esquecer_tudo()


def _levanta(funcao, *args) -> bool:
    try:
        funcao(*args)
    except Exception:
        return True
    return False


# ------------------------------------- empréstimo, devolução e renovação


def verificar_circulacao():
    """
    Itens 2 a 6 e 10: o balcão inteiro, contra o banco de mentira.

    Cada impedimento tem um caso, e cada caso confere DUAS coisas: o 409 com o
    código do §4.3 e que nenhuma linha ficou em `lendings`. Barrar e gravar é
    o pior dos dois mundos — o leitor sai sem o livro e o sistema diz que ele
    levou.
    """
    from fastapi.testclient import TestClient

    from biblio.api.main import app
    from biblio.biblivre import emprestimo, operador

    secao("Balcão — empréstimo, devolução e renovação")
    banco = _cenario()
    desligar = _ligar(banco)
    operador.esquecer_tudo()
    c = TestClient(app)
    hoje = dt.date.today()
    try:
        token = _entrar(c).json()["token"]
        cab = {"X-Sessao": token}

        def emprestar(holding_id, user_id, **extra):
            return c.post("/api/circulacao/emprestimos", headers=cab,
                          json={"holding_id": holding_id, "user_id": user_id,
                                **extra})

        # --- o caminho feliz (item 2) ---
        antes = (banco.commits, len(banco.emprestimos))
        r = emprestar(11, 101)
        corpo = r.json()
        checar("empréstimo feliz é 201", r.status_code == 201, corpo)
        checar("gravou UMA linha em lendings",
               len(banco.emprestimos) == antes[1] + 1)
        linha = banco.emprestimos[-1]
        checar("created_by é o operador da sessão, não o admin 1",
               linha["criado_por"] == OPERADOR_ID, linha["criado_por"])
        checar("expected_return_date foi preenchida", linha["previsto"] is not None)
        checar("previous_lending_id é nulo num empréstimo novo",
               linha["anterior"] is None)
        checar("o id saiu da sequence (maior que os já gravados)",
               linha["id"] == 9, linha["id"])
        checar("o exemplar foi travado antes de gravar (FOR UPDATE)",
               11 in banco.travas)
        checar("a transação commitou uma vez", banco.commits == antes[0] + 1)
        emp = corpo["emprestimo"]
        checar("a resposta traz tombo, título e leitor para o recibo",
               emp["tombo"] == "Bib.2026.1" and "Dom Casmurro" in emp["titulo"]
               and emp["leitor"] == "Ana Paula Souza", emp)
        prazo = dt.date.fromisoformat(emp["previsto_para"])
        checar("prazo de 15 dias corridos, empurrado para dia de funcionamento",
               dt.timedelta(days=15) <= (prazo - hoje) <= dt.timedelta(days=21)
               and prazo.isoweekday() <= 5, emp["previsto_para"])
        renovar_id = emp["lending_id"]

        # O prazo em si, sem depender de que dia é hoje: 5/1/2026 é segunda.
        uteis = frozenset({2, 3, 4, 5, 6})          # segunda a sexta
        checar("prazo: 15 dias caindo em dia útil não se move",
               emprestimo.calcular_prazo(dt.date(2026, 1, 5), 15, uteis)
               == dt.date(2026, 1, 20))
        checar("prazo caindo no sábado vai para a segunda",
               emprestimo.calcular_prazo(dt.date(2026, 1, 5), 5, uteis)
               == dt.date(2026, 1, 12))

        # --- cada impedimento, um caso (item 3) ---
        base = len(banco.emprestimos)
        # O último campo é onde o motivo aparece: quase todos vêm DENTRO de
        # `impedimentos` (a lista que a tela traduz em frase), mas "exemplar
        # inexistente" é recusado antes da análise — o `FOR UPDATE` não achou
        # a linha —, e aí o código vem só em `codigo`, com `impedimentos`
        # vazio. Está anotado como divergência no relatório do pacote: a tela
        # que só olha `impedimentos` mostra frase genérica nesse caso.
        casos = [
            ("leitor inativo", 21, 102, "leitor_inativo", True),
            ("leitor bloqueado", 21, 103, "leitor_bloqueado", True),
            ("leitor no limite do tipo", 21, 104, "limite_atingido", True),
            ("leitor inexistente", 21, 999, "leitor_nao_encontrado", True),
            ("exemplar já emprestado", 12, 106, "exemplar_emprestado", True),
            ("exemplar marcado indisponível", 13, 106, "exemplar_indisponivel", True),
            ("exemplar inexistente", 999, 106, "exemplar_nao_encontrado", False),
        ]
        for rotulo, holding_id, user_id, codigo, na_lista in casos:
            antes_rb = banco.rollbacks
            r = emprestar(holding_id, user_id)
            dados = r.json()
            checar(f"barra: {rotulo} -> 409 {codigo}",
                   r.status_code == 409 and dados["codigo"] == codigo
                   and (codigo in dados["impedimentos"]) is na_lista, dados)
            checar(f"barra: {rotulo} não deixa linha e desfaz a transação",
                   len(banco.emprestimos) == base
                   and banco.rollbacks == antes_rb + 1)
        checar("impedimento não vem como confirmável",
               "confirmavel" not in emprestar(12, 106).json())
        checar("nem forcar_avisos passa por cima de impedimento",
               emprestar(12, 106, forcar_avisos=True).status_code == 409)
        checar("os códigos usados são só os do §4.3",
               {caso[3] for caso in casos} <= set(emprestimo.IMPEDIMENTOS))

        # --- aviso: barra sem a flag, passa com ela (item 4) ---
        r = emprestar(21, 105)
        dados = r.json()
        checar("leitor em atraso é AVISO: 409 confirmável, sem impedimento",
               r.status_code == 409 and dados["impedimentos"] == []
               and dados.get("confirmavel") is True, dados)
        checar("o aviso chega como código, com a frase pronta ao lado",
               "leitor_com_atraso" in dados["avisos"]
               and any(a["codigo"] == "leitor_com_atraso"
                       for a in dados["avisos_detalhe"]), dados["avisos"])
        checar("reserva de outro leitor também é aviso, nunca impedimento",
               "reserva_de_outro_leitor" in dados["avisos"], dados["avisos"])
        checar("o aviso não gravou nada", len(banco.emprestimos) == base)
        r = emprestar(21, 105, forcar_avisos=True)
        checar("com forcar_avisos o mesmo empréstimo passa (201)",
               r.status_code == 201, r.json())
        checar("e agora a linha existe", len(banco.emprestimos) == base + 1)
        checar("a reserva da Ana continua de pé (era de outro leitor)",
               any(res["user_id"] == 101 and res["record_id"] == 2
                   for res in banco.reservas))
        devolver_21 = r.json()["emprestimo"]["lending_id"]
        multa_aviso = emprestar(22, 107).json()
        checar("multa em aberto é aviso, não impedimento",
               "multa_em_aberto" in multa_aviso.get("avisos", []), multa_aviso)

        # --- devolução, multa e reserva pendente (item 5) ---
        r = c.post("/api/circulacao/devolucoes", headers=cab,
                   json={"holding_id": 31})
        dados = r.json()
        checar("devolução do atrasado é 200", r.status_code == 200, dados)
        checar("fechou o empréstimo (return_date preenchido)",
               banco.por_id(5)["devolvido"] is not None)
        checar("atraso em dias corridos", dados["atraso_dias"] == 10,
               dados["atraso_dias"])
        checar("multa = dias × fine_value do tipo (10 × 0,50)",
               dados["multa"] and dados["multa"]["valor"] == 5.0, dados["multa"])
        gravada = [m for m in banco.multas if m["lending_id"] == 5]
        checar("a multa entrou em lending_fines, em aberto e no nome do operador",
               len(gravada) == 1 and gravada[0]["pago_em"] is None
               and gravada[0]["criado_por"] == OPERADOR_ID, gravada)

        multas_antes = len(banco.multas)
        r = c.post("/api/circulacao/devolucoes", headers=cab,
                   json={"holding_id": 31})
        checar("devolver duas vezes o mesmo exemplar é 409 conflito",
               r.status_code == 409 and r.json()["codigo"] == "conflito",
               r.json())
        checar("a segunda devolução não gera segunda multa",
               len(banco.multas) == multas_antes)

        multas_antes = len(banco.multas)
        r = c.post("/api/circulacao/devolucoes", headers=cab,
                   json={"holding_id": 62})
        dados = r.json()
        checar("atrasado com fine_value 0,00 (o caso da instalação real): "
               "conta o atraso e NÃO grava multa",
               r.status_code == 200 and dados["atraso_dias"] == 7
               and dados["multa"] is None
               and len(banco.multas) == multas_antes, dados.get("multa"))

        r = c.post("/api/circulacao/devolucoes", headers=cab,
                   json={"lending_id": devolver_21})
        dados = r.json()
        checar("devolução em dia: sem atraso e sem multa",
               r.status_code == 200 and dados["atraso_dias"] == 0
               and dados["multa"] is None, dados)
        checar("a devolução avisa da reserva pendente da obra",
               dados["reserva"] and dados["reserva"]["user_id"] == 101,
               dados["reserva"])
        checar("devolução sem exemplar e sem empréstimo é 400, não 500",
               c.post("/api/circulacao/devolucoes", headers=cab, json={})
               .status_code == 400)

        # Multa que o banco recusa: `devolver` grava a multa dentro de
        # SAVEPOINT (`_tentar`), então uma base que não aceita a linha —
        # `lending_fines` ausente, GRANT que falta — fecha a devolução do mesmo
        # jeito e marca `gravada: False`. É deliberado (segurar o livro do
        # leitor porque a multa não pôde ser escrita seria pior), e é o único
        # caso do balcão que exercita o rollback PARCIAL. Que nenhuma tela
        # mostre esse `gravada` está no relatório do pacote.
        atrasado_extra = banco.emprestimo(22, 105, hoje - dt.timedelta(days=6))
        multas_antes, commits_antes = len(banco.multas), banco.commits
        banco.explodir_em = "INSERT INTO lending_fines"
        r = c.post("/api/circulacao/devolucoes", headers=cab,
                   json={"lending_id": atrasado_extra})
        banco.explodir_em = ""
        dados = r.json()
        checar("multa recusada pelo banco não cancela a devolução (SAVEPOINT)",
               r.status_code == 200 and banco.commits == commits_antes + 1
               and banco.por_id(atrasado_extra)["devolvido"] is not None, dados)
        checar("e a resposta diz que a multa NÃO foi gravada",
               dados["multa"]["gravada"] is False
               and dados["multa"]["valor"] == 3.0
               and len(banco.multas) == multas_antes, dados["multa"])

        # --- renovação (item 6) ---
        r = c.post("/api/circulacao/renovacoes", headers=cab,
                   json={"lending_id": renovar_id})
        dados = r.json()
        checar("renovação é 200", r.status_code == 200, dados)
        novo = dados["emprestimo"]
        checar("renovar fecha a linha antiga",
               banco.por_id(renovar_id)["devolvido"] is not None)
        checar("renovar abre linha NOVA com previous_lending_id",
               novo["lending_id"] != renovar_id
               and banco.por_id(novo["lending_id"])["anterior"] == renovar_id)
        checar("o prazo novo é contado de hoje",
               dt.date.fromisoformat(novo["previsto_para"]) > hoje)
        checar("renovar de novo o empréstimo já fechado é 409",
               c.post("/api/circulacao/renovacoes", headers=cab,
                      json={"lending_id": renovar_id}).status_code == 409)

        multas_antes = len(banco.multas)
        r = c.post("/api/circulacao/renovacoes", headers=cab,
                   json={"lending_id": 6})
        dados = r.json()
        checar("renovação de atrasado passa e informa o atraso",
               r.status_code == 200 and dados["atraso_dias"] == 4, dados)
        checar("renovação atrasada NÃO gera multa (quirk do doRenew)",
               len(banco.multas) == multas_antes)
        checar("mas o atraso volta como aviso, para o balcão ver o que perdoou",
               "leitor_com_atraso" in dados["avisos"], dados["avisos"])

        # --- consulta ---
        ficha = c.get("/api/circulacao/leitor/101", headers=cab).json()
        checar("ficha traz leitor, situação e empréstimos",
               ficha["leitor"]["nome"] == "Ana Paula Souza"
               and ficha["situacao"]["limite"] == 3
               and isinstance(ficha["emprestimos"], list), ficha.get("leitor"))
        checar("a matrícula é o id com zeros à esquerda",
               ficha["leitor"]["matricula"] == "00101")
        checar("leitor inexistente é 404 na consulta",
               c.get("/api/circulacao/leitor/999", headers=cab).status_code == 404)
        checar("exemplar inexistente é 404 na consulta",
               c.get("/api/circulacao/exemplar/999", headers=cab)
               .status_code == 404)
        achados = c.get("/api/circulacao/leitores?busca=fabio", headers=cab).json()
        checar("busca de leitor ignora acento (Fábio por 'fabio')",
               achados["total"] == 1
               and achados["leitores"][0]["id"] == 106, achados)
        checar("busca não devolve leitor inativo",
               c.get("/api/circulacao/leitores?busca=bruno", headers=cab)
               .json()["total"] == 0)
        pend = c.get("/api/circulacao/pendencias?tipo=atrasados",
                     headers=cab).json()
        checar("pendências listam só o que está vencido",
               all(i["atraso_dias"] > 0 for i in pend["itens"])
               and pend["total"] == len(pend["itens"]), pend.get("total"))
        checar("tipo de pendência inválido é 409, não 500",
               c.get("/api/circulacao/pendencias?tipo=xpto", headers=cab)
               .status_code == 409)

        # --- ROLLBACK: falha no meio não deixa meia operação (item 10) ---
        # A renovação é o caso de verdade: ela FECHA o empréstimo antigo e só
        # depois abre o novo. Se a segunda metade falhar e a transação não
        # desfizer, o livro fica devolvido sem estar devolvido.
        aberto = banco.aberto_do_exemplar(61)
        commits_antes, rollbacks_antes = banco.commits, banco.rollbacks
        linhas_antes = len(banco.emprestimos)
        banco.explodir_em = "INSERT INTO lendings"
        print("  ...   (o traceback a seguir é do caso de falha proposital)",
              flush=True)
        r = c.post("/api/circulacao/renovacoes", headers=cab,
                   json={"lending_id": aberto["id"]})
        banco.explodir_em = ""
        checar("falha no meio da renovação vira 500 legível, sem stack",
               r.status_code == 500 and "Traceback" not in r.text
               and r.json()["codigo"] == "falha_inesperada", r.text[:200])
        checar("a transação foi desfeita e nada commitou",
               banco.rollbacks == rollbacks_antes + 1
               and banco.commits == commits_antes)
        checar("o empréstimo antigo continua ABERTO (o fechamento voltou atrás)",
               banco.por_id(aberto["id"])["devolvido"] is None)
        checar("e nenhuma linha nova ficou pela metade",
               len(banco.emprestimos) == linhas_antes)
        r = c.post("/api/circulacao/renovacoes", headers=cab,
                   json={"lending_id": aberto["id"]})
        checar("com o banco de pé de novo, a mesma renovação funciona",
               r.status_code == 200, r.json())
    finally:
        desligar()
        operador.esquecer_tudo()


# ---------------------------------------------- resolver o que foi bipado


def verificar_resolver():
    """
    Item 7: o bipe cru. Tombo, ISBN (que devolve a lista de exemplares) e
    código que não é nada.

    O caminho do ISBN é o que faz o acervo migrado funcionar no balcão: os
    16.251 tombos existem no banco, nem todos no papel, então bipar o código de
    barras da CAPA tem de devolver os exemplares daquela obra com o estado de
    cada um, para o operador escolher.
    """
    from fastapi.testclient import TestClient

    from biblio.api.main import app
    from biblio.biblivre import acervo, operador

    secao("Balcão — resolver tombo, ISBN e leitor")
    banco = _cenario()
    # Um tombo de acervo migrado (o NUMACERVO, só dígitos) que é também o
    # número de uma leitora — a ambiguidade que o `preferir` resolve.
    banco.exemplar(52, 5, "105")
    desligar = _ligar(banco)
    operador.esquecer_tudo()
    c = TestClient(app)
    try:
        cab = {"X-Sessao": _entrar(c).json()["token"]}

        def resolver(codigo):
            return c.get("/api/circulacao/resolver", headers=cab,
                         params={"codigo": codigo}).json()

        r = resolver("Bib.2026.1")
        checar("tombo cai em tipo=tombo, com o exemplar montado",
               r["tipo"] == "tombo" and r["exemplar"]["holding_id"] == 11
               and "Dom Casmurro" in r["obra"]["titulo"], r.get("tipo"))
        r = resolver("Bib.2026.2")
        checar("tombo emprestado já vem com o empréstimo em aberto",
               r["exemplar"]["emprestado"] is True
               and r["emprestimo"]["leitor"] == "Ana Paula Souza",
               r.get("emprestimo"))

        r = resolver(ISBN_DOM)
        checar("ISBN cai em tipo=isbn e lista os exemplares da obra",
               r["tipo"] == "isbn" and len(r["exemplares"]) == 3, r.get("tipo"))
        checar("a lista diz qual está na estante e qual saiu",
               [e["disponivel"] for e in r["exemplares"]] == [True, False, False],
               [(e["tombo"], e["disponivel"]) for e in r["exemplares"]])
        dez = [v for v in acervo.variantes(ISBN_DOM) if len(v) == 10]
        if dez:
            checar("ISBN-10 da capa antiga casa com o ISBN-13 gravado",
                   resolver(dez[0])["tipo"] == "isbn")

        checar("id de leitor cai em tipo=leitor",
               resolver("101")["leitor"]["id"] == 101)
        checar("matrícula com zeros à esquerda cai no mesmo leitor",
               resolver("00101")["leitor"]["id"] == 101)
        checar("matrícula impressa (users_values) também resolve",
               resolver("2023-101")["leitor"]["id"] == 101)

        # O tombo migrado é o NUMACERVO: "105" é o exemplar 52 E a leitora 105.
        def resolver_como(codigo, preferir):
            return c.get("/api/circulacao/resolver", headers=cab,
                         params={"codigo": codigo, "preferir": preferir}).json()

        r = resolver("105")
        checar("tombo que também é nº de leitor vem como tombo, com o aviso",
               r["tipo"] == "tombo" and r["exemplar"]["holding_id"] == 52
               and r.get("tambem_leitor", {}).get("user_id") == 105, r)
        r = resolver_como("105", "leitor")
        checar("esperando a carteirinha, o mesmo número é o leitor",
               r["tipo"] == "leitor" and r["leitor"]["id"] == 105, r.get("tipo"))
        r = resolver_como("105", "exemplar")
        checar("esperando o livro, é o exemplar, sem perguntar do leitor",
               r["tipo"] == "tombo" and "tambem_leitor" not in r, r.get("tipo"))
        checar("preferir inventado é 400",
               c.get("/api/circulacao/resolver", headers=cab,
                     params={"codigo": "105", "preferir": "x"}).status_code == 400)
        checar("preferir leitor não atrapalha o tombo que não é leitor",
               resolver_como("Bib.2026.1", "leitor")["tipo"] == "tombo")

        # Busca de obra por título: o livro sem etiqueta e sem ISBN.
        def obras(busca):
            return c.get("/api/circulacao/obras", headers=cab,
                         params={"busca": busca}).json()["obras"]

        achadas = obras("casmurro")
        checar("título acha a obra com os exemplares e o estado",
               len(achadas) == 1 and achadas[0]["record_id"] == 1
               and achadas[0]["total"] == 3 and achadas[0]["disponiveis"] == 1,
               achadas)
        checar("busca por título ignora acento (memorias → Memórias)",
               [o["record_id"] for o in obras("memorias postumas")] == [6])
        checar("o autor também serve de busca",
               {o["record_id"] for o in obras("machado")} == {1, 6})
        checar("palavras em qualquer ordem",
               [o["record_id"] for o in obras("secas vidas")] == [4])
        checar("título que não existe é lista vazia",
               obras("xilogravura") == [])
        checar("busca vazia é lista vazia, não erro", obras("") == [])

        r = resolver("999999999")
        checar("código que não é nada volta 200 com tipo=desconhecido",
               r["tipo"] == "desconhecido" and r["mensagem"], r)
        checar("bipe vazio não é erro HTTP",
               resolver("")["tipo"] == "desconhecido")
    finally:
        desligar()
        operador.esquecer_tudo()


# ----------------------------------------------- conferência da base (A2)


def verificar_conferencia():
    """
    Item 8: `verificacao.conferir` contra o banco de mentira.

    Duas coisas importam aqui: o formato do contrato (§4.1) e o fato de que
    checagem que não pôde rodar volta `ok: None` sem derrubar as outras — é o
    que faz a conferência ser útil numa instalação com tabela faltando.
    Depois, três defeitos injetados, porque conferência que nunca acusa nada
    não prova que acusaria.
    """
    from fastapi.testclient import TestClient

    from biblio.api.main import app
    from biblio.biblivre import operador, verificacao

    secao("Conferência da base — o relatório do pós-carga")
    banco = _cenario()
    desligar = _ligar(banco)
    operador.esquecer_tudo()
    c = TestClient(app)
    try:
        cab = {"X-Sessao": _entrar(c).json()["token"]}
        gravacoes_antes = banco.gravacoes
        r = c.post("/api/manutencao/conferencia", headers=cab)
        rel = r.json()
        checar("POST /api/manutencao/conferencia responde 200",
               r.status_code == 200, rel)
        checagens = rel.get("checagens") or []
        chaves = {"chave", "rotulo", "ok", "valor", "esperado", "detalhe"}
        checar("toda checagem tem as seis chaves do contrato",
               checagens and all(chaves <= set(ch) for ch in checagens),
               len(checagens))
        resumo = rel["resumo"]
        checar("o resumo soma o que a lista tem",
               resumo["total"] == len(checagens)
               and resumo["ok"] + resumo["falhas"] + resumo["nao_verificadas"]
               == resumo["total"], resumo)
        checar("a conferência exige sessão como o resto da manutenção",
               c.post("/api/manutencao/conferencia").status_code == 401)

        por_chave = {ch["chave"]: ch for ch in checagens}
        checar("a checagem do índice (a que responde 'o reindex pegou?') existe",
               "indice_reindex" in por_chave)
        checar("base de mentira sadia não acusa falha",
               resumo["falhas"] == 0,
               [ch["chave"] for ch in checagens if ch["ok"] is False])
        checar("as sequences das quatro tabelas são conferidas",
               {"sequence_lendings", "sequence_users", "sequence_biblio_records",
                "sequence_biblio_holdings"} <= set(por_chave))
        checar("contagem informativa não tem esperado e nunca falha",
               por_chave["total_obras"]["esperado"] is None
               and por_chave["total_obras"]["ok"] is True)
        checar("o prefixo de tombo em vigor é lido de configurations",
               por_chave["prefixo_tombo"]["valor"] == "Bib",
               por_chave["prefixo_tombo"])

        # Checagem que não pôde rodar: `ok=None` com o motivo, e as outras
        # seguem. É o comportamento que vale na instalação com tabela ausente
        # ou sem GRANT — e é o que impede uma conferência de 24 perguntas de
        # morrer por causa da primeira.
        banco.cego_em = "FROM lending_fines f"
        cego = {ch["chave"]: ch for ch in
                verificacao.conferir(banco.abrir())["checagens"]}
        banco.cego_em = ""
        checar("checagem que não pôde rodar volta ok=None com o motivo",
               cego["multas_sem_emprestimo"]["ok"] is None
               and cego["multas_sem_emprestimo"]["detalhe"],
               cego["multas_sem_emprestimo"])
        checar("e não derruba as outras 23",
               cego["indice_reindex"]["ok"] is True
               and cego["total_obras"]["ok"] is True)

        # Três defeitos de verdade, um de cada família.
        banco.indice.discard(3)                       # obra fora do índice
        banco.exemplar(99, 777, "Bib.2026.1")         # órfã + tombo repetido
        banco.sequencias["lendings_id_seq"] = (1, False)   # a armadilha do §A2
        rel = verificacao.conferir(banco.abrir())
        por_chave = {ch["chave"]: ch for ch in rel["checagens"]}
        checar("acusa a obra que ficou fora de biblio_idx_fields",
               por_chave["indice_reindex"]["ok"] is False
               and "3" in por_chave["indice_reindex"]["detalhe"],
               por_chave["indice_reindex"])
        checar("acusa o exemplar órfão, com amostra no detalhe",
               por_chave["exemplares_orfaos"]["ok"] is False
               and "Bib.2026.1" in por_chave["exemplares_orfaos"]["detalhe"],
               por_chave["exemplares_orfaos"])
        checar("acusa o tombo duplicado",
               por_chave["tombos_duplicados"]["ok"] is False)
        checar("acusa a sequence atrás do max(id) e diz como corrigir",
               por_chave["sequence_lendings"]["ok"] is False
               and "setval" in por_chave["sequence_lendings"]["detalhe"],
               por_chave["sequence_lendings"])
        checar("o resumo conta as falhas", rel["resumo"]["falhas"] >= 4,
               rel["resumo"])
        checar("conferência não escreve nada: nenhum INSERT/UPDATE/DELETE",
               banco.gravacoes == gravacoes_antes, banco.gravacoes)
    finally:
        desligar()
        operador.esquecer_tudo()


# ------------------------------------- canal HTTP com o BibLivre instalado


def _biblivre_de_mentira():
    """
    Um `http.server` local que imita o `JsonController` do BibLivre 5.

    O bastante para os quatro caminhos que importam: login (aceito e
    recusado), o `reindex` que demora, o `progress` que a barra consulta e o
    `error.no_permission` que é a assinatura de sessão perdida no Tomcat.
    """
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    estado = {"sessoes": set(), "logins": 0, "reindexes": 0, "n": 0,
              "expirar": False, "demora": 0.6, "indexados": 0, "total": 100,
              # O backup do BibLivre sao duas acoes: `prepare`, que devolve o
              # id na hora, e `backup`, que roda o `pg_dump` e so responde no
              # fim. A demora aqui e o que prova que o disparo nao espera.
              "backups": 0, "backup_n": 0, "backup_atual": 0,
              "backup_total": 40, "demora_backup": 0.3}
    trava = threading.Lock()

    class Mao(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_a):
            pass

        def _json(self, dados, extra=()):
            corpo = json.dumps(dados).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json;charset=UTF-8")
            self.send_header("Content-Length", str(len(corpo)))
            for chave, valor in extra:
                self.send_header(chave, valor)
            self.end_headers()
            self.wfile.write(corpo)

        def _logado(self):
            for parte in (self.headers.get("Cookie") or "").split(";"):
                nome, _, valor = parte.strip().partition("=")
                if nome == "JSESSIONID":
                    with trava:
                        if estado["expirar"]:
                            estado["expirar"] = False
                            estado["sessoes"].discard(valor)
                            return False
                        return valor in estado["sessoes"]
            return False

        def do_POST(self):
            consulta = parse_qs(urlparse(self.path).query)
            tamanho = int(self.headers.get("Content-Length") or 0)
            bruto = self.rfile.read(tamanho).decode("utf-8") if tamanho else ""
            corpo = parse_qs(bruto)
            modulo = (consulta.get("module") or [""])[0]
            acao = (consulta.get("action") or [""])[0]

            if modulo == "login":
                with trava:
                    estado["logins"] += 1
                if ((corpo.get("username") or [""])[0] != "admin"
                        or (corpo.get("password") or [""])[0] != "senha-certa"):
                    return self._json({"success": False,
                                       "message": "Acesso negado",
                                       "message_level": "warning"})
                with trava:
                    estado["n"] += 1
                    sid = f"SESSAO{estado['n']}"
                    estado["sessoes"].add(sid)
                return self._json({"success": True, "message": "login.success"},
                                  extra=[("Set-Cookie", f"JSESSIONID={sid}; Path=/")])

            if not self._logado():
                # `JsonController.doAuthorizationError`
                return self._json({"success": False,
                                   "message": "Você não tem permissão",
                                   "message_level": "warning"})

            if modulo == "administration.indexing" and acao == "reindex":
                with trava:
                    estado["reindexes"] += 1
                    demora = estado["demora"]
                time.sleep(demora)          # o reindex real leva minutos
                with trava:
                    estado["indexados"] = estado["total"]
                return self._json({"success": True})
            if modulo == "administration.indexing" and acao == "progress":
                with trava:
                    return self._json({"success": True,
                                       "current": estado["indexados"],
                                       "total": estado["total"]})
            if modulo == "administration.translations" and acao == "list":
                return self._json({"success": True, "translations": {}})

            if modulo == "administration.backup" and acao == "prepare":
                with trava:
                    estado["backup_n"] += 1
                    ident = str(estado["backup_n"])
                    estado["backup_atual"] = 0
                return self._json({"success": True, "id": ident,
                                   "total": estado["backup_total"]})
            if modulo == "administration.backup" and acao == "backup":
                with trava:
                    estado["backups"] += 1
                    demora = estado["demora_backup"]
                time.sleep(demora)          # o pg_dump real leva minutos
                with trava:
                    estado["backup_atual"] = estado["backup_total"]
                return self._json({"success": True})
            if modulo == "administration.backup" and acao == "progress":
                with trava:
                    return self._json({"success": True,
                                       "current": estado["backup_atual"],
                                       "total": estado["backup_total"]})

            return self._json({"success": False, "message": "error.void"})

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Mao)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}/Biblivre5/"
    return servidor, url, estado, trava


def verificar_canal_http():
    """
    Item 9: `biblio.biblivre.web` contra o BibLivre de mentira.

    É o único módulo do pacote que fala HTTP em vez de SQL, e o que ele existe
    para respeitar é uma regra de tempo: `reindexar()` NÃO pode bloquear, senão
    a tela fica pendurada os minutos que o Tomcat leva para varrer 14 mil
    registros. Por isso o servidor de mentira demora de propósito.

    `tests/teste_web_biblivre.py` (do pacote A1) cobre o mesmo módulo com mais
    fundo — HTML no lugar de JSON, backup, timeout. Aqui fica o mínimo que não
    pode regredir sem alguém notar na hora.
    """
    from biblio.biblivre import web

    secao("Canal HTTP com o BibLivre — sem sair da máquina")
    servidor, url, estado, trava = _biblivre_de_mentira()
    try:
        checar("sem configuração, `estado()` diz o que falta e não sonda",
               web.estado()["configurado"] is False
               and "não configurado" in web.estado()["erro"], web.estado())
        checar("URL sem http:// é recusada na hora",
               web.configurar("localhost:8080", "admin", "x")["configurado"]
               is False)

        e = web.configurar(url, "admin", "senha-errada")
        checar("senha errada: configurado sim, conectado não",
               e["configurado"] is True and e["conectado"] is False and e["erro"],
               e)
        checar("a senha do admin não sai em `estado()`",
               "senha" not in web.estado()
               and "senha-errada" not in str(web.estado()))
        checar("login recusado devolve dict com erro, não exceção",
               web.entrar()["ok"] is False)

        e = web.configurar(url, "admin", "senha-certa")
        checar("login certo: conectado", e["conectado"] is True, e)
        checar("`entrar()` reaproveitável", web.entrar()["ok"] is True)

        marca = time.time()
        r = web.reindexar()
        gasto = time.time() - marca
        checar("reindexar() dispara e volta na hora (não bloqueia)",
               r["ok"] is True and gasto < 0.4, f"{gasto:.2f}s")
        checar("segunda reindexação simultânea é recusada com motivo",
               web.reindexar()["ok"] is False)
        p = web.progresso_reindex()
        checar("progresso responde durante a reindexação",
               p["rodando"] is True and p["total"] == 100, p)

        limite = time.time() + 5
        while web.progresso_reindex()["rodando"] and time.time() < limite:
            time.sleep(0.05)
        p = web.progresso_reindex()
        checar("a reindexação termina e o progresso fecha em 100%",
               p["rodando"] is False and p["pct"] == 100 and not p["erro"], p)
        with trava:
            checar("o BibLivre de mentira recebeu UMA reindexação",
                   estado["reindexes"] == 1, estado["reindexes"])
            logins_antes = estado["logins"]

        # Sessão perdida no Tomcat: a próxima chamada reloga sozinha e repete.
        with trava:
            estado["expirar"] = True
        p = web.progresso_reindex()
        with trava:
            relogou = estado["logins"] == logins_antes + 1
        checar("sessão expirada: reloga uma vez e a chamada dá certo",
               not p["erro"] and relogou, p.get("erro"))

        checar("resetar_caches derruba tradução e avisa do que não dá por HTTP",
               web.resetar_caches().get("ok") is True)

        # `server_close` junto com o `shutdown`: sem fechar o socket que
        # escuta, a conexão ficaria na fila do sistema e o teste esperaria o
        # timeout inteiro em vez de levar "conexão recusada" na hora.
        servidor.shutdown()
        servidor.server_close()
        e = web.configurar(url, "admin", "senha-certa")   # invalida a sonda
        checar("BibLivre fora do ar vira erro legível, não exceção crua",
               e["conectado"] is False and e["erro"], e)
    finally:
        try:
            servidor.shutdown()
            servidor.server_close()
        except Exception:
            pass


# --------------------------------- manutenção pela API (os três botões)


def verificar_manutencao_api():
    """
    A outra metade do item 9: as rotas que transformam passo manual em botão.

    A seção de cima prova que o pacote `web` fala com o Tomcat. Esta prova o
    que só existe no router, e que nenhuma tela cobre ainda:

      * TODA rota de manutenção pede sessão — inclusive as de consulta. Um
        `POST /backup` produz um `.b5bz` com nome, CPF e endereço de todos os
        leitores, com URL de download; deixar isso aberto no wi-fi da
        biblioteca seria pior que qualquer incômodo de ter de entrar antes;
      * o disparo volta na hora e o progresso é rota separada (o reindex de 14
        mil registros leva minutos; requisição pendurada é tela travada);
      * a senha do admin do BibLivre não volta na resposta, como a do Postgres;
      * perder um polling não vira 409: o progresso responde 200 mesmo com o
        Tomcat fora do ar, senão a barra sumiria no primeiro soluço da rede.
    """
    from fastapi.testclient import TestClient

    from biblio.api.main import app
    from biblio.biblivre import operador, web

    secao("Manutenção pela API — reindexar, caches e backup")
    banco = _cenario()
    desligar = _ligar(banco)
    operador.esquecer_tudo()
    c = TestClient(app)
    servidor, url, estado, trava = _biblivre_de_mentira()

    # URL e credencial do BibLivre vivem em memória de processo, e a seção de
    # cima deixou lá a instalação de mentira dela. Volta ao estado de máquina
    # recém-ligada — é o único jeito de o caso "nada configurado" ser de
    # verdade — e devolve no fim. Mexer no `_cfg` privado é deliberado: não
    # existe (nem deveria existir) rota que esqueça a credencial.
    config_antes = dict(web._cfg)
    web._cfg.update(url="", senha="")
    web._invalidar_sonda()
    try:
        # --- nenhuma rota de manutenção fica aberta ---
        gets = ["/api/manutencao", "/api/manutencao/reindexar",
                "/api/manutencao/backup"]
        posts = ["/api/manutencao/reindexar", "/api/manutencao/caches",
                 "/api/manutencao/conferencia", "/api/manutencao/backup"]
        fechadas = ([c.get(r).status_code for r in gets]
                    + [c.post(r).status_code for r in posts]
                    + [c.post("/api/manutencao/biblivre",
                              json={"url": url, "usuario": "admin",
                                    "senha": "senha-certa"}).status_code])
        checar("as 8 rotas de manutenção pedem sessão (nenhuma aberta na LAN)",
               fechadas == [401] * 8, fechadas)
        checar("a tentativa sem sessão não guardou a credencial",
               web.estado()["configurado"] is False)

        cab = {"X-Sessao": _entrar(c).json()["token"]}

        # --- instalação sem BibLivre configurado ---
        r = c.get("/api/manutencao", headers=cab)
        p = r.json()
        biblivre = p.get("biblivre") or {}
        checar("sem BibLivre configurado o panorama responde 200 e diz o que falta",
               r.status_code == 200 and set(p) == {"biblivre", "reindex", "backup"}
               and biblivre.get("configurado") is False
               and biblivre.get("erro"), p.get("biblivre"))
        recusas = {}
        for rota in ("/api/manutencao/reindexar", "/api/manutencao/caches",
                     "/api/manutencao/backup"):
            resp = c.post(rota, headers=cab)
            recusas[rota] = (resp.status_code, resp.json().get("codigo"))
        checar("sem configuração, os três botões são biblivre_nao_configurado",
               set(recusas.values()) == {(409, "biblivre_nao_configurado")},
               recusas)
        checar("o progresso responde 200 mesmo sem configuração nenhuma",
               c.get("/api/manutencao/reindexar", headers=cab).status_code == 200
               and c.get("/api/manutencao/backup", headers=cab).status_code == 200)
        with trava:
            checar("recusa por falta de configuração não abre socket",
                   estado["logins"] == 0, estado["logins"])

        # --- configurar a instalação (de mentira) ---
        r = c.post("/api/manutencao/biblivre", headers=cab,
                   json={"url": url, "usuario": "admin", "senha": "senha-certa"})
        dados = r.json()
        checar("POST /biblivre guarda a credencial e sonda na hora",
               r.status_code == 200 and dados.get("configurado") is True
               and dados.get("conectado") is True, dados)
        checar("a senha do admin não volta na resposta nem no panorama",
               "senha-certa" not in r.text
               and "senha-certa" not in c.get("/api/manutencao", headers=cab).text)

        # --- reindexar: dispara e volta na hora ---
        marca = time.time()
        r = c.post("/api/manutencao/reindexar", headers=cab)
        gasto = time.time() - marca
        checar("POST /reindexar dispara e volta na hora (não pendura a tela)",
               r.status_code == 200 and r.json().get("iniciado") is True
               and gasto < 0.4, f"{gasto:.2f}s {r.json()}")
        # Segunda chamada simultânea: o BibLivre tem lock por tipo de registro
        # e responderia sucesso calado, sem indexar nada. O 409 é o certo; o
        # CÓDIGO que ele traz é `biblivre_indisponivel`, que quer dizer "o
        # Tomcat não respondeu" e não "já está rodando" — está no relatório do
        # pacote como divergência, e é decisão do router, não daqui.
        segunda = c.post("/api/manutencao/reindexar", headers=cab)
        checar("segunda reindexação simultânea é 409, não sucesso calado",
               segunda.status_code == 409 and segunda.json().get("mensagem"),
               segunda.json())
        p = c.get("/api/manutencao/reindexar", headers=cab).json()
        checar("o progresso é rota separada e responde durante a varredura",
               p.get("rodando") is True and p.get("total") == 100, p)
        limite = time.time() + 5
        while (c.get("/api/manutencao/reindexar", headers=cab).json().get("rodando")
               and time.time() < limite):
            time.sleep(0.05)
        p = c.get("/api/manutencao/reindexar", headers=cab).json()
        checar("a reindexação fecha em 100% e sem erro",
               p.get("rodando") is False and p.get("pct") == 100
               and not p.get("erro"), p)
        with trava:
            checar("o BibLivre de mentira recebeu UMA reindexação pela API",
                   estado["reindexes"] == 1, estado["reindexes"])

        # --- caches: o que dá por HTTP, e o que não dá ---
        r = c.post("/api/manutencao/caches", headers=cab)
        dados = r.json()
        checar("POST /caches derruba a tradução e responde 200",
               r.status_code == 200 and dados.get("ok") is True
               and dados.get("traducoes") is True, dados)
        checar("e avisa que campo de leitor ainda exige restart do Tomcat",
               dados.get("campos_de_leitor") is False
               and "restart" in (dados.get("detalhe") or ""), dados.get("detalhe"))

        # --- backup: o .b5bz saindo do próprio BibLivre ---
        r = c.post("/api/manutencao/backup", headers=cab, json={"tipo": "full"})
        dados = r.json()
        checar("POST /backup dispara o .b5bz e devolve o id, sem esperar o pg_dump",
               r.status_code == 200 and dados.get("iniciado") is True
               and dados.get("id"), dados)
        b = c.get("/api/manutencao/backup", headers=cab).json()
        checar("GET /backup traz o andamento e a URL de download do .b5bz",
               b.get("rodando") is True
               and "controller=download" in (b.get("url_download") or ""), b)
        limite = time.time() + 5
        while (c.get("/api/manutencao/backup", headers=cab).json().get("rodando")
               and time.time() < limite):
            time.sleep(0.05)
        b = c.get("/api/manutencao/backup", headers=cab).json()
        checar("o backup termina, fecha em 100% e sem erro",
               b.get("rodando") is False and b.get("pct") == 100
               and not b.get("erro"), b)
        with trava:
            checar("o BibLivre de mentira gerou UM backup",
                   estado["backups"] == 1, estado["backups"])
        r = c.post("/api/manutencao/backup", headers=cab, json={"tipo": "xpto"})
        with trava:
            gerados = estado["backups"]
        checar("tipo de backup inventado é 409 e nem chega a chamar o Tomcat",
               r.status_code == 409 and gerados == 1, r.json())

        # --- Tomcat fora do ar ---
        # `server_close` junto com o `shutdown` pelo mesmo motivo da seção de
        # cima: sem fechar o socket que escuta, a chamada esperaria o timeout
        # inteiro em vez de levar "conexão recusada".
        #
        # Daqui para baixo cada chamada que sai custa DOIS SEGUNDOS de relógio:
        # nesta máquina, conexão recusada em 127.0.0.1 leva ~2s para voltar
        # (retransmissão de SYN do stack do Windows), não é instantânea como em
        # Linux. Por isso o trecho tem três checagens e nenhum laço de polling
        # — a regra deste arquivo é rodar em segundos, e um laço aqui custaria
        # 2s por volta.
        servidor.shutdown()
        servidor.server_close()
        r = c.post("/api/manutencao/reindexar", headers=cab)
        checar("com o Tomcat fora do ar o disparo ainda volta 200: é assíncrono",
               r.status_code == 200 and r.json().get("iniciado") is True, r.json())
        p = c.get("/api/manutencao/reindexar", headers=cab)
        checar("o progresso não vira 409: 200 com o erro dentro do corpo",
               p.status_code == 200
               and "BibLivre" in (p.json().get("erro") or ""), p.json())
        r = c.post("/api/manutencao/caches", headers=cab)
        checar("o botão síncrono, aí sim, é 409 biblivre_indisponivel com motivo",
               r.status_code == 409
               and r.json().get("codigo") == "biblivre_indisponivel"
               and r.json().get("mensagem"), r.json())
    finally:
        try:
            servidor.shutdown()
            servidor.server_close()
        except Exception:
            pass
        web._cfg.update(config_antes)
        web._invalidar_sonda()
        desligar()
        operador.esquecer_tudo()


def main():
    print(f"dados de teste em {DADOS}")
    verificar_api()
    verificar_migracao()
    verificar_migracao_pela_tela()
    verificar_sessao_operador()
    verificar_circulacao()
    verificar_resolver()
    verificar_conferencia()
    verificar_canal_http()
    verificar_manutencao_api()
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
