"""
O outro canal: HTTP contra o próprio BibLivre, não SQL.

    from biblio.biblivre import web

    web.configurar("http://localhost:8080/Biblivre5/", "admin", "...")
    web.entrar()
    web.reindexar()                 # dispara e volta na hora
    web.progresso_reindex()         # {"rodando": True, "atual": 3210, "total": 14866}

POR QUE HTTP AQUI, SE TODO O RESTO É SQL
----------------------------------------
Inserir em `biblio_records` por SQL não preenche `biblio_idx_*`: o registro
existe e não aparece na busca. Reproduzir o indexador em SQL seria copiar a
tokenização Java do `IndexingBO` — e índice errado falha **em silêncio**, que é
a pior superfície possível para uma reimplementação. Mais barato e mais correto
é mandar o BibLivre indexar: as ações já existem
(`biblivre.administration.indexing.Handler`: `reindex` e `progress`), e o
mesmo canal serve para o backup `.b5bz` (que é `pg_dump` empacotado pelo
`BackupBO`, não formato de intercâmbio) e para derrubar o cache estático de
tradução sem reiniciar o Tomcat.

O QUE FOI VERIFICADO NO FONTE
-----------------------------
Lido em https://github.com/cleydyr/Biblivre-5 (fork; a instalação da biblioteca
é 5.0.x — ver "O QUE FALTA CONFIRMAR" no fim).

`core/controllers/SchemaServlet.java` + `core/ExtendedRequest.java`
(`loadSchemaAndController`) + `core/controllers/Controller.java`:
    Um servlet só, mapeado em `/`. A URL é
    `<base>?controller=json&module=<pacote>&action=<método>` — a forma que o
    próprio fonte documenta em comentário (`administration/backup/Handler.java`
    traz `http://localhost:8080/Biblivre5/?controller=json&module=administration.backup&action=backup`).
    `module` vira `Class.forName("biblivre." + module + ".Handler")` e `action`
    vira o método, em camelCase. O **schema** sai do primeiro segmento do path
    depois do contexto; não havendo segmento, uma instalação de biblioteca
    única cai em `Constants.SINGLE_SCHEMA` (`single`). Por isso a URL base
    configurada é quem escolhe o schema: `.../Biblivre5/` numa instalação
    única, `.../Biblivre5/<schema>/` numa multi-biblioteca.

`login/Handler.java` — `login` lê `username` e `password` (nada mais), e no
    sucesso grava `<schema>.logged_user` e `<schema>.logged_user_atps` na
    sessão do Tomcat (cookie JSESSIONID). Não devolve JSON próprio: o
    `JsonController` monta `{"success": ..., "message": ..., "message_level":
    ...}` a partir do `Message` (`ActionResult.NORMAL`/`SUCCESS` = sucesso;
    `WARNING` = "login.access_denied").

`administration/indexing/Handler.java` — `reindex` (parâmetro `record_type`,
    default `"biblio"`) e `progress`. `progress` **não** devolve um vetor: é
    `{"success", "current", "total", "complete"}`. `IndexingBO.reindex` limpa
    os índices e relê `biblio_records` em `limit = 30`, com um lock `volatile`
    por tipo de registro — chamar duas vezes em paralelo faz a segunda voltar
    calada, sem indexar nada. `getReindexProgress` é `countIndexed` contra
    `count`: durante o reindex o `atual` **começa em zero**, porque
    `clearIndexes` roda antes.

`administration/translations/Handler.java` — a ação `list` chama
    `Languages.reset(schema)` e, para cada idioma, `Translations.reset(schema,
    language)`. Confirmado: dá para derrubar o cache de tradução por HTTP.

`administration/backup/Handler.java` + `BackupBO.java` — o `.b5bz` sai de três
    ações em sequência: `prepare` (parâmetro `type`, um de `full`,
    `exclude_digital_media`, `digital_media_only`; devolve `{"success","id"}`),
    `backup` (parâmetro `id`, **síncrono** — roda `pg_dump` e só responde no
    fim) e `progress` (parâmetro `id`; `{"current","total","complete"}`). O
    arquivo se recupera por `controller=download`, não `json`:
    `<base>?controller=download&module=administration.backup&action=download&id=<id>`.
    Em disco ele fica no destino de backup com o nome
    `Biblivre Backup AAAA-MM-DD HHhMMmSSs Full.b5bz` (`BackupBO.move`).

`core/auth/AuthorizationPoints.java` — `login/login` é `LOGIN`;
    `administration.indexing/{reindex,progress}` é `ADMINISTRATION_INDEXING`;
    `administration.translations/list` é `ADMINISTRATION_TRANSLATIONS`;
    `administration.backup/{prepare,backup,download,progress,list}` é
    `ADMINISTRATION_BACKUP`. Sem sessão, `AuthorizationBO.authorize` levanta
    `AuthorizationException` e o `JsonController.doAuthorizationError` responde
    `{"success": false, "message": "<error.no_permission>", "message_level":
    "warning"}` — é essa a assinatura de **sessão expirada** que este módulo
    reconhece para relogar e repetir a chamada uma vez.

O VEREDITO SOBRE `UserFields.reset` — O RESTART DO TOMCAT **NÃO** PODE MORRER
----------------------------------------------------------------------------
Procurado no fonte inteiro. `UserFields.reset()` tem exatamente dois chamadores
(`circulation/user/UserFields.java`, no `static {}` da própria classe, e
`core/StaticBO.resetCache()`), e `StaticBO.resetCache()` tem três:

    administration/setup/Handler.java:381   restore de backup  (destrutivo)
    administration/setup/Handler.java:445   importBiblivre3    (destrutivo)
    core/schemas/Schemas.java:226           deleteSchema       (destrutivo)

Nenhuma ação alcançável por HTTP derruba o cache de campos de leitor sem
destruir a instalação. Campo criado em `users_fields` por SQL continua exigindo
**reiniciar o Tomcat** para aparecer. (Pior: `SchemaServlet.processStaticRequest`
serve `<schema>.user_fields.js` de um arquivo de cache em disco montado por
`UserFields.getFields`, então há duas camadas do mesmo cache.) `resetar_caches()`
faz o que dá — as traduções — e diz na resposta que os campos de leitor ficaram
de fora.

DUAS COISAS QUE O IMPLEMENTADOR PRECISA RESPEITAR
-------------------------------------------------
  * `reindexar()` **não bloqueia**: 14 mil registros em lotes de 30, com heap de
    256 MB, é chamada longa. Dispara em thread e devolve; quem acompanha é
    `progresso_reindex()`. Vale o mesmo para `gerar_backup()`, porque a ação
    `backup` do BibLivre é síncrona.
  * A senha do admin segue a regra da senha do Postgres: memória, nunca disco,
    nunca de volta em `estado()`. Ela viaja no **corpo** do POST, nunca na query
    string, para não cair no access log do Tomcat.

O QUE FALTA CONFIRMAR CONTRA O WAR INSTALADO
--------------------------------------------
Isto foi lido num fork no GitHub; a biblioteca roda um 5.0.x instalado pelo
instalador de Windows. Antes de confiar em produção, conferir na instalação:
o contexto da URL (`/Biblivre5/` é o padrão do instalador, mas é configurável),
o nome do schema (`single` numa instalação de biblioteca única), e se a ação
`administration.translations/list` responde JSON — numa base com muitas
traduções ela devolve o mapa inteiro, que é grande. Nada aqui depende do
tamanho da resposta, só do `success`.
"""

