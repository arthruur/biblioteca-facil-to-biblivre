"""
Balcão: empréstimo, devolução, renovação e consulta.

Casca fina, como todos os routers do projeto: quem sabe a regra é
`biblio.biblivre.emprestimo`, que reproduz o `LendingBO` do BibLivre. Aqui só
se valida a entrada, abre-se a transação, chama-se o domínio e traduz-se
recusa em status HTTP.

TRÊS COISAS QUE NÃO SÃO NEGOCIÁVEIS (e onde elas moram)

  * **este arquivo é quem commita** — uma transação por requisição, em
    `sessao.com_banco`: abre a conexão, chama, `commit()` no sucesso,
    `rollback()` na recusa e em qualquer exceção, fecha sempre;
  * tudo que toca banco passa por `deps.em_thread` (também dentro de
    `com_banco`) — bloquear o event loop travaria a captura, que não espera;
  * o `operador_id` sai da **sessão** (`X-Sessao`), nunca do corpo. É o que faz
    `lendings.created_by` valer alguma coisa (§1.4 do plano). Nenhuma rota
    daqui aceita operador pelo corpo, e o `operador_id=1` que o contrato deixou
    como padrão de `devolver` nunca chega a ser usado.

CONSULTA TAMBÉM PEDE SESSÃO — a decisão, com o motivo
O briefing deixava o GET livre à escolha do router. Todos os GETs daqui exigem
`X-Sessao`, por três razões: (1) a ficha do leitor é dado pessoal — nome,
pendências, multas e o histórico do que a pessoa leu — e a rede é o wi-fi
aberto da biblioteca, o mesmo argumento que fez a §1.4 exigir login para
gravar; (2) as telas já mandam o cabeçalho em toda chamada de circulação e já
tratam 401 derrubando a sessão (`useCirculacao.js`, `TelaBalcaoCirculacao.jsx`),
então exigir não custa nada e o comportamento fica uniforme; (3) é o 401 num
GET barato — a ficha, o laço de atrasados — que faz a tela perceber cedo que a
sessão expirou, em vez de descobrir só quando alguém já está com o livro na
mão. O custo aceito: uma tela pública de consulta ao acervo, se um dia
existir, vai precisar de outra rota (não desta com o cabeçalho removido).
"""

from fastapi import APIRouter

from biblio.biblivre import emprestimo

from ..schemas import PedidoDevolucao, PedidoEmprestimo, PedidoRenovacao
from .sessao import Sessao, com_banco, falha, quem_e, resposta_erro, sem_operador

router = APIRouter(prefix="/circulacao", tags=["circulacao"])


# --- tradução domínio -> HTTP -------------------------------------------

# Estes dois códigos, numa CONSULTA, são "não existe" e não "não pode": o 404
# é o que a tela do celular já espera para dizer "leitor não encontrado"
# (useCirculacao.js). Numa gravação eles continuam 409, porque ali o contrato
# do §4.2 promete 201 ou 409 e a tela lê o corpo do 409 para achar o motivo.
_NAO_ENCONTRADO = ("leitor_nao_encontrado", "exemplar_nao_encontrado")


def _codigos(motivos) -> list:
    """
    `[{"codigo": …, "mensagem": …}]` -> `["codigo", …]`.

    O domínio devolve impedimento e aviso como dicionário (código, frase de
    balcão e às vezes um detalhe); as telas, escritas contra o §4.3, esperam a
    lista de CÓDIGOS — `impedimentos.includes('conflito')`, `impedimentos.map`.
    A tradução é aqui, na costura, e não no pacote: o vocabulário fechado é
    contrato de HTTP. O dicionário inteiro continua indo junto, em
    `impedimentos_detalhe` / `avisos_detalhe`, para quem quiser a frase pronta
    e o detalhe ("reservada por Fulano").
    """
    saida = []
    for motivo in motivos or []:
        codigo = motivo.get("codigo") if isinstance(motivo, dict) else motivo
        if codigo:
            saida.append(str(codigo))
    return saida


def _com_avisos(resultado: dict) -> dict:
    """Normaliza os avisos de uma resposta de sucesso, no mesmo formato do 409."""
    avisos = resultado.get("avisos") or []
    resultado["avisos"] = _codigos(avisos)
    resultado["avisos_detalhe"] = avisos
    return resultado


