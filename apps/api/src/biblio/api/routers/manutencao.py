"""
Os passos que sobravam fora do app: reindexar, caches, conferência, backup.

Casca fina sobre dois pacotes: `biblio.biblivre.web` (que fala HTTP com o
BibLivre instalado, logado como admin) e `biblio.biblivre.verificacao` (que
confere a base com SQL puro, só leitura).

DUAS REGRAS QUE ESTE ARQUIVO NÃO PODE PERDER DE VISTA

  * reindex e backup **disparam e voltam**; o progresso é rota separada. São
    minutos de trabalho do lado do Tomcat — `IndexingBO.reindex` varre a
    `biblio_records` em lotes de 30 e só responde no fim, e o backup roda um
    `pg_dump`. A tela precisa de barra de progresso, não de requisição
    pendurada. Quem segura a espera é a thread interna do pacote `web`;
  * a senha do admin do BibLivre segue a regra da senha do Postgres: entra em
    memória, nunca vai para disco e **nunca volta na resposta** — `web.estado()`
    devolve URL e estado de conexão, e nada mais.

TUDO AQUI PEDE SESSÃO
Inclusive os GETs. Estas rotas disparam trabalho pesado na instalação inteira
(um reindex derruba os índices antes de reconstruir; um backup produz um
`.b5bz` com nome, CPF e endereço de todos os leitores, com URL de download) e
guardam a credencial de administrador. Deixar isso aberto na LAN da biblioteca
seria pior do que qualquer incômodo de ter de entrar antes. O efeito colateral
aceito, e que o integrador precisa saber: sem Postgres de pé não há login, e
sem login não há como disparar reindex nem backup pela API — o caminho de
socorro continua sendo a tela do próprio BibLivre.
"""

from fastapi import APIRouter

from biblio.biblivre import verificacao, web

from ..deps import em_thread
from ..schemas import ConfigBiblivre, PedidoBackup
from .sessao import Sessao, com_banco, falha, quem_e, resposta_erro, sem_operador

router = APIRouter(prefix="/manutencao", tags=["manutencao"])


# --- tradução domínio -> HTTP -------------------------------------------

# A frase que o pacote `web` usa quando ainda não há URL nem credencial. Ela é
# privada lá dentro, e por isso vem com `getattr` e um padrão: se o pacote
# mudar a frase, o pior que acontece é o código do erro virar
# `biblivre_indisponivel` em vez de `biblivre_nao_configurado` — nenhuma rota
# quebra por causa disso.
_SEM_CONFIG = getattr(web, "_ERRO_SEM_CONFIG", "não configurado")


def _recusa(resultado: dict, oque: str):
    """
    Falha do lado do BibLivre -> 409 com motivo legível.

    Dois códigos, e nenhum deles pertence ao vocabulário do §4.3 (que é sobre
    empréstimo, não sobre manutenção) — estão documentados aqui e no relatório
    do pacote:

      * `biblivre_nao_configurado` — falta URL ou credencial de admin. É a
        primeira coisa a fazer na tela de manutenção;
      * `biblivre_indisponivel` — está configurado, mas o Tomcat não respondeu,
        recusou o login ou negou a ação.

    Os dois são 409 (e não 502) para manter a regra única da API do balcão:
    200 quer dizer "foi"; 409 quer dizer "não foi, e a `mensagem` explica em
    português".
    """
    erro = (resultado.get("erro") or "").strip()
    configurado = _SEM_CONFIG not in erro
    codigo = "biblivre_indisponivel" if configurado else "biblivre_nao_configurado"
    return resposta_erro(codigo, f"{oque} não foi possível: "
                                 f"{erro or 'o BibLivre não respondeu'}", 409)


def _panorama() -> dict:
    """
    O estado das três frentes numa passada só. **Bloqueante.**

    Feito numa função só, e não em três `em_thread`, porque as três consultam o
    mesmo Tomcat: uma ida ao threadpool em vez de três, e a resposta sai
    coerente entre si. Sem configuração nenhuma as três voltam na hora, sem
    tocar a rede (o pacote `web` corta antes de abrir socket).
    """
    return {"biblivre": web.estado(),
            "reindex": web.progresso_reindex(),
            "backup": web.estado_backup()}


# --- estado --------------------------------------------------------------