import json as _json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar

from .ambiente import carregar_env

# Mesma postura de `conexao.py`: o `.env` da raiz precisa estar no ambiente na
# hora em que as variáveis são lidas. O que já estava no ambiente vence.
carregar_env()

# Chamada normal (login, progress, prepare): se o Tomcat não respondeu em 15s,
# alguma coisa está errada. As duas chamadas longas — `reindex` e `backup` —
# rodam em thread e usam `TIMEOUT_LONGO`.
TIMEOUT_PADRAO = 15
TIMEOUT_LONGO = 3600

# `estado()` é chamado em laço pela tela; o TTL evita abrir socket a cada dois
# segundos. Mesmo número da sonda do Postgres, pela mesma razão.
TTL_SONDA = 15.0

TIPOS_BACKUP = ("full", "exclude_digital_media", "digital_media_only")

_lock = threading.Lock()          # protege `_cfg` e `_sessao`
_login_lock = threading.Lock()    # só uma thread relogando por vez
_estado_lock = threading.Lock()   # protege `_reindex` e `_backup`


def _env(*nomes: str, padrao: str = "") -> str:
    for n in nomes:
        v = os.environ.get(n)
        if v:
            return v
    return padrao


def _normalizar_url(url: str) -> str:
    """Base sempre com barra no fim: sem ela o `doGet` do servlet responde 302
    (`mustRedirectToSchema`) antes de olhar o `controller`."""
    return (url or "").strip().rstrip("/") + "/"


