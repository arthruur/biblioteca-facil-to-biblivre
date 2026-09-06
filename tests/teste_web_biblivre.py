"""
Verificação do canal HTTP com o BibLivre (`biblio.biblivre.web`) — sem rede.

    python tests/teste_web_biblivre.py

O módulo `web` é o único do pacote que não fala SQL: ele manda o próprio
BibLivre reindexar, derrubar cache de tradução e gerar o `.b5bz`. Testá-lo
contra uma instalação real significaria ter Tomcat, PostgreSQL e um acervo de
14 mil registros de pé — então aqui sobe um **BibLivre de mentira**: um
`http.server` numa porta local que imita o `JsonController` (o mesmo
`{"success", "message", "message_level"}`), o cookie JSESSIONID e o
`AuthorizationException` que vira `error.no_permission`.

O que isto cobre, que é o que doeria mais se regredisse:

  1. login ok e login recusado — e a senha não aparecendo em `estado()`;
  2. `reindexar()` voltando **na hora** enquanto o servidor ainda está preso na
     chamada longa (é a regra que o módulo existe para respeitar);
  3. o polling de `progresso_reindex()` até `rodando: False`, com `pct`;
  4. sessão expirada: a chamada seguinte reloga sozinha e repete, uma vez só;
  5. HTML em vez de JSON e servidor fora do ar viram dict com `erro` legível,
     nunca exceção crua.
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parents[1]

# Antes de importar `biblio.*`: sem isto um `.env` da máquina pode preencher
# BIBLIVRE_WEB_* e o caso de "não configurado" passaria a nascer configurado.
os.environ["BIBLIO_SEM_ENV"] = "1"
for _chave in ("BIBLIVRE_WEB_URL", "BIBLIVRE_WEB_USUARIO", "BIBLIVRE_WEB_SENHA"):
    os.environ.pop(_chave, None)

# Fallback para quem roda sem `pip install -e .` (o `verificar.py` conta com o
# editável; este arquivo precisa rodar sozinho também).
sys.path.insert(0, str(RAIZ / "packages" / "biblivre-client" / "src"))

from biblio.biblivre import web  # noqa: E402

USUARIO = "admin"
SENHA = "abracadabra-de-mentira"

falhas: list[str] = []


def checar(rotulo, condicao, extra=""):
    print(("  ok   " if condicao else "  FALHA") + f"  {rotulo}"
          + (f"   {extra}" if extra and not condicao else ""))
    if not condicao:
        falhas.append(rotulo)


def secao(titulo):
    print(f"\n{titulo}")


# --- O BibLivre de mentira ----------------------------------------------


class Falso:
    """Estado do servidor, compartilhado entre as threads do handler."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sessoes: set[str] = set()
        self.proxima_sessao = 0
        self.logins = 0                 # quantas vezes login/login foi chamado
        self.reindexes = 0
        self.indexados = 0
        self.total = 100
        self.demora_reindex = 1.0       # o reindex real leva minutos
        self.responder_html = False     # simula URL base errada
        self.expirar_na_proxima = False # simula sessão perdida no Tomcat
        self.backup_id = 0
        self.backup_passo = 0
        self.backup_total = 3