@router.get("", summary="Estado: BibLivre configurado, reindex, backup")
async def estado(x_sessao: str = Sessao):
    """
    `{biblivre:{configurado,url,conectado}, reindex:{…}, backup:{…}}`.

    `conectado` é sonda de verdade (uma chamada autenticada ao BibLivre), com
    cache curto dentro do pacote porque a tela pergunta em laço. Nunca devolve
    a senha do admin.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        return await em_thread(_panorama)
    except Exception as e:
        return falha(e, "a leitura do estado da manutenção")


@router.post("/biblivre", summary="URL e credencial de admin do BibLivre")
async def configurar_biblivre(dados: ConfigBiblivre, x_sessao: str = Sessao):
    """
    Guarda URL e credencial em memória e testa na hora.

    A resposta é o `estado()` do pacote — `{configurado, url, conectado, erro}`,
    sem a senha. `configurado: true` com `conectado: false` é resposta útil e
    não erro: quer dizer "anotei, mas o Tomcat não respondeu agora", e é
    exatamente o que a tela precisa mostrar para quem digitou a URL errada.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        return await em_thread(web.configurar, dados.url, dados.usuario,
                               dados.senha)
    except Exception as e:
        return falha(e, "a configuração do BibLivre")


# --- reindexação ---------------------------------------------------------


@router.post("/reindexar", summary="Dispara o reindex da base bibliográfica")
async def reindexar(x_sessao: str = Sessao):
    """
    Dispara e volta na hora: `{iniciado: true}`. O progresso é o GET desta rota.

    Uma por vez — o BibLivre tem lock por tipo de registro e faria a segunda
    chamada voltar calada, sem indexar nada, o que pareceria sucesso. Aqui a
    segunda chamada leva 409 com o motivo.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        resultado = await em_thread(web.reindexar)
    except Exception as e:
        return falha(e, "o disparo da reindexação")
    if not resultado.get("ok"):
        return _recusa(resultado, "Reindexar")
    return {"iniciado": True, **resultado}


@router.get("/reindexar", summary="Progresso do reindex")
async def progresso_reindex(x_sessao: str = Sessao):
    """
    `{rodando, atual, total, pct}` — para o laço da barra de progresso.

    Nunca devolve 409: falha de consulta volta como `erro` dentro do corpo, com
    o último valor conhecido. Perder um polling não pode apagar o estado da
    tela nem parecer que a reindexação morreu.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        return await em_thread(web.progresso_reindex)
    except Exception as e:
        return falha(e, "a leitura do progresso da reindexação")


# --- caches e conferência ------------------------------------------------


@router.post("/caches", summary="Derruba os caches estáticos sem reiniciar o Tomcat")
async def caches(x_sessao: str = Sessao):
    """
    `{ok, detalhe}` — traduções sim, campos de leitor não, e a resposta diz.

    Não existe reset de `users_fields` por HTTP no BibLivre 5: os únicos
    caminhos até `StaticBO.resetCache()` são destrutivos (restore, importação,
    remoção de schema). Campo de leitor criado por SQL continua exigindo
    restart do Tomcat, e o `aviso` da resposta existe para que ninguém fique
    esperando o contrário.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        resultado = await em_thread(web.resetar_caches)
    except Exception as e:
        return falha(e, "a limpeza dos caches")
    if not resultado.get("ok"):
        return _recusa(resultado, "Limpar os caches")
    return {"detalhe": resultado.get("aviso", ""), **resultado}


@router.post("/conferencia", summary="Conferência pós-carga (só leitura)")
async def conferencia(x_sessao: str = Sessao):
    """
    `{checagens: [...], resumo}` — a conferência do §A2, contra o Postgres.

    É a única rota de manutenção que fala com o banco em vez do Tomcat, e é só
    leitura: checagem que não pôde rodar (tabela ausente, sem GRANT) volta com
    `ok: null` e o motivo, sem derrubar as outras. É POST, e não GET, porque
    custa uma dezena de varreduras na base inteira — não é coisa para laço de
    tela.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        return await com_banco(verificacao.conferir)
    except Exception as e:
        return falha(e, "a conferência da base")


# --- backup --------------------------------------------------------------


@router.post("/backup", summary="Gera o .b5bz pelo próprio BibLivre")
async def backup(dados: PedidoBackup | None = None, x_sessao: str = Sessao):
    """
    Dispara o backup e volta na hora: `{iniciado: true, id}`.

    Quem gera é o próprio BibLivre (`administration.backup`), e não nós: o
    `.b5bz` continua sendo a verdade da biblioteca, e um formato reimplementado
    por fora seria um restore que ninguém testou. O corpo pode vir vazio — o
    padrão é `full`, que é o que se quer antes de mexer na base.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    dados = dados or PedidoBackup()
    try:
        resultado = await em_thread(web.gerar_backup, dados.tipo)
    except Exception as e:
        return falha(e, "o disparo do backup")
    if not resultado.get("ok"):
        return _recusa(resultado, "Gerar o backup")
    return {"iniciado": True, **resultado}


@router.get("/backup", summary="Estado do backup")
async def estado_backup(x_sessao: str = Sessao):
    """
    `{rodando, arquivo, criado_em}` e a URL de download do `.b5bz`.

    Como o progresso do reindex, nunca 409: erro de consulta volta dentro do
    corpo, com o último valor conhecido.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        return await em_thread(web.estado_backup)
    except Exception as e:
        return falha(e, "a leitura do estado do backup")