_cfg: dict = {
    "url": _normalizar_url(_env("BIBLIVRE_WEB_URL")) if _env("BIBLIVRE_WEB_URL") else "",
    "usuario": _env("BIBLIVRE_WEB_USUARIO", padrao="admin"),
    "senha": _env("BIBLIVRE_WEB_SENHA"),
}

_sessao: dict = {"opener": None, "logado": False}

_reindex: dict = {
    "rodando": False, "record_type": "biblio", "atual": 0, "total": 0,
    "erro": "", "iniciado_em": "", "terminado_em": "",
}

_backup: dict = {
    "rodando": False, "id": None, "tipo": "", "atual": 0, "total": 0,
    "erro": "", "iniciado_em": "", "terminado_em": "",
}

_sonda: dict = {}
_sonda_em: float = 0.0


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- Transporte ---------------------------------------------------------


def _novo_opener():
    """
    Opener com pote de cookies próprio — é ele que guarda o JSESSIONID.

    Em memória, como a senha: reiniciar o processo desloga, e tudo bem.
    """
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar()))


def _configurado(cfg: dict) -> bool:
    return bool(cfg.get("url") and cfg.get("usuario") and cfg.get("senha"))


def _texto_da_resposta(resp) -> str:
    bruto = resp.read()
    tipo = resp.headers.get("Content-Type", "")
    codec = "utf-8"
    if "charset=" in tipo:
        codec = tipo.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
    try:
        return bruto.decode(codec, errors="replace")
    except LookupError:
        return bruto.decode("utf-8", errors="replace")