ESTADO = Falso()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # o teste já é barulhento o bastante

    # -- utilidades --

    def _responder(self, dados: dict, tipo="application/json;charset=UTF-8"):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for cabecalho, valor in getattr(self, "_extra", []):
            self.send_header(cabecalho, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def _responder_html(self):
        corpo = b"<!DOCTYPE html><html><body>tela de login do BibLivre</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=UTF-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _sem_permissao(self):
        # Cópia do que o JsonController.doAuthorizationError produz.
        self._responder({"success": False,
                         "message": "Você não tem permissão para executar esta ação",
                         "message_level": "warning"})

    def _logado(self) -> bool:
        bruto = self.headers.get("Cookie", "")
        for parte in bruto.split(";"):
            nome, _, valor = parte.strip().partition("=")
            if nome == "JSESSIONID":
                with ESTADO.lock:
                    if ESTADO.expirar_na_proxima:
                        ESTADO.expirar_na_proxima = False
                        ESTADO.sessoes.discard(valor)
                        return False
                    return valor in ESTADO.sessoes
        return False

    # -- roteamento --

    def do_POST(self):
        self._extra = []
        consulta = parse_qs(urlparse(self.path).query)
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = parse_qs(self.rfile.read(tamanho).decode("utf-8")) if tamanho else {}

        with ESTADO.lock:
            html = ESTADO.responder_html
        if html:
            return self._responder_html()

        modulo = (consulta.get("module") or [""])[0]
        acao = (consulta.get("action") or [""])[0]

        if modulo == "login" and acao == "login":
            return self._login(corpo)

        if not self._logado():
            return self._sem_permissao()

        if modulo == "administration.indexing":
            return self._indexing(acao, consulta)
        if modulo == "administration.translations" and acao == "list":
            return self._responder({"success": True, "translations": {"pt-BR": {}}})
        if modulo == "administration.backup":
            return self._backup(acao, consulta)

        return self._responder({"success": False, "message": "error.void",
                                "message_level": "error"})

    # -- ações --

    def _login(self, corpo):
        usuario = (corpo.get("username") or [""])[0]
        senha = (corpo.get("password") or [""])[0]
        with ESTADO.lock:
            ESTADO.logins += 1
        if usuario != USUARIO or senha != SENHA:
            return self._responder({"success": False,
                                    "message": "Acesso negado. Usuário ou senha inválidos",
                                    "message_level": "warning"})
        with ESTADO.lock:
            ESTADO.proxima_sessao += 1
            sid = f"SESSAO{ESTADO.proxima_sessao}"
            ESTADO.sessoes.add(sid)
        self._extra = [("Set-Cookie", f"JSESSIONID={sid}; Path=/")]
        return self._responder({"success": True,
                                "message": "Seja bem-vindo ao Biblivre IV",
                                "message_level": "normal"})

    def _indexing(self, acao, consulta):
        if acao == "reindex":
            with ESTADO.lock:
                ESTADO.reindexes += 1
                ESTADO.indexados = 0        # clearIndexes roda antes
                demora = ESTADO.demora_reindex
            time.sleep(demora)              # o de verdade leva minutos
            with ESTADO.lock:
                ESTADO.indexados = ESTADO.total
            return self._responder({"success": True, "time": demora})
        if acao == "progress":
            with ESTADO.lock:
                atual, total = ESTADO.indexados, ESTADO.total
            return self._responder({"success": True, "current": atual,
                                    "total": total, "complete": atual == total})
        return self._responder({"success": False, "message": "ação desconhecida",
                                "message_level": "error"})

    def _backup(self, acao, consulta):
        if acao == "prepare":
            with ESTADO.lock:
                ESTADO.backup_id += 1
                ESTADO.backup_passo = 0
                ident = ESTADO.backup_id
            return self._responder({"success": True, "id": ident})
        if acao == "backup":
            time.sleep(0.4)
            with ESTADO.lock:
                ESTADO.backup_passo = ESTADO.backup_total
            return self._responder({"success": True})
        if acao == "progress":
            with ESTADO.lock:
                passo, total = ESTADO.backup_passo, ESTADO.backup_total
            return self._responder({"success": True, "current": passo,
                                    "total": total, "complete": passo == total})
        return self._responder({"success": False, "message": "ação desconhecida",
                                "message_level": "error"})


def subir_servidor():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}/"


def esperar(condicao, limite=10.0, passo=0.05):
    """Espera ativa curta — o polling é o que está sendo testado."""
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(passo)
    return False


# --- Os testes ----------------------------------------------------------


def verificar_configuracao(url):
    secao("configuração e credencial")

    antes = web.estado()
    checar("estado() começa não configurado", antes["configurado"] is False, antes)
    checar("estado() não configurado explica o que falta",
           "não configurado" in antes["erro"], antes)

    ruim = web.configurar("localhost:8080/Biblivre5", USUARIO, SENHA)
    checar("URL sem esquema é recusada", ruim["configurado"] is False, ruim)

    sem_senha = web.configurar(url, USUARIO, "")
    checar("senha vazia é recusada", sem_senha["configurado"] is False, sem_senha)

    resultado = web.configurar(url, USUARIO, SENHA)
    checar("configurar() devolve configurado", resultado["configurado"] is True, resultado)
    checar("configurar() normaliza a barra final", resultado["url"].endswith("/"),
           resultado)
    checar("a senha não volta em configurar()",
           SENHA not in json.dumps(resultado, ensure_ascii=False), resultado)