def _recusa(resultado: dict, consulta: bool = False):
    """
    Erro de domínio -> 409 com o vocabulário fechado do §4.3.

    O corpo é sempre `{status, codigo, mensagem, impedimentos, avisos}`. Duas
    formas chegam aqui e a tela precisa distinguir:

      * impedimento de verdade — `impedimentos` preenchido; barra, e nem
        `forcar_avisos` passa;
      * só avisos — `impedimentos` VAZIO, `avisos` preenchido e
        `confirmavel: true`. É o único caso em que a tela pode oferecer
        "emprestar assim mesmo", e ela tem de dizer o que está ignorando.

    `sem_operador` vira 401 mesmo vindo do domínio: é falta de identidade, não
    impedimento de empréstimo.
    """
    codigo = resultado.get("codigo") or "conflito"
    mensagem = resultado.get("mensagem") or "A operação não pôde ser concluída."

    if codigo == "sem_operador":
        return sem_operador(mensagem)

    impedimentos = resultado.get("impedimentos") or []
    avisos = resultado.get("avisos") or []
    extra = {}
    if resultado.get("confirmavel"):
        extra["confirmavel"] = True
    if resultado.get("detalhe"):
        extra["detalhe"] = resultado["detalhe"]

    status = 404 if (consulta and codigo in _NAO_ENCONTRADO) else 409
    return resposta_erro(
        codigo, mensagem, status,
        impedimentos=_codigos(impedimentos), avisos=_codigos(avisos),
        impedimentos_detalhe=impedimentos, avisos_detalhe=avisos, **extra)


def _incompleto(mensagem: str):
    """
    400 para pedido malformado — que não é a mesma coisa que recusa de balcão.

    Fica de fora do vocabulário do §4.3 de propósito: `pedido_incompleto` é
    defeito de quem chamou, não motivo para o leitor não levar o livro, e
    misturar os dois faria a tela mostrar "não pode levar" para um `null` que
    ela mesma mandou.
    """
    return resposta_erro("pedido_incompleto", mensagem, 400)


# --- consulta ------------------------------------------------------------


@router.get("/resolver", summary="Tombo, ISBN ou leitor? Quem decide é o servidor")
async def resolver(codigo: str = "", preferir: str = "",
                   x_sessao: str = Sessao):
    """
    O bipe cru vira `{"tipo": "tombo"|"isbn"|"leitor"|"desconhecido", …}`.

    Quem decide é o servidor, não a tela: só o banco sabe se `2019000123` é
    tombo, matrícula ou nada. Código não reconhecido NÃO é erro HTTP — volta
    200 com `tipo: "desconhecido"`, porque errar a leitura do código de barras
    é rotina no balcão e a tela precisa mostrar "não reconheci isto" sem
    tratar como falha.

    `preferir` (`leitor` | `exemplar`) é o que a tela espera agora: o tombo
    do acervo migrado é o NUMACERVO, só dígitos, e "842" pode ser exemplar ou
    leitor.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    if preferir not in ("", "leitor", "exemplar"):
        return _incompleto("preferir é 'leitor' ou 'exemplar'.")
    try:
        return await com_banco(emprestimo.resolver, codigo, preferir)
    except Exception as e:
        return falha(e, "a leitura do código")


@router.get("/leitores", summary="Busca de leitor por nome")
async def leitores(busca: str = "", limite: int = 20, x_sessao: str = Sessao):
    """
    Mesmo critério do `UserDAO.search`: sem acento, `ILIKE`, inativo escondido.

    Busca vazia devolve lista vazia (200), não erro: é o estado inicial do
    campo de busca da tela do PC.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        achados = await com_banco(emprestimo.procurar_leitores, busca, limite)
    except Exception as e:
        return falha(e, "a busca de leitores")
    return {"leitores": achados, "total": len(achados), "busca": busca}