def _http(cfg: dict, opener, modulo: str, acao: str, corpo: dict | None,
          extra: dict | None, timeout: int) -> dict:
    """
    Uma requisição. `-> {"ok", "json", "erro"}`; nunca levanta.

    `controller/module/action` (e o que for identificador, como `id` ou
    `record_type`) vão na query string, como nos comentários do fonte; o resto
    vai no corpo, porque é onde a senha precisa estar para não ir ao access log.
    """
    consulta = {"controller": "json", "module": modulo, "action": acao}
    consulta.update(extra or {})
    url = cfg["url"] + "?" + urllib.parse.urlencode(consulta)
    dados = urllib.parse.urlencode(corpo or {}).encode("utf-8")

    req = urllib.request.Request(url, data=dados, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json",
    })

    try:
        with opener.open(req, timeout=timeout) as resp:
            texto = _texto_da_resposta(resp)
            tipo = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return {"ok": False, "json": {},
                "erro": f"o BibLivre respondeu HTTP {e.code} em {modulo}/{acao}"}
    except urllib.error.URLError as e:
        return {"ok": False, "json": {},
                "erro": f"não foi possível falar com o BibLivre em {cfg['url']}: "
                        f"{getattr(e, 'reason', e)}"}
    except Exception as e:  # socket.timeout, erro de TLS, DNS...
        return {"ok": False, "json": {},
                "erro": f"falha ao chamar o BibLivre ({modulo}/{acao}): {e}"}

    enxuto = texto.lstrip()
    if not enxuto:
        return {"ok": False, "json": {},
                "erro": f"o BibLivre respondeu vazio em {modulo}/{acao}"}
    if enxuto[0] == "<" or "html" in tipo.lower():
        # O servlet cai em `/jsp/index.jsp` quando não reconhece o controller:
        # quase sempre URL base errada, não sessão perdida.
        return {"ok": False, "json": {},
                "erro": "o BibLivre respondeu HTML em vez de JSON — confira a "
                        f"URL base ({cfg['url']}), que deve ser a raiz da "
                        "instalação, algo como http://localhost:8080/Biblivre5/"}

    try:
        dados_json = _json.loads(enxuto)
    except ValueError:
        return {"ok": False, "json": {},
                "erro": f"resposta do BibLivre não é JSON ({modulo}/{acao})"}
    if not isinstance(dados_json, dict):
        return {"ok": False, "json": {},
                "erro": f"resposta do BibLivre em formato inesperado ({modulo}/{acao})"}

    return {"ok": bool(dados_json.get("success")), "json": dados_json, "erro": ""}


def _sessao_expirada(resposta: dict) -> bool:
    """
    `JsonController.doAuthorizationError` responde `error.no_permission`.

    A mensagem chega traduzida, então o que se procura é o miolo que sobrevive
    em pt-BR ("não tem permissão") e em inglês ("no permission") — mais a
    própria chave, para o caso de a tradução faltar na base.
    """
    if resposta.get("ok"):
        return False
    msg = str(resposta.get("json", {}).get("message", "")).lower()
    return "permiss" in msg or "no_permission" in msg


_ERRO_SEM_CONFIG = ("BibLivre web não configurado: falta a URL da instalação "
                    "e a credencial de administrador")


def _chamar(modulo: str, acao: str, corpo: dict | None = None,
            extra: dict | None = None, timeout: int = TIMEOUT_PADRAO,
            _relogar: bool = True) -> dict:
    """
    Chamada autenticada. Entra sozinho se ainda não entrou, e se a sessão tiver
    expirado tenta `entrar()` **uma** vez e repete.
    """
    with _lock:
        cfg = dict(_cfg)
        opener = _sessao["opener"]
        logado = _sessao["logado"]

    if not _configurado(cfg):
        return {"ok": False, "json": {}, "erro": _ERRO_SEM_CONFIG}

    if not logado or opener is None:
        entrada = entrar()
        if not entrada.get("ok"):
            return {"ok": False, "json": {}, "erro": entrada.get("erro", "")}
        with _lock:
            opener = _sessao["opener"]

    resposta = _http(cfg, opener, modulo, acao, corpo, extra, timeout)

    if _relogar and _sessao_expirada(resposta):
        with _lock:
            _sessao["logado"] = False
        entrada = entrar()
        if not entrada.get("ok"):
            return {"ok": False, "json": {},
                    "erro": "sessão do BibLivre expirou e o novo login falhou: "
                            + entrada.get("erro", "")}
        return _chamar(modulo, acao, corpo, extra, timeout, _relogar=False)

    if not resposta["ok"] and not resposta["erro"]:
        resposta["erro"] = (resposta["json"].get("message")
                            or f"o BibLivre recusou {modulo}/{acao}")
    return resposta


# --- Configuração e estado ----------------------------------------------