def verificar_login(url):
    secao("login")

    web.configurar(url, USUARIO, "senha-errada")
    ruim = web.entrar()
    checar("login com senha errada não levanta e traz erro",
           ruim["ok"] is False and ruim["erro"], ruim)
    checar("o erro do login é legível e sem a senha",
           "negado" in ruim["erro"].lower() and "senha-errada" not in ruim["erro"],
           ruim)

    estado_ruim = web.estado()
    checar("estado() após login recusado diz desconectado",
           estado_ruim["conectado"] is False, estado_ruim)

    web.configurar(url, USUARIO, SENHA)
    bom = web.entrar()
    checar("login válido entra", bom["ok"] is True, bom)

    agora = web.estado()
    checar("estado() diz conectado", agora["conectado"] is True, agora)
    checar("a senha não vaza em estado()",
           SENHA not in json.dumps(agora, ensure_ascii=False), agora)
    checar("estado() tem exatamente o contrato",
           {"configurado", "url", "conectado", "erro"} <= set(agora), agora)


def verificar_reindex(url):
    secao("reindexação (não pode bloquear)")

    web.configurar(url, USUARIO, SENHA)
    with ESTADO.lock:
        ESTADO.demora_reindex = 1.0
        ESTADO.reindexes = 0

    inicio = time.time()
    disparo = web.reindexar()
    gasto = time.time() - inicio
    checar("reindexar() aceita", disparo["ok"] is True, disparo)
    checar(f"reindexar() volta na hora (gastou {gasto:.2f}s, servidor dorme 1.0s)",
           gasto < 0.5, disparo)

    andando = web.progresso_reindex()
    checar("progresso_reindex() diz rodando", andando["rodando"] is True, andando)
    checar("progresso_reindex() tem o contrato",
           {"rodando", "atual", "total", "pct"} <= set(andando), andando)

    checar("o reindex termina",
           esperar(lambda: not web.progresso_reindex()["rodando"]))

    fim = web.progresso_reindex()
    checar("no fim, sem erro", fim["erro"] == "", fim)
    checar("no fim, pct = 100", fim["pct"] == 100, fim)
    checar("no fim, atual == total", fim["atual"] == fim["total"] == 100, fim)
    checar("terminado_em preenchido", bool(fim["terminado_em"]), fim)
    with ESTADO.lock:
        checar("o BibLivre foi chamado uma vez só", ESTADO.reindexes == 1)


def verificar_reindex_concorrente(url):
    secao("uma reindexação por vez")

    web.configurar(url, USUARIO, SENHA)
    with ESTADO.lock:
        ESTADO.demora_reindex = 1.0
        ESTADO.reindexes = 0

    primeiro = web.reindexar()
    segundo = web.reindexar()
    checar("o primeiro disparo passa", primeiro["ok"] is True, primeiro)
    checar("o segundo é recusado", segundo["ok"] is False, segundo)
    checar("o segundo explica por quê",
           "andamento" in segundo["erro"], segundo)

    esperar(lambda: not web.progresso_reindex()["rodando"])
    with ESTADO.lock:
        checar("o BibLivre não recebeu a segunda chamada", ESTADO.reindexes == 1)


