"""
Quem está no balcão. Sessão em memória, autenticada contra `logins`.

O token volta no corpo e o cliente o reenvia em `X-Sessao`, na mesma mecânica
do `X-Dispositivo` que a captura já usa — cabeçalho porque é identidade de quem
chama, não dado da chamada. A regra de negócio é do `biblio.biblivre.operador`;
aqui só há casca.

Este arquivo também guarda as **peças compartilhadas** pelos três routers do
balcão (sessão, circulação e manutenção): o envelope de erro, o cabeçalho
`X-Sessao` e a transação por requisição. Elas moram aqui, e não num quarto
arquivo, porque o mapa de propriedade do plano (§3) dá ao pacote A8 exatamente
três routers — um arquivo novo ficaria sem dono. `deps.py` seria o lugar
natural, mas é do integrador.

POR QUE A SESSÃO EXISTE
A decisão §1.4 do plano: `created_by` passa a ser o operador de verdade, e sem
isso qualquer celular no wi-fi da biblioteca registraria empréstimo. O token é
opaco, vive só em memória do processo e expira por inatividade — reiniciar o
servidor desloga todo mundo, que é o preço de não persistir credencial.
"""

import traceback

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from biblio.biblivre import conexao, operador

from ..deps import em_thread
from ..schemas import Credenciais

router = APIRouter(prefix="/sessao", tags=["sessao"])


# --- Peças compartilhadas pelos routers do balcão ------------------------

# O cabeçalho de identidade. `default=""` e não `None` para que a rota trate
# "não mandou" e "mandou vazio" do mesmo jeito — os dois são "sem operador".
Sessao = Header(default="", alias="X-Sessao")


def resposta_erro(codigo: str, mensagem: str, status: int, **extra):
    """
    O envelope único de erro da API do balcão.

    Corpo plano de propósito (`{"status","codigo","mensagem",...}`), e não o
    `{"detail": …}` que o `HTTPException` do FastAPI produz: as telas leem
    `dados.mensagem` e `dados.codigo` direto (ver `client.js`), e o vocabulário
    fechado do §4.3 do plano só serve se chegar sempre no mesmo lugar.
    """
    corpo = {"status": "erro", "codigo": codigo, "mensagem": mensagem}
    corpo.update(extra)
    return JSONResponse(corpo, status_code=status)


def sem_operador(mensagem: str = ""):
    """401 do vocabulário fechado — o único motivo de recusa por identidade."""
    return resposta_erro(
        "sem_operador",
        mensagem or "Sessão não identificada ou expirada — entre de novo com o "
                    "login do BibLivre.",
        401)


def quem_e(token: str) -> dict | None:
    """
    O operador por trás do `X-Sessao`, ou `None`.

    Só memória (dicionário protegido por lock no `operador`), então não passa
    por `em_thread`: mandar isto para o threadpool custaria mais que a busca.
    Cada consulta renova o "visto por último" — a expiração é por inatividade,
    e o balcão não pode ser deslogado no meio do expediente por estar lento.
    """
    dados = operador.sessao((token or "").strip())
    return dados["operador"] if dados else None


class SemBanco(RuntimeError):
    """Não deu para abrir a conexão com o Postgres do BibLivre."""


def _transacao(funcao, args: tuple, kwargs: dict):
    """
    Uma transação por requisição: abre, chama, commita, fecha. **Bloqueante.**

    É aqui — e só aqui — que o sistema commita. Os pacotes de domínio não
    commitam de propósito (regra do repositório e §1.3 do plano), o que deixa a
    decisão de gravar num lugar só, junto com a de desfazer.

    Erro de domínio (o dict com `ok: False`) faz ROLLBACK, não commit: uma
    recusa pode ter deixado trava, SAVEPOINT ou até um `UPDATE` no meio do
    caminho, e commitar isso gravaria meia operação. Exceção também desfaz, e a
    conexão fecha sempre — nada de conexão global entre requisições, porque uma
    conexão compartilhada viraria uma transação compartilhada entre dois
    atendimentos ao mesmo tempo.
    """
    try:
        con = conexao.conectar()
    except Exception as e:
        raise SemBanco(str(e)) from e

    try:
        try:
            resultado = funcao(con, *args, **kwargs)
        except Exception:
            con.rollback()
            raise
        if isinstance(resultado, dict) and resultado.get("ok") is False:
            con.rollback()
        else:
            con.commit()
        return resultado
    finally:
        try:
            con.close()
        except Exception:
            pass