def configurar(url: str, usuario: str, senha: str) -> dict:
    """
    URL base da instalação + credencial de admin. Só memória.

    Devolve o mesmo dicionário de `estado()` — **sem a senha**, que é o que
    pode ir para a tela ou para o log.
    """
    url = _normalizar_url(url)
    if not url.startswith(("http://", "https://")):
        return {"configurado": False, "url": "", "conectado": False,
                "erro": "URL inválida: precisa começar com http:// ou https://"}
    if not (usuario or "").strip() or not (senha or ""):
        return {"configurado": False, "url": url, "conectado": False,
                "erro": "usuário e senha do administrador do BibLivre são obrigatórios"}

    with _lock:
        _cfg["url"] = url
        _cfg["usuario"] = usuario.strip()
        _cfg["senha"] = senha
        # Credencial nova, sessão velha não vale mais.
        _sessao["opener"] = None
        _sessao["logado"] = False
    _invalidar_sonda()
    return estado()


def estado() -> dict:
    """
    `{"configurado", "url", "conectado", "erro"}` — sem a senha dentro.

    `conectado` é resultado de sonda real (um `progress` autenticado), com
    cache de `TTL_SONDA`, pela mesma razão que a sonda do Postgres tem: a tela
    pergunta em laço.
    """
    global _sonda, _sonda_em

    with _lock:
        cfg = dict(_cfg)

    if not _configurado(cfg):
        return {"configurado": False, "url": cfg.get("url", ""),
                "conectado": False, "erro": _ERRO_SEM_CONFIG}

    with _lock:
        fresco = _sonda and (time.time() - _sonda_em) < TTL_SONDA
        cache = dict(_sonda) if fresco else None
    if cache is not None:
        return {"configurado": True, "url": cfg["url"], **cache}

    resposta = _chamar("administration.indexing", "progress",
                       extra={"record_type": "biblio"})
    resultado = {"conectado": bool(resposta["ok"]), "erro": resposta["erro"]}

    with _lock:
        _sonda = dict(resultado)
        _sonda_em = time.time()
    return {"configurado": True, "url": cfg["url"], **resultado}


def _invalidar_sonda() -> None:
    global _sonda_em
    with _lock:
        _sonda_em = 0.0


def entrar() -> dict:
    """
    Login; guarda o cookie de sessão em memória.

    `login/Handler.java` lê `username` e `password` — os dois no corpo do POST,
    nunca na query. Um pote de cookies novo a cada login: sessão velha do
    Tomcat não é reaproveitada por engano.
    """
    with _lock:
        cfg = dict(_cfg)

    if not _configurado(cfg):
        return {"ok": False, "erro": _ERRO_SEM_CONFIG}

    with _login_lock:
        opener = _novo_opener()
        resposta = _http(cfg, opener, "login", "login",
                         corpo={"username": cfg["usuario"], "password": cfg["senha"]},
                         extra=None, timeout=TIMEOUT_PADRAO)

        if not resposta["ok"]:
            with _lock:
                _sessao["opener"] = None
                _sessao["logado"] = False
            erro = resposta["erro"] or resposta["json"].get("message") or \
                "o BibLivre recusou o login (usuário ou senha inválidos)"
            _invalidar_sonda()
            return {"ok": False, "erro": erro}

        with _lock:
            _sessao["opener"] = opener
            _sessao["logado"] = True
    _invalidar_sonda()
    return {"ok": True, "erro": "", "usuario": cfg["usuario"]}


# --- Reindexação --------------------------------------------------------