@router.get("/obras", summary="Busca de obra por título, com os exemplares")
async def obras(busca: str = "", limite: int = 20, x_sessao: str = Sessao):
    """
    O caminho do livro sem etiqueta e sem ISBN: parte do título (ou do autor)
    devolve as obras e, em cada uma, os exemplares com o estado — a mesma lista
    que o caminho do ISBN mostra. Busca vazia é lista vazia (200).
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        achados = await com_banco(emprestimo.procurar_obras, busca, limite)
    except Exception as e:
        return falha(e, "a busca de obras")
    return {"obras": achados, "total": len(achados), "busca": busca}


@router.get("/leitor/{user_id}", summary="Ficha, situação e empréstimos do leitor")
async def leitor(user_id: int, x_sessao: str = Sessao):
    """`{leitor, situacao, emprestimos}` — 404 quando o cadastro não existe."""
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        achado = await com_banco(emprestimo.buscar_leitor, user_id)
    except Exception as e:
        return falha(e, "a leitura da ficha do leitor")
    if not achado.get("ok"):
        return _recusa(achado, consulta=True)
    return achado


@router.get("/exemplar/{holding_id}", summary="Exemplar, obra e empréstimo em aberto")
async def exemplar(holding_id: int, x_sessao: str = Sessao):
    """`{exemplar, obra, emprestimo|null}` — 404 quando o tombo não existe."""
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        achado = await com_banco(emprestimo.buscar_exemplar, holding_id)
    except Exception as e:
        return falha(e, "a leitura do exemplar")
    if not achado.get("ok"):
        return _recusa(achado, consulta=True)
    return achado


@router.get("/pendencias", summary="Atrasados e movimento do dia")
async def pendencias(tipo: str = "atrasados", limite: int = 50,
                     x_sessao: str = Sessao):
    """
    `{itens, total}` — o relatório que hoje obriga a abrir o BibLivre.

    `tipo`: `atrasados` (vencidos), `hoje` (vencem hoje) ou `abertos`. A multa
    que vem em cada item é ESTIMATIVA: `lending_fines` só ganha linha na
    devolução.
    """
    if quem_e(x_sessao) is None:
        return sem_operador()
    try:
        achado = await com_banco(emprestimo.pendencias, tipo, limite)
    except Exception as e:
        return falha(e, "a leitura das pendências")
    if not achado.get("ok"):
        return _recusa(achado)
    return achado


# --- gravação ------------------------------------------------------------


@router.post("/emprestimos", status_code=201,
             summary="Empresta (201) ou barra com o motivo (409)")
async def emprestar(dados: PedidoEmprestimo, x_sessao: str = Sessao):
    """
    Grava o empréstimo em nome do operador da sessão.

    O corpo traz exemplar, leitor e a confirmação; o operador **não** vem por
    aqui — ele sai do `X-Sessao` e vai para `lendings.created_by`. Quem estiver
    sem sessão leva 401 e não grava nada.

    `forcar_avisos` só passa por cima de AVISO (leitor em atraso, multa em
    aberto, reserva de terceiro — os três que o `LendingBO` também não barra).
    Impedimento continua barrando, e a tela precisa dizer o que está ignorando.
    """
    operador = quem_e(x_sessao)
    if operador is None:
        return sem_operador()
    if dados.holding_id is None or dados.user_id is None:
        return _incompleto("Informe o exemplar (holding_id) e o leitor "
                           "(user_id) para emprestar.")

    try:
        resultado = await com_banco(
            emprestimo.emprestar, dados.holding_id, dados.user_id,
            operador["id"], previsto_para=dados.previsto_para,
            forcar_avisos=bool(dados.forcar_avisos))
    except Exception as e:
        return falha(e, "o empréstimo")

    if not resultado.get("ok"):
        return _recusa(resultado)
    return _com_avisos(resultado)


@router.post("/devolucoes", summary="Devolve, com multa e reserva pendente")
async def devolver(dados: PedidoDevolucao, x_sessao: str = Sessao):
    """
    Fecha o empréstimo do exemplar (bipe) ou do `lending_id` (ficha do leitor).

    `{devolucao, multa|null, reserva|null, atraso_dias}`. O `operador_id` da
    sessão é passado explicitamente: o padrão `1` da assinatura do contrato
    gravaria a multa em nome do admin do instalador, e quem recebeu a devolução
    é informação de balcão.
    """
    operador = quem_e(x_sessao)
    if operador is None:
        return sem_operador()
    if dados.holding_id is None and dados.lending_id is None:
        return _incompleto("Informe o exemplar (holding_id) ou o empréstimo "
                           "(lending_id) para devolver.")

    try:
        resultado = await com_banco(
            emprestimo.devolver, holding_id=dados.holding_id,
            lending_id=dados.lending_id, operador_id=operador["id"])
    except Exception as e:
        return falha(e, "a devolução")

    if not resultado.get("ok"):
        return _recusa(resultado)
    return resultado


@router.post("/renovacoes", summary="Renova um empréstimo em aberto")
async def renovar(dados: PedidoRenovacao, x_sessao: str = Sessao):
    """
    Renova como o `LendingBO.doRenew`: fecha a linha antiga e abre outra, com
    `previous_lending_id` apontando para ela.

    Quirk do BibLivre reproduzido pelo domínio: renovação de livro atrasado
    NÃO gera multa. O atraso volta em `atraso_dias` e como aviso — o balcão
    precisa ver o que está perdoando.
    """
    operador = quem_e(x_sessao)
    if operador is None:
        return sem_operador()
    if dados.lending_id is None:
        return _incompleto("Informe o empréstimo (lending_id) para renovar.")

    try:
        resultado = await com_banco(emprestimo.renovar, dados.lending_id,
                                    operador["id"])
    except Exception as e:
        return falha(e, "a renovação")

    if not resultado.get("ok"):
        return _recusa(resultado)
    return _com_avisos(resultado)