async def com_banco(funcao, *args, **kwargs):
    """
    Roda `funcao(con, ...)` numa transação, fora do event loop.

    Tudo que toca banco passa por `em_thread`: o psycopg2 é bloqueante, e
    segurar o event loop trava a tela de todo mundo — inclusive a captura, que
    pela SPEC §7 não pode esperar.
    """
    return await em_thread(_transacao, funcao, args, kwargs)


def _erro_de_banco(e: Exception) -> bool:
    """O Postgres respondeu erro (tabela ausente, sem GRANT, conexão caída)?"""
    try:
        import psycopg2
    except ImportError:  # pragma: no cover - ambiente sem a dependência
        return False
    return isinstance(e, psycopg2.Error)


def falha(e: Exception, oque: str):
    """
    Exceção -> resposta em português. Nunca um 500 com stack para a tela.

    Duas famílias, porque quem está no balcão precisa saber qual é:

      * banco indisponível (sem senha, sem psycopg2, Postgres fora do ar,
        tabela que não existe) -> **503 `sem_banco`**. Não adianta repetir;
        alguém tem de configurar ou levantar o banco.
      * qualquer outra -> **500 `falha_inesperada`**, com uma frase legível e
        o tipo do erro. O traceback vai para o console do servidor, que é onde
        se depura, e não para a resposta, que é onde vaza.
    """
    if isinstance(e, SemBanco):
        return resposta_erro(
            "sem_banco",
            f"Banco do BibLivre indisponível. Não deu para concluir: {oque}. "
            f"Nada foi gravado. {e}", 503)
    if _erro_de_banco(e):
        return resposta_erro(
            "sem_banco",
            f"O Postgres do BibLivre recusou a operação. Não deu para "
            f"concluir: {oque}. Nada foi gravado. {e}".strip(), 503)

    traceback.print_exc()
    return resposta_erro(
        "falha_inesperada",
        f"Falha inesperada ({e.__class__.__name__}). Não deu para concluir: "
        f"{oque}. Nada foi gravado; confira o console do servidor antes de "
        "repetir.", 500)


# --- Rotas ---------------------------------------------------------------


@router.post("", summary="Entra com o login do BibLivre")
async def entrar(dados: Credenciais):
    """
    `{usuario, senha}` -> `{token, operador}`; 401 quando não confere.

    A senha vai direto para `operador.autenticar`, que compara o SHA-1 +
    Base64 do próprio BibLivre e não a guarda em lugar nenhum. Ela não volta na
    resposta, não entra na sessão e não é logada.

    Usuário inexistente e senha errada dão a MESMA resposta, de propósito:
    quem tenta adivinhar não deve descobrir quais logins existem, e a tela não
    ganha nada com o detalhe.

    Erro de banco aqui NÃO vira 401 — mentir "senha errada" quando o Postgres
    caiu mandaria o balcão digitar a senha de novo dez vezes. Vira 503.
    """
    usuario = (dados.usuario or "").strip()
    if not usuario or not (dados.senha or ""):
        return sem_operador("Informe o usuário e a senha do BibLivre.")

    try:
        achado = await com_banco(operador.autenticar, usuario, dados.senha)
    except Exception as e:
        return falha(e, "a entrada no balcão")

    if not achado:
        return sem_operador("Usuário ou senha não conferem.")

    token = operador.abrir_sessao(achado)
    viva = operador.sessao(token)
    return {
        "token": token,
        "operador": viva["operador"],
        "expira_em": viva["expira_em"],
        # Aviso, não impedimento: é o mesmo que o BibLivre mostra a quem entra
        # com a senha pública do instalador. Ninguém consome ainda — mas é a
        # única hora em que dá para saber.
        "senha_padrao": bool(achado.get("senha_padrao")),
    }


@router.get("", summary="A sessão corrente (401 se não houver)")
async def atual(x_sessao: str = Sessao):
    """
    Quem está logado neste token — é o que a tela chama ao abrir para decidir
    entre mostrar o balcão e pedir a senha.

    O token NÃO volta aqui: quem pergunta já o tem, e repeti-lo na resposta só
    aumentaria o número de lugares por onde ele pode vazar (log, cache, print
    de tela).
    """
    dados = operador.sessao((x_sessao or "").strip())
    if not dados:
        return sem_operador()
    return {"operador": dados["operador"], "criada_em": dados["criada_em"],
            "visto_em": dados["visto_em"], "expira_em": dados["expira_em"]}


@router.delete("", summary="Sai")
async def sair(x_sessao: str = Sessao):
    """
    Encerra a sessão. Idempotente e sem 401: token que já morreu não é erro.

    Sair tem de funcionar sempre — recusar a saída de quem já está deslogado
    deixaria a tela presa numa sessão que não existe mais.
    """
    operador.encerrar((x_sessao or "").strip())
    return {"ok": True}