def verificar_sessao_expirada(url):
    secao("sessão expirada reloga e repete")

    web.configurar(url, USUARIO, SENHA)
    entrada = web.entrar()
    checar("entrou antes de expirar", entrada["ok"] is True, entrada)

    with ESTADO.lock:
        ESTADO.logins = 0
        ESTADO.expirar_na_proxima = True

    depois = web.resetar_caches()
    checar("a chamada seguinte à expiração dá certo mesmo assim",
           depois["ok"] is True, depois)
    with ESTADO.lock:
        checar("relogou uma vez só", ESTADO.logins == 1, f"logins={ESTADO.logins}")

    # Expiração + credencial ruim: tem de virar erro, não laço de login.
    web.configurar(url, USUARIO, SENHA)
    web.entrar()
    with ESTADO.lock:
        ESTADO.logins = 0
        ESTADO.expirar_na_proxima = True
    # Mexer em `_cfg` direto, e não por `configurar()`, é de propósito: o caso
    # é "o admin trocou a senha no BibLivre com a sessão aberta", e
    # `configurar()` derrubaria a sessão junto — apagando o que se quer testar.
    web._cfg["senha"] = "trocaram-a-senha"
    perdido = web.resetar_caches()
    checar("expirou e o novo login falhou: erro, não exceção",
           perdido["ok"] is False and "expirou" in perdido["erro"], perdido)
    with ESTADO.lock:
        checar("não entrou em laço de login", ESTADO.logins <= 2,
               f"logins={ESTADO.logins}")


def verificar_caches(url):
    secao("caches estáticos")

    web.configurar(url, USUARIO, SENHA)
    resultado = web.resetar_caches()
    checar("traduções resetadas", resultado["traducoes"] is True, resultado)
    checar("campos de leitor NÃO resetados (não há ação HTTP no BibLivre 5)",
           resultado["campos_de_leitor"] is False, resultado)
    checar("o aviso explica que o Tomcat precisa reiniciar",
           "Tomcat" in resultado["aviso"], resultado)


def verificar_backup(url):
    secao("backup .b5bz")

    web.configurar(url, USUARIO, SENHA)

    invalido = web.gerar_backup("zip")
    checar("tipo de backup inválido é recusado", invalido["ok"] is False, invalido)

    inicio = time.time()
    disparo = web.gerar_backup("full")
    gasto = time.time() - inicio
    checar("gerar_backup() aceita", disparo["ok"] is True, disparo)
    checar(f"gerar_backup() não espera o pg_dump ({gasto:.2f}s)", gasto < 0.3, disparo)
    checar("veio o id do backup", disparo.get("id"), disparo)

    checar("o backup termina", esperar(lambda: not web.estado_backup()["rodando"]))

    fim = web.estado_backup()
    checar("backup sem erro", fim["erro"] == "", fim)
    checar("backup em 100%", fim["pct"] == 100, fim)
    checar("a URL de download usa controller=download",
           "controller=download" in fim["url_download"]
           and f"id={fim['id']}" in fim["url_download"], fim)


def verificar_falhas_de_rede(url, porta_morta):
    secao("falha de rede e HTML em vez de JSON")

    web.configurar(url, USUARIO, SENHA)
    web.entrar()
    with ESTADO.lock:
        ESTADO.responder_html = True
    try:
        resultado = web.resetar_caches()
    finally:
        with ESTADO.lock:
            ESTADO.responder_html = False
    checar("HTML em vez de JSON vira erro, não exceção", resultado["ok"] is False,
           resultado)
    checar("o erro do HTML aponta a URL base",
           "HTML" in resultado["erro"] and "URL base" in resultado["erro"], resultado)

    web.configurar(porta_morta, USUARIO, SENHA)
    caido = web.entrar()
    checar("servidor fora do ar vira erro legível", caido["ok"] is False, caido)
    checar("o erro cita a URL", porta_morta.rstrip("/") in caido["erro"], caido)

    fora = web.estado()
    checar("estado() com o servidor fora do ar não levanta",
           fora["conectado"] is False and fora["erro"], fora)

    sem_servidor = web.progresso_reindex()
    checar("progresso_reindex() sobrevive ao servidor fora do ar",
           sem_servidor["erro"] != "" and sem_servidor["rodando"] is False,
           sem_servidor)


def main():
    servidor, url = subir_servidor()
    # Uma porta que ninguém escuta: subimos e derrubamos para ter o número.
    morto, url_morta = subir_servidor()
    morto.shutdown()
    morto.server_close()

    print(f"BibLivre de mentira em {url}")
    try:
        verificar_configuracao(url)
        verificar_login(url)
        verificar_reindex(url)
        verificar_reindex_concorrente(url)
        verificar_sessao_expirada(url)
        verificar_caches(url)
        verificar_backup(url)
        verificar_falhas_de_rede(url, url_morta)
    finally:
        servidor.shutdown()
        servidor.server_close()

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