def reindexar(record_type: str = "biblio") -> dict:
    """
    Dispara o reindex da base bibliográfica. **Não bloqueia.**

    `IndexingBO.reindex` lê `biblio_records` em lotes de 30 e só responde no
    fim; 14 mil registros levam minutos. A chamada vai para uma thread e quem
    acompanha é `progresso_reindex()`.

    Uma por vez: o próprio BibLivre tem um lock por tipo de registro e faz a
    segunda chamada voltar calada, sem indexar nada — o que daria a impressão
    de sucesso. Aqui a segunda chamada é recusada com erro legível.
    """
    with _lock:
        cfg = dict(_cfg)
    if not _configurado(cfg):
        return {"ok": False, "erro": _ERRO_SEM_CONFIG}

    with _estado_lock:
        if _reindex["rodando"]:
            return {"ok": False,
                    "erro": "já existe uma reindexação em andamento — "
                            "acompanhe por progresso_reindex()"}
        _reindex.update({"rodando": True, "record_type": record_type,
                         "atual": 0, "total": 0, "erro": "",
                         "iniciado_em": _agora(), "terminado_em": ""})

    threading.Thread(target=_rodar_reindex, args=(record_type,),
                     name="biblivre-reindex", daemon=True).start()
    return {"ok": True, "erro": "", "rodando": True, "record_type": record_type}


def _rodar_reindex(record_type: str) -> None:
    try:
        resposta = _chamar("administration.indexing", "reindex",
                           extra={"record_type": record_type},
                           timeout=TIMEOUT_LONGO)
        erro = "" if resposta["ok"] else resposta["erro"]
    except Exception as e:  # a thread não pode morrer levando o estado junto
        erro = f"falha inesperada na reindexação: {e}"

    with _estado_lock:
        _reindex["rodando"] = False
        _reindex["erro"] = erro
        _reindex["terminado_em"] = _agora()


def progresso_reindex() -> dict:
    """
    `{"rodando", "atual", "total", "pct"}` — e mais `erro`/`terminado_em`.

    `atual` e `total` vêm do BibLivre (`countIndexed` contra `count`), não de
    contagem local. Durante o reindex o `atual` começa em zero, porque
    `IndexingBO.reindex` limpa os índices antes de reconstruir. Se a consulta
    ao BibLivre falhar, devolve o último valor conhecido com o erro junto —
    perder o polling não é motivo para perder o estado.
    """
    with _estado_lock:
        local = dict(_reindex)

    resposta = _chamar("administration.indexing", "progress",
                       extra={"record_type": local["record_type"]})

    if resposta["ok"]:
        atual = int(resposta["json"].get("current") or 0)
        total = int(resposta["json"].get("total") or 0)
        with _estado_lock:
            _reindex["atual"] = atual
            _reindex["total"] = total
        erro = local["erro"]
    else:
        atual, total = local["atual"], local["total"]
        erro = local["erro"] or resposta["erro"]

    return {"rodando": local["rodando"], "atual": atual, "total": total,
            "pct": 0 if not total else min(100, int(atual * 100 / total)),
            "erro": erro, "iniciado_em": local["iniciado_em"],
            "terminado_em": local["terminado_em"]}


# --- Caches estáticos ---------------------------------------------------


def resetar_caches() -> dict:
    """
    Traduções sim, campos de leitor não — e a resposta diz isso.

    `administration.translations/list` chama `Languages.reset(schema)` e
    `Translations.reset(schema, idioma)` antes de montar a resposta, então
    serve de reset por HTTP.

    Não existe equivalente para `UserFields`: os únicos caminhos até
    `StaticBO.resetCache()` são restore de backup, importação do Biblivre 3 e
    remoção de schema — todos destrutivos. Campo de leitor criado por SQL
    continua exigindo reiniciar o Tomcat. Ver o docstring do módulo.
    """
    resposta = _chamar("administration.translations", "list")
    return {
        "ok": bool(resposta["ok"]),
        "traducoes": bool(resposta["ok"]),
        "campos_de_leitor": False,
        "erro": resposta["erro"],
        "aviso": "campos de leitor (`users_fields`) não têm reset por HTTP no "
                 "BibLivre 5: o cache só cai com restart do Tomcat",
    }


# --- Backup .b5bz -------------------------------------------------------


def gerar_backup(tipo: str = "full") -> dict:
    """
    Administração → Backup → Full: o `.b5bz` feito pelo próprio BibLivre.

    São duas ações: `prepare` (rápida, devolve o `id`) e `backup` (roda o
    `pg_dump` e só responde no fim). O `prepare` é síncrono aqui — precisamos do
    `id` para responder; o `backup` vai para thread, como o reindex.
    """
    tipo = (tipo or "full").strip().lower()
    if tipo not in TIPOS_BACKUP:
        return {"ok": False, "erro": f"tipo de backup inválido: {tipo!r} "
                                     f"(esperado um de {', '.join(TIPOS_BACKUP)})"}

    with _estado_lock:
        if _backup["rodando"]:
            return {"ok": False,
                    "erro": "já existe um backup em andamento — "
                            "acompanhe por estado_backup()"}

    resposta = _chamar("administration.backup", "prepare", extra={"type": tipo})
    if not resposta["ok"]:
        return {"ok": False, "erro": resposta["erro"]}

    ident = resposta["json"].get("id")
    if ident is None:
        return {"ok": False,
                "erro": "o BibLivre aceitou o prepare mas não devolveu o id do backup"}

    with _estado_lock:
        if _backup["rodando"]:  # corrida entre o prepare e o start
            return {"ok": False, "erro": "já existe um backup em andamento"}
        _backup.update({"rodando": True, "id": ident, "tipo": tipo,
                        "atual": 0, "total": 0, "erro": "",
                        "iniciado_em": _agora(), "terminado_em": ""})

    threading.Thread(target=_rodar_backup, args=(ident,),
                     name="biblivre-backup", daemon=True).start()
    return {"ok": True, "erro": "", "id": ident, "tipo": tipo, "rodando": True}


def _rodar_backup(ident) -> None:
    try:
        resposta = _chamar("administration.backup", "backup",
                           extra={"id": ident}, timeout=TIMEOUT_LONGO)
        erro = "" if resposta["ok"] else resposta["erro"]
    except Exception as e:
        erro = f"falha inesperada no backup: {e}"

    with _estado_lock:
        _backup["rodando"] = False
        _backup["erro"] = erro
        _backup["terminado_em"] = _agora()


def estado_backup() -> dict:
    """
    Andamento do backup e a URL de onde baixar o `.b5bz`.

    O download não passa pelo `controller=json`: é `controller=download`, que
    devolve o zip. Em disco o arquivo fica no destino de backup da instalação,
    com o nome `Biblivre Backup AAAA-MM-DD HHhMMmSSs Full.b5bz`.
    """
    with _estado_lock:
        local = dict(_backup)
    with _lock:
        url_base = _cfg.get("url", "")

    if local["id"] is None:
        return {"rodando": False, "id": None, "atual": 0, "total": 0, "pct": 0,
                "erro": local["erro"], "url_download": "",
                "iniciado_em": "", "terminado_em": local["terminado_em"]}

    resposta = _chamar("administration.backup", "progress",
                       extra={"id": local["id"]})
    if resposta["ok"]:
        atual = int(resposta["json"].get("current") or 0)
        total = int(resposta["json"].get("total") or 0)
        with _estado_lock:
            _backup["atual"], _backup["total"] = atual, total
        erro = local["erro"]
    else:
        atual, total = local["atual"], local["total"]
        erro = local["erro"] or resposta["erro"]

    download = url_base + "?" + urllib.parse.urlencode({
        "controller": "download", "module": "administration.backup",
        "action": "download", "id": local["id"]}) if url_base else ""

    return {"rodando": local["rodando"], "id": local["id"], "tipo": local["tipo"],
            "atual": atual, "total": total,
            "pct": 0 if not total else min(100, int(atual * 100 / total)),
            "erro": erro, "url_download": download,
            "iniciado_em": local["iniciado_em"],
            "terminado_em": local["terminado_em"]}
