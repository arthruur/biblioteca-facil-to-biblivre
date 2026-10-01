"""
Circulação do dia a dia: emprestar, devolver, renovar e consultar.

    from biblio.biblivre import conexao, emprestimo

    con = conexao.conectar()
    r = emprestimo.emprestar(con, holding_id=42, user_id=317, operador_id=1)
    con.commit()          # quem commita é o chamador, como em todo o pacote

ESTE MÓDULO NÃO É O `circulacao.py`
-----------------------------------
`circulacao.py` é migração: lê o backup do sistema antigo e grava 19 mil
empréstimos de uma vez, com id explícito, preservando a numeração de origem.
Aqui é o balcão — uma operação por vez, com o BibLivre possivelmente aberto na
mesma base no PC ao lado. Duas consequências que valem escrever:

  * os ids saem da **sequence** (`nextval`), nunca de contador nosso;
  * toda gravação trava o exemplar (`SELECT ... FOR UPDATE`) e revalida o
    estado dentro da transação, porque entre ler e clicar o livro pode ter
    saído pela tela do BibLivre.

A REGRA DO PACOTE CONTINUA VALENDO: **nada aqui commita.** Toda função recebe a
conexão e devolve; quem fecha a transação é o router.

O QUE ISTO PRECISA REPRODUZIR
-----------------------------
`LendingBO.doLend`, `LendingBO.checkLending`, `LendingBO.doReturn` e
`LendingFineBO` do BibLivre 5 — condições que barram o empréstimo, prazo por
tipo de usuário, cálculo de multa e o comportamento da renovação. Um empréstimo
gravado aqui tem de ser indistinguível de um feito pela tela do BibLivre: o
`.b5bz` continua sendo a verdade e o BibLivre continua instalado.

Também já verificado e válido aqui: empréstimo em aberto **não** altera
`biblio_holdings.availability` — "emprestado" é derivado de
`lendings.return_date IS NULL` (ver o docstring de `circulacao.py`).

O QUE FOI LIDO NO FONTE (github.com/cleydyr/Biblivre-5, `src/java/biblivre/`)
-----------------------------------------------------------------------------
`circulation/lending/LendingBO.java`
    `checkLending(holding, user)` barra em QUATRO condições, e só nelas:
      1. `UserStatus.BLOCKED` ou `UserStatus.INACTIVE`  -> "blocked_user";
      2. `holding.availability != AVAILABLE`            -> "holding_unavailable";
      3. `isLent(holding)`                              -> "holding_is_lent";
      4. `checkUserLendLimit(user, false)`, que é
         `getCurrentLendingsCount(user) < type.getLendingLimit()`.
    Não há checagem de multa, de atraso nem de reserva de terceiro. Isso não é
    ambiguidade do fonte: é ausência declarada, e está refletido na divisão
    impedimento/aviso abaixo.
    `doLend` monta o prazo com `CalendarUtils.calculateExpectedReturnDate` e,
    depois de gravar, apaga a reserva DO PRÓPRIO leitor para aquela obra
    (`ReservationBO.delete(user.getId(), holding.getRecordId())`) — reproduzido
    em `emprestar`.
    `checkRenew` é `checkLending` menos o `isLent` (o exemplar está emprestado
    justamente para quem renova) e com o limite frouxo: `count <= limite`.
    `doRenew` recalcula o prazo a partir de HOJE, não da data prevista antiga.

`circulation/lending/LendingDAO.java`
    doLend   INSERT INTO lendings (holding_id, user_id, previous_lending_id,
             expected_return_date, created_by) VALUES (?, ?, ?, ?, ?)
             — sem `id` e sem `created`: os dois vêm do DEFAULT (a sequence e o
             `now()`). É exatamente o que fazemos aqui.
    doReturn UPDATE lendings SET return_date = now() WHERE id = ?
    doRenew  doReturn(antigo) + doLend(linha nova) com
             `previous_lending_id` = id do antigo, na mesma transação.
             Ou seja: renovação é LINHA NOVA, não UPDATE de
             `expected_return_date` — e é assim que o recibo do próprio
             BibLivre separa "empréstimos" de "renovações"
             (`previousLendingId != null && > 0`).
    corrente SELECT * FROM lendings WHERE holding_id = ? AND return_date IS null
             ORDER BY id DESC  — o `ORDER BY id DESC` está reproduzido, porque
             base migrada pode ter duas linhas abertas para o mesmo exemplar.

`core/utils/CalendarUtils.java`
    `calculateExpectedReturnDate(schema, hoje, dias)`:
      - `moveByDays(dias)`, NÃO `moveByBusinessDays` (a chamada de dias úteis
        está comentada no fonte). Então são `dias` CORRIDOS;
      - o resultado é empurrado para frente até cair num dia de funcionamento
        (`HolidayHandlerType.FORWARD`);
      - a semana útil vem de `configurations['general.business_days']`, no
        formato do `java.util.Calendar` (1=domingo … 7=sábado). O instalador
        semeia `2,3,4,5,6` no schema `global` = segunda a sexta;
      - `loadHolidays()` está COMENTADO no fonte: nenhum feriado é registrado
        no calendário "BR-BIBL". Feriado, hoje, não entra na conta — só o dia
        da semana. É a resposta à pergunta "feriados entram no prazo?": não.

`administration/usertype` + `users_types` (biblivre_template_4.0.0.sql)
    O prazo e o limite saem do TIPO DO LEITOR:
      `users_types.lending_time_limit` (dias) e `users_types.lending_limit`.
    A instalação semeia id 1 "Leitor" (limite 3, prazo 15 dias, multa 0,00) e
    id 2 "Funcionário" (99, 365 dias, multa 0,00) — e a migração deste
    repositório põe todo mundo no tipo 1 (`leitores.TIPO_LEITOR`).
    Sem tipo, o BibLivre usa limite 1 e prazo 7 dias (o `: 1` e o `: 7` dos
    ternários de `LendingBO`); está reproduzido em `LIMITE_SEM_TIPO` /
    `DIAS_SEM_TIPO`.

`circulation/lending/LendingFineBO.java` + `LendingFineDAO.java`
    multa = `dias de atraso * users_types.fine_value` (valor POR DIA, por
    item), com `calculateLateDays` = diferença em dias CORRIDOS entre
    `expected_return_date` e agora, nunca negativa.
    `createFine` só é chamada por `doReturn` quando o valor é > 0, e grava
    `INSERT INTO lending_fines (user_id, lending_id, fine_value, payment_date,
    created_by)` — `payment_date` fica nulo enquanto a multa não é paga; quem
    quita é `payFine`, com `UPDATE ... SET payment_date = now()`.
    Consequência prática desta instalação: `fine_value` é 0,00 nos dois tipos
    semeados, então NENHUMA multa é gravada até alguém configurar o valor em
    Administração. O módulo calcula certo e simplesmente não insere linha.
    ATENÇÃO, quirk reproduzido: `doRenew` chama o `doReturn` do DAO direto e
    NÃO passa por `LendingFineBO` — renovar um livro atrasado não gera multa
    no BibLivre. Aqui também não gera; em compensação `renovar` devolve
    `atraso_dias` e um aviso, para o balcão ver o que está perdoando.

`circulation/user/UserDAO.java`
    A busca de leitor é `U.name_ascii ilike '%' || <busca sem acento> || '%'`
    com `U.status <> 'inactive'` e `ORDER BY UPPER(U.name)`; busca numérica cai
    em `U.id = ?`. Os filtros da tela dão de graça a definição dos dois avisos:
      multa em aberto -> `lending_fines` com `fine_value > 0 AND payment_date IS NULL`
      em atraso       -> `lendings` com `return_date IS NULL AND expected_return_date < now()`
    `UserDTO.getEnrollment()` é `leftPad(id, 5, "0")`: a "matrícula" impressa na
    carteirinha é o id com zeros à esquerda — por isso `resolver` aceita
    "00317" tanto quanto "317".

`circulation/reservation/ReservationDAO.java`
    Reserva é da OBRA (`reservations.record_id`), não do exemplar, e vale
    enquanto `expires > localtimestamp`.

IMPEDIMENTO vs AVISO, E POR QUÊ
-------------------------------
Impedimento barra (o router devolve 409). Aviso passa com `forcar_avisos=True`
e uma confirmação na tela.

  BARRAM — são exatamente o que `checkLending` recusa, mais os erros de
  identidade e a corrida:
    leitor_nao_encontrado    id que não existe em `users`
    leitor_inativo           `users.status = 'inactive'`
    leitor_bloqueado         `users.status = 'blocked'`
    limite_atingido          abertos >= `users_types.lending_limit`
    exemplar_nao_encontrado  id que não existe em `biblio_holdings`
    exemplar_indisponivel    `availability <> 'available'`
    exemplar_emprestado      já há `lendings` em aberto para ele
    conflito                 a revalidação dentro da transação mudou de
                             resposta (alguém emprestou/devolveu no BibLivre
                             entre a consulta e o clique)

  AVISAM — o BibLivre NÃO barra por nada disto, e barrar deixaria o app mais
  rígido que a tela do PC ao lado: o balcão veria "não pode" e o BibLivre
  emprestaria o mesmo livro no clique seguinte. Como é informação que o
  atendente precisa ver, entra como aviso confirmável:
    leitor_com_atraso        tem outro empréstimo vencido (ou o cadastro está
                             em `pending_issues`, que é o status "com
                             pendências" do BibLivre)
    multa_em_aberto          `lending_fines` não pagas
    reserva_de_outro_leitor  a obra tem reserva viva de outra pessoa — o
                             BibLivre nem consulta isso ao emprestar; é
                             acréscimo nosso, e por isso jamais barra

O que ficou por confirmar contra a instalação real está no relatório do pacote,
não aqui: o valor de `general.business_days` na base da biblioteca, o
`fine_value` dos tipos de usuário, e se `users_types` tem tipos além dos dois
semeados.

ESQUELETO DO INTEGRADOR
-----------------------
As assinaturas abaixo são o contrato que as telas e os routers já consomem
(docs/PLANO_AGENTES.html, §4.1). A implementação é do pacote **A3**; mudança de
assinatura passa pelo integrador, porque tem gente codificando contra ela.
"""

import datetime as _dt
import re
import unicodedata

from . import acervo as _acervo
from . import marc as _marc

# Vocabulário fechado dos motivos que barram ou avisam. A tela traduz cada um
# para uma frase de balcão, então acrescentar código aqui é mudar contrato.
IMPEDIMENTOS = (
    "leitor_nao_encontrado",
    "leitor_inativo",
    "leitor_bloqueado",
    "leitor_com_atraso",
    "limite_atingido",
    "multa_em_aberto",
    "exemplar_nao_encontrado",
    "exemplar_emprestado",
    "exemplar_indisponivel",
    "reserva_de_outro_leitor",
    "conflito",
)

# Dos códigos acima, estes três não barram: o BibLivre empresta assim mesmo
# (ver "IMPEDIMENTO vs AVISO" no topo). Passam com `forcar_avisos=True`.
CODIGOS_AVISO = ("leitor_com_atraso", "multa_em_aberto", "reserva_de_outro_leitor")
CODIGOS_IMPEDIMENTO = tuple(c for c in IMPEDIMENTOS if c not in CODIGOS_AVISO)

# `LendingBO`: sem tipo de usuário, o BibLivre usa limite 1 e prazo 7 dias.
LIMITE_SEM_TIPO = 1
DIAS_SEM_TIPO = 7

# `Constants.CONFIG_BUSINESS_DAYS`. Formato do java.util.Calendar:
# 1=domingo, 2=segunda … 7=sábado. O instalador semeia segunda a sexta.
CHAVE_DIAS_UTEIS = "general.business_days"
DIAS_UTEIS_PADRAO = frozenset({2, 3, 4, 5, 6})

# `UserStatus` (toString em minúsculas).
STATUS_INATIVO = "inactive"
STATUS_BLOQUEADO = "blocked"
STATUS_PENDENCIAS = "pending_issues"

# `HoldingAvailability`: só existem 'available' e 'unavailable'.
DISPONIVEL = "available"

MENSAGENS = {
    "leitor_nao_encontrado": "Leitor não encontrado no cadastro do BibLivre.",
    "leitor_inativo": "Leitor inativo — reative o cadastro no BibLivre antes de emprestar.",
    "leitor_bloqueado": "Leitor bloqueado no BibLivre.",
    "leitor_com_atraso": "Leitor com devolução em atraso.",
    "limite_atingido": "Leitor já está no limite de empréstimos do tipo dele.",
    "multa_em_aberto": "Leitor tem multa em aberto.",
    "exemplar_nao_encontrado": "Exemplar não encontrado — confira o tombo.",
    "exemplar_emprestado": "Exemplar já está emprestado.",
    "exemplar_indisponivel": "Exemplar marcado como indisponível no BibLivre.",
    "reserva_de_outro_leitor": "Esta obra tem reserva de outro leitor.",
    "conflito": "O estado mudou enquanto a operação era feita. Confira e tente de novo.",
    "sem_operador": "Nenhum operador identificado — entre com o login do BibLivre.",
}


# --------------------------------------------------------------- utilidades

def _erro(codigo: str, mensagem: str = "", **extra) -> dict:
    """
    Erro de domínio: dict, nunca exceção crua.

    O router transforma isto num 409 com `codigo` e `mensagem`; a tela mostra a
    mensagem para o atendente sem precisar traduzir código nenhum.
    """
    saida = {"ok": False, "codigo": codigo,
             "mensagem": mensagem or MENSAGENS.get(codigo, codigo)}
    saida.update(extra)
    return saida


def _motivo(codigo: str, detalhe: str = "") -> dict:
    item = {"codigo": codigo, "mensagem": MENSAGENS.get(codigo, codigo)}
    if detalhe:
        item["detalhe"] = detalhe
    return item


def sem_acento(texto: str) -> str:
    """`TextUtils.removeDiacriticals`: NFD sem acentos, sem mexer na caixa."""
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if not unicodedata.combining(c))


def _data(valor):
    """Valor de data vindo do banco -> `datetime.date` (ou None)."""
    if valor is None:
        return None
    if isinstance(valor, _dt.datetime):
        return valor.date()
    if isinstance(valor, _dt.date):
        return valor
    try:
        return _dt.date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        return None


def _iso(valor):
    """Valor de data -> "AAAA-MM-DD" (ou None). É o formato do contrato."""
    d = _data(valor)
    return d.isoformat() if d else None


def _iso_hora(valor):
    """Carimbo completo, para "emprestado em" e "devolvido em"."""
    if valor is None:
        return None
    if isinstance(valor, _dt.datetime):
        return valor.replace(microsecond=0).isoformat(sep=" ")
    return _iso(valor)


def _tentar(cur, sql: str, args=()):
    """
    Consulta que pode não existir nesta base (tabela ausente, permissão) sem
    derrubar a transação inteira.

    No Postgres um erro aborta a transação corrente, e aqui a transação é a
    operação de balcão: um `configurations` inacessível não pode impedir o
    empréstimo. O SAVEPOINT isola a tentativa. Devolve None quando falhou.
    """
    cur.execute("SAVEPOINT emprestimo_tentativa")
    try:
        cur.execute(sql, args)
        linhas = cur.fetchall()
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT emprestimo_tentativa")
        return None
    cur.execute("RELEASE SAVEPOINT emprestimo_tentativa")
    return linhas


# ------------------------------------------------------------------- prazo

def dias_uteis(cur) -> frozenset:
    """
    Dias de funcionamento, na mesma ordem de busca do `Configurations.get`:
    schema da biblioteca e, não achando, o schema `global` (é lá que o
    instalador semeia `general.business_days`).
    """
    for sql in ("SELECT value FROM configurations WHERE key = %s",
                "SELECT value FROM global.configurations WHERE key = %s"):
        linhas = _tentar(cur, sql, (CHAVE_DIAS_UTEIS,))
        if linhas and linhas[0][0] and str(linhas[0][0]).strip():
            dias = {int(n) for n in re.findall(r"\d", str(linhas[0][0]))
                    if 1 <= int(n) <= 7}
            if dias:
                return frozenset(dias)
    return DIAS_UTEIS_PADRAO


def _e_dia_util(dia: _dt.date, uteis) -> bool:
    # isoweekday: 1=segunda … 7=domingo. Calendar: 1=domingo … 7=sábado.
    return ((dia.isoweekday() % 7) + 1) in uteis


def _avancar(dia: _dt.date, uteis) -> _dt.date:
    """Empurra para frente até cair em dia de funcionamento (FORWARD)."""
    for _ in range(14):
        if _e_dia_util(dia, uteis):
            return dia
        dia += _dt.timedelta(days=1)
    return dia          # semana sem nenhum dia útil configurado: não trava


def calcular_prazo(data_base: _dt.date, dias: int, uteis) -> _dt.date:
    """
    `CalendarUtils.calculateExpectedReturnDate`: `dias` CORRIDOS a partir da
    data do empréstimo, empurrados para o próximo dia de funcionamento.

    O `setStartDate` do ObjectLab Kit também normaliza a data inicial com o
    mesmo handler, por isso a base é normalizada antes de somar. Na prática só
    muda alguma coisa se alguém emprestar num dia em que a biblioteca está
    fechada — ponto anotado no relatório para conferir contra a instalação.
    """
    inicio = _avancar(data_base, uteis)
    return _avancar(inicio + _dt.timedelta(days=max(int(dias or 0), 0)), uteis)


def _atraso_em_dias(previsto, referencia: _dt.date = None) -> int:
    """`LendingFineBO.calculateLateDays`: dias corridos, nunca negativo."""
    previsto = _data(previsto)
    if previsto is None:
        return 0
    hoje = referencia or _dt.date.today()
    return max((hoje - previsto).days, 0)


# --------------------------------------------------------- leitura de dados

_COLUNAS_EXEMPLAR = """
    h.id, h.record_id, h.accession_number, h.availability, h.database,
    h.location_d, r.iso2709,
    l.id, l.user_id, l.expected_return_date, l.created, l.previous_lending_id,
    u.name
"""

# `getCurrentLending` ordena por id DESC: base migrada pode ter mais de uma
# linha aberta para o mesmo exemplar, e o BibLivre olha a última.
_SQL_EXEMPLAR = """
SELECT {colunas}
  FROM biblio_holdings h
  LEFT JOIN biblio_records r ON r.id = h.record_id
  LEFT JOIN lendings l ON l.holding_id = h.id AND l.return_date IS NULL
  LEFT JOIN users u ON u.id = l.user_id
 WHERE {filtro}
 ORDER BY l.id DESC
 LIMIT 1
"""


def _titulo_autor(iso2709) -> tuple:
    """Título e autor saem do MARC, não de coluna — não existe coluna."""
    reg = _marc.do_iso2709(iso2709) if iso2709 else None
    if reg is None:
        return "", ""
    titulo = ""
    campo = reg.get("245")
    if campo is not None:
        partes = [campo.get(c) for c in ("a", "n", "b")]
        titulo = " ".join(p.strip() for p in partes if p).strip(" /:,.")
    autor = ""
    campo = reg.get("100")
    if campo is not None:
        autor = (campo.get("a") or "").strip(" ,.")
    return titulo, autor


def _montar_exemplar(linha, hoje: _dt.date = None) -> dict:
    """Uma linha do `_SQL_EXEMPLAR` -> {exemplar, obra, emprestimo}."""
    (hid, record_id, tombo, disponibilidade, base, volume, iso,
     lending_id, luser, previsto, criado, anterior, nome_leitor) = linha
    titulo, autor = _titulo_autor(iso)
    hoje = hoje or _dt.date.today()

    emprestimo = None
    if lending_id is not None:
        atraso = _atraso_em_dias(previsto, hoje)
        emprestimo = {
            "lending_id": lending_id,
            "user_id": luser,
            "leitor": nome_leitor or "",
            "previsto_para": _iso(previsto),
            "emprestado_em": _iso_hora(criado),
            "renovacao": bool(anterior),
            "atraso_dias": atraso,
            "atrasado": atraso > 0,
        }

    return {
        "exemplar": {
            "holding_id": hid,
            "record_id": record_id,
            "tombo": tombo or "",
            "disponibilidade": disponibilidade or "",
            "database": base or "",
            "volume": volume or "",
            "emprestado": emprestimo is not None,
        },
        "obra": {"record_id": record_id, "titulo": titulo, "autor": autor},
        "emprestimo": emprestimo,
    }


def _ler_exemplar(cur, filtro: str, valor):
    cur.execute(_SQL_EXEMPLAR.format(colunas=_COLUNAS_EXEMPLAR, filtro=filtro),
                (valor,))
    linha = cur.fetchone()
    return _montar_exemplar(linha) if linha else None


_SQL_LEITOR = """
SELECT u.id, u.name, u.status, u.type,
       t.name, t.lending_limit, t.lending_time_limit, t.fine_value
  FROM users u
  LEFT JOIN users_types t ON t.id = u.type
 WHERE u.id = %s
"""


def _ler_leitor(cur, user_id):
    cur.execute(_SQL_LEITOR, (user_id,))
    linha = cur.fetchone()
    if not linha:
        return None
    uid, nome, status, tipo, tipo_nome, limite, dias, multa_dia = linha
    return {
        # `id` e `user_id` são o mesmo número. As telas de A6/A7 tentam `id`
        # primeiro; manter os dois evita um `undefined` bobo no balcão.
        "id": uid,
        "user_id": uid,
        "nome": nome or "",
        # `UserDTO.getEnrollment()`: o número da carteirinha é o id com zeros.
        "matricula": str(uid).zfill(5),
        "status": (status or "").strip().lower(),
        "tipo_id": tipo,
        "tipo": tipo_nome or "",
        "limite": int(limite) if limite is not None else LIMITE_SEM_TIPO,
        "dias_prazo": int(dias) if dias is not None else DIAS_SEM_TIPO,
        "multa_por_dia": float(multa_dia or 0.0),
    }


_SQL_ABERTOS = """
SELECT count(*),
       coalesce(sum(CASE WHEN expected_return_date < now() THEN 1 ELSE 0 END), 0)
  FROM lendings
 WHERE user_id = %s AND return_date IS NULL
"""

# Mesma definição do filtro "com multa" de `UserDAO.search`.
_SQL_MULTAS = """
SELECT coalesce(sum(fine_value), 0), count(*)
  FROM lending_fines
 WHERE user_id = %s AND fine_value > 0 AND payment_date IS NULL
"""

_SQL_EMPRESTIMOS_DO_LEITOR = """
SELECT l.id, l.holding_id, l.expected_return_date, l.created,
       l.previous_lending_id, h.accession_number, h.record_id, r.iso2709
  FROM lendings l
  LEFT JOIN biblio_holdings h ON h.id = l.holding_id
  LEFT JOIN biblio_records r ON r.id = h.record_id
 WHERE l.user_id = %s AND l.return_date IS NULL
 ORDER BY l.expected_return_date ASC, l.id ASC
"""

# Reserva é da OBRA e vale enquanto `expires > localtimestamp`
# (ReservationDAO). Diferença deliberada: aceitamos `expires` nulo, que existe
# na base migrada, porque aqui a reserva nunca barra — só avisa.
_SQL_RESERVAS_DE_OUTROS = """
SELECT r.id, r.user_id, u.name, r.expires, r.created
  FROM reservations r
  LEFT JOIN users u ON u.id = r.user_id
 WHERE r.record_id = %s
   AND (r.expires IS NULL OR r.expires > localtimestamp)
   AND r.user_id <> %s
 ORDER BY r.created ASC
 LIMIT 5
"""

_SQL_PROXIMA_RESERVA = """
SELECT r.id, r.user_id, u.name, r.expires
  FROM reservations r
  LEFT JOIN users u ON u.id = r.user_id
 WHERE r.record_id = %s
   AND (r.expires IS NULL OR r.expires > localtimestamp)
 ORDER BY r.created ASC
 LIMIT 1
"""


def _ler_situacao(cur, leitor: dict) -> dict:
    cur.execute(_SQL_ABERTOS, (leitor["user_id"],))
    abertos, atrasados = cur.fetchone()
    linhas = _tentar(cur, _SQL_MULTAS, (leitor["user_id"],))
    valor_multas, qtd_multas = (linhas[0] if linhas else (0, 0))
    status = leitor["status"]
    abertos, atrasados = int(abertos or 0), int(atrasados or 0)
    return {
        "abertos": abertos,
        "atrasados": atrasados,
        "multas": round(float(valor_multas or 0.0), 2),
        "multas_qtd": int(qtd_multas or 0),
        "limite": leitor["limite"],
        "dias_prazo": leitor["dias_prazo"],
        "status": status,
        "pode_levar": (status not in (STATUS_INATIVO, STATUS_BLOQUEADO)
                       and abertos < leitor["limite"]),
    }


def _emprestimos_do_leitor(cur, user_id: int) -> list:
    cur.execute(_SQL_EMPRESTIMOS_DO_LEITOR, (user_id,))
    hoje = _dt.date.today()
    itens = []
    for (lid, hid, previsto, criado, anterior, tombo, record_id, iso) in cur.fetchall():
        titulo, autor = _titulo_autor(iso)
        atraso = _atraso_em_dias(previsto, hoje)
        itens.append({
            "lending_id": lid,
            "holding_id": hid,
            "record_id": record_id,
            "tombo": tombo or "",
            "titulo": titulo,
            "autor": autor,
            "previsto_para": _iso(previsto),
            "emprestado_em": _iso_hora(criado),
            "renovacao": bool(anterior),
            "atraso_dias": atraso,
            "atrasado": atraso > 0,
        })
    return itens


# ------------------------------------------------ o que o balcão acabou de ler

def resolver(con, codigo: str, preferir: str = "") -> dict:
    """
    O que o balcão acabou de bipar ou digitar?

    Ordem de tentativa: tombo exato → ISBN (via `acervo`, que casa ISBN-10 com
    ISBN-13) → id/matrícula de leitor. No caminho do ISBN devolve **todos** os
    exemplares da obra com o estado de cada um: é assim que se empresta o livro
    cuja etiqueta nunca foi impressa, que é o caso comum do acervo migrado.

    O tombo do acervo migrado é o NUMACERVO — só dígitos, como o número do
    leitor —, então "842" digitado à mão pode ser os dois. `preferir` é a tela
    dizendo o que espera naquele momento:

        "leitor"    leitor primeiro (o celular, esperando a carteirinha)
        "exemplar"  a ordem de sempre, sem perguntar pelo leitor
        ""          a ordem de sempre; se o tombo também é número de leitor,
                    a resposta leva `tambem_leitor` para a tela oferecer a
                    ficha (o PC, onde a barra aceita os dois)

    -> {"tipo": "tombo"|"isbn"|"leitor"|"desconhecido", ...}
    """
    bruto = (codigo or "").strip()
    if not bruto:
        return {"tipo": "desconhecido", "codigo": "",
                "mensagem": "Nada foi lido."}

    with con.cursor() as cur:
        user_id = None
        if preferir == "leitor":
            user_id = _leitor_por_codigo(cur, bruto)

        achado = None if user_id is not None else _ler_exemplar(
            cur, "h.accession_number = %s", bruto)
        if achado:
            resposta = {"tipo": "tombo", "codigo": bruto, **achado}
            if not preferir and bruto.isdigit():
                outro = _leitor_por_codigo(cur, bruto)
                if outro is not None:
                    resposta["tambem_leitor"] = {"user_id": outro}
            return resposta

        # ISBN: só faz sentido tentar com 10 ou 13 dígitos, senão qualquer
        # matrícula viraria consulta de acervo.
        digitos = re.sub(r"[^0-9Xx]", "", bruto).upper()
        obra = None
        if len(digitos) in (10, 13):
            obra = _obra_por_isbn(cur, bruto)
        if obra and user_id is None:
            exemplares = _exemplares_da_obra(cur, obra["record_id"])
            return {"tipo": "isbn", "codigo": bruto, "obra": obra,
                    "exemplares": exemplares}

        if user_id is None:
            user_id = _leitor_por_codigo(cur, bruto)

    if user_id is not None:
        ficha = buscar_leitor(con, user_id)
        if ficha.get("ok"):
            return {"tipo": "leitor", "codigo": bruto, **ficha}

    return {"tipo": "desconhecido", "codigo": bruto,
            "mensagem": "Código não bate com tombo, ISBN nem leitor."}


def _obra_por_isbn(cur, isbn: str):
    """
    Obra pelo ISBN, com o índice do `acervo` na frente.

    O `acervo` mantém `{isbn -> registro}` em memória justamente para o scanner
    não pagar uma varredura de 15 mil registros por bipe. Quando ele está frio
    ou desligado (processo sem senha do Postgres), caímos num LIKE sobre o
    `iso2709`: continua sendo varredura, mas o filtro roda no Postgres e volta
    UMA linha, não a tabela inteira para dentro do Python.
    """
    try:
        achado = _acervo.buscar(isbn)
    except Exception:
        achado = None
    if achado and achado.get("record_id"):
        return {"record_id": achado["record_id"],
                "titulo": achado.get("titulo", ""),
                "autor": achado.get("autor", ""),
                "isbn": isbn}

    for variante in sorted(_acervo.variantes(isbn), key=len, reverse=True):
        linhas = _tentar(
            cur,
            "SELECT id, iso2709 FROM biblio_records "
            "WHERE database = 'main' AND iso2709 LIKE %s LIMIT 1",
            ("%" + variante + "%",))
        if linhas:
            rec_id, iso = linhas[0]
            titulo, autor = _titulo_autor(iso)
            return {"record_id": rec_id, "titulo": titulo, "autor": autor,
                    "isbn": isbn}
    return None


def _leitor_por_codigo(cur, bruto: str):
    """
    Leitor por id, por matrícula impressa (id com zeros à esquerda) ou pelo
    campo `registration` que a migração criou em `users_values`.
    """
    if bruto.isdigit():
        cur.execute("SELECT id FROM users WHERE id = %s", (int(bruto),))
        linha = cur.fetchone()          # "00317" e "317" caem no mesmo id
        if linha:
            return linha[0]
    linhas = _tentar(
        cur,
        "SELECT user_id FROM users_values "
        "WHERE key = 'registration' AND value = %s LIMIT 1", (bruto,))
    return linhas[0][0] if linhas else None


# ------------------------------------------------------------------ consulta

def buscar_exemplar(con, holding_id: int) -> dict:
    """Exemplar + obra + empréstimo em aberto, se houver."""
    with con.cursor() as cur:
        achado = _ler_exemplar(cur, "h.id = %s", holding_id)
    if not achado:
        return _erro("exemplar_nao_encontrado",
                     f"Exemplar {holding_id} não existe em biblio_holdings.")
    return {"ok": True, **achado}


_SQL_EXEMPLARES_DA_OBRA = """
SELECT h.id, h.accession_number, h.availability, h.location_d, h.database,
       l.id, l.user_id, l.expected_return_date, u.name
  FROM biblio_holdings h
  LEFT JOIN lendings l ON l.holding_id = h.id AND l.return_date IS NULL
  LEFT JOIN users u ON u.id = l.user_id
 WHERE h.record_id = %s
 ORDER BY h.accession_number ASC, h.id ASC
"""


def _exemplares_da_obra(cur, record_id: int) -> list:
    cur.execute(_SQL_EXEMPLARES_DA_OBRA, (record_id,))
    linhas = cur.fetchall()
    hoje = _dt.date.today()
    itens = []
    for (hid, tombo, disp, volume, base, lid, luser, previsto, nome) in linhas:
        atraso = _atraso_em_dias(previsto, hoje) if lid is not None else 0
        itens.append({
            "holding_id": hid,
            "record_id": record_id,
            "tombo": tombo or "",
            "disponibilidade": disp or "",
            "database": base or "",
            "volume": volume or "",
            "emprestado": lid is not None,
            "disponivel": lid is None and (disp or "") == DISPONIVEL,
            "emprestimo": None if lid is None else {
                "lending_id": lid,
                "user_id": luser,
                "leitor": nome or "",
                "previsto_para": _iso(previsto),
                "atraso_dias": atraso,
                "atrasado": atraso > 0,
            },
        })
    return itens


def exemplares_da_obra(con, record_id: int) -> list:
    """
    Os exemplares de uma obra, com estado — o caminho do ISBN.

    Uma query só, com join: a lista sai pronta para a tela dizer "dos 6
    exemplares, 4 estão na estante".
    """
    with con.cursor() as cur:
        return _exemplares_da_obra(cur, record_id)


def buscar_leitor(con, user_id: int) -> dict:
    """Ficha do leitor + situação + empréstimos."""
    with con.cursor() as cur:
        leitor = _ler_leitor(cur, user_id)
        if leitor is None:
            return _erro("leitor_nao_encontrado",
                         f"Leitor {user_id} não existe em users.")
        estado = _ler_situacao(cur, leitor)
        emprestimos = _emprestimos_do_leitor(cur, leitor["user_id"])
    return {"ok": True, "leitor": leitor, "situacao": estado,
            "emprestimos": emprestimos}


_SQL_PROCURAR_POR_NOME = """
SELECT u.id, u.name, u.status, t.name, t.lending_limit,
       (SELECT count(*) FROM lendings l
         WHERE l.user_id = u.id AND l.return_date IS NULL) AS abertos,
       (SELECT count(*) FROM lendings l
         WHERE l.user_id = u.id AND l.return_date IS NULL
           AND l.expected_return_date < now()) AS atrasados
  FROM users u
  LEFT JOIN users_types t ON t.id = u.type
 WHERE u.status <> %s AND u.name_ascii ILIKE %s
 ORDER BY upper(u.name) ASC
 LIMIT %s
"""

_SQL_PROCURAR_POR_ID = _SQL_PROCURAR_POR_NOME.replace(
    "u.name_ascii ILIKE %s", "u.id = %s")


def procurar_leitores(con, busca: str, limite: int = 20) -> list:
    """
    Busca por nome, no mesmo critério do `UserDAO` (ascii + ilike).

    Reproduz `UserDAO.search`: o termo é normalizado com `removeDiacriticals`,
    casa contra `name_ascii` com `%termo%`, esconde os inativos e ordena por
    `upper(name)`. Termo só de dígitos vira busca por id, como lá.
    """
    termo = (busca or "").strip()
    if not termo:
        return []
    limite = max(1, min(int(limite or 20), 200))

    with con.cursor() as cur:
        if termo.isdigit():
            cur.execute(_SQL_PROCURAR_POR_ID,
                        (STATUS_INATIVO, int(termo), limite))
        else:
            cur.execute(_SQL_PROCURAR_POR_NOME,
                        (STATUS_INATIVO, "%" + sem_acento(termo) + "%", limite))
        linhas = cur.fetchall()

    saida = []
    for (uid, nome, status, tipo, limite_tipo, abertos, atrasados) in linhas:
        teto = int(limite_tipo) if limite_tipo is not None else LIMITE_SEM_TIPO
        abertos = int(abertos or 0)
        saida.append({
            "id": uid,
            "user_id": uid,
            "nome": nome or "",
            "matricula": str(uid).zfill(5),
            "status": (status or "").strip().lower(),
            "tipo": tipo or "",
            "abertos": abertos,
            "atrasados": int(atrasados or 0),
            "limite": teto,
            "pode_levar": abertos < teto,
        })
    return saida


# A busca de obra por título. Não existe coluna de título: ele mora no MARC
# (`iso2709`), e o índice do BibLivre (`biblio_idx_*`) só existe depois de um
# reindex — que é justamente o que falta logo depois de uma carga. Então o
# filtro grosso roda no Postgres, sobre o MARC cru e sem acento, e o fino roda
# aqui, sobre título e autor de verdade.
_ACENTOS = "ÁÀÂÃÄáàâãäÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÕÖóòôõöÚÙÛÜúùûüÇçÑñ"
_SEM_ACENTOS = "AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCcNn"

# Quantas obras o filtro grosso traz para o fino escolher. Uma palavra comum
# ("história") casa com centenas; o teto protege o balcão de trazer o acervo
# inteiro para dentro do Python.
_CANDIDATOS_TITULO = 400

_SQL_PROCURAR_OBRAS = """
SELECT r.id, r.iso2709
  FROM biblio_records r
 WHERE r.database = 'main' AND {filtros}
 ORDER BY r.id
 LIMIT %s
"""


def _normalizar(texto: str) -> str:
    return sem_acento(texto or "").lower()


def procurar_obras(con, busca: str, limite: int = 20) -> list:
    """
    Obras pelo título (ou autor), com os exemplares de cada uma.

    É o caminho do livro que não tem etiqueta legível nem ISBN na capa: o
    operador digita parte do título e escolhe o exemplar que está na mão, como
    no caminho do ISBN. Cada palavra precisa aparecer no título ou no autor,
    em qualquer ordem, sem acento e sem caixa. Título que começa pelo termo vem
    primeiro.

    -> [{record_id, titulo, autor, exemplares: [...], total, disponiveis}]
    """
    palavras = [w for w in _normalizar(busca).split() if len(w) >= 2][:5]
    if not palavras:
        return []
    limite = max(1, min(int(limite or 20), 50))

    filtros = " AND ".join(
        "translate(r.iso2709, %s, %s) ILIKE %s" for _ in palavras)
    args: list = []
    for w in palavras:
        args += [_ACENTOS, _SEM_ACENTOS, f"%{w}%"]
    args.append(_CANDIDATOS_TITULO)

    with con.cursor() as cur:
        cur.execute(_SQL_PROCURAR_OBRAS.format(filtros=filtros), tuple(args))
        candidatos = cur.fetchall()

        termo = " ".join(palavras)
        achados = []
        for rec_id, iso in candidatos:
            titulo, autor = _titulo_autor(iso)
            t, a = _normalizar(titulo), _normalizar(autor)
            if not all(w in t or w in a for w in palavras):
                continue        # a palavra estava em outro campo do MARC
            ordem = (0 if t.startswith(termo)
                     else 1 if all(w in t for w in palavras) else 2)
            achados.append((ordem, t, rec_id, titulo, autor))
        achados.sort()

        saida = []
        for _, _, rec_id, titulo, autor in achados[:limite]:
            exemplares = _exemplares_da_obra(cur, rec_id)
            saida.append({
                "record_id": rec_id,
                "titulo": titulo,
                "autor": autor,
                "exemplares": exemplares,
                "total": len(exemplares),
                "disponiveis": sum(1 for e in exemplares if e["disponivel"]),
            })
    return saida


def situacao(con, user_id: int) -> dict:
    """-> {"abertos", "atrasados", "multas", "limite", "pode_levar"}"""
    with con.cursor() as cur:
        leitor = _ler_leitor(cur, user_id)
        if leitor is None:
            return _erro("leitor_nao_encontrado",
                         f"Leitor {user_id} não existe em users.")
        return {"ok": True, **_ler_situacao(cur, leitor)}


# ---------------------------------------------------------- a regra do balcão

def _analisar(cur, holding_id: int, user_id: int, renovacao: bool = False,
              lending_atual: int = None) -> dict:
    """
    O miolo de `checar`, `emprestar` e `renovar` — um lugar só.

    Faz as leituras (exemplar, leitor, situação, reservas), aplica
    `checkLending` / `checkRenew` e devolve tudo o que as três precisam.
    Chamado de novo DENTRO da transação, depois do FOR UPDATE, é também a
    revalidação: mesma função, dados frescos.
    """
    hoje = _dt.date.today()
    impedimentos, avisos = [], []

    dados = _ler_exemplar(cur, "h.id = %s", holding_id)
    if dados is None:
        return {"exemplar": None, "obra": None, "emprestimo": None,
                "leitor": None, "situacao": None, "previsto_para": None,
                "impedimentos": [_motivo("exemplar_nao_encontrado")],
                "avisos": []}

    exemplar, obra, aberto = dados["exemplar"], dados["obra"], dados["emprestimo"]

    # checkLending 2: o material precisa estar disponível.
    if exemplar["disponibilidade"] != DISPONIVEL:
        impedimentos.append(_motivo(
            "exemplar_indisponivel",
            f"availability = {exemplar['disponibilidade'] or 'vazio'}"))

    # checkLending 3: não pode já estar emprestado. Na renovação o exemplar
    # está emprestado de propósito — o que barra é ser de OUTRO leitor, ou o
    # empréstimo ter sido fechado por baixo (corrida com o BibLivre).
    if renovacao:
        if aberto is None or (lending_atual and aberto["lending_id"] != lending_atual):
            impedimentos.append(_motivo(
                "conflito", "o empréstimo a renovar não está mais em aberto"))
        elif aberto["user_id"] != user_id:
            impedimentos.append(_motivo(
                "exemplar_emprestado",
                f"em nome de {aberto['leitor'] or aberto['user_id']}"))
    elif aberto is not None:
        impedimentos.append(_motivo(
            "exemplar_emprestado",
            f"com {aberto['leitor'] or aberto['user_id']} desde "
            f"{aberto['emprestado_em'] or '?'}"))

    leitor = _ler_leitor(cur, user_id)
    if leitor is None:
        impedimentos.append(_motivo("leitor_nao_encontrado"))
        return {"exemplar": exemplar, "obra": obra, "emprestimo": aberto,
                "leitor": None, "situacao": None, "previsto_para": None,
                "impedimentos": impedimentos, "avisos": avisos}

    estado = _ler_situacao(cur, leitor)

    # checkLending 1: bloqueado ou inativo não leva.
    if leitor["status"] == STATUS_INATIVO:
        impedimentos.append(_motivo("leitor_inativo"))
    elif leitor["status"] == STATUS_BLOQUEADO:
        impedimentos.append(_motivo("leitor_bloqueado"))
    elif leitor["status"] == STATUS_PENDENCIAS:
        # `pending_issues` não barra no BibLivre; o vocabulário fechado não tem
        # código próprio para ele, e é literalmente "com pendências".
        avisos.append(_motivo(
            "leitor_com_atraso",
            "cadastro marcado como 'pendências' (pending_issues) no BibLivre"))

    # checkLending 4 / checkRenew: `count < limite` para emprestar,
    # `count <= limite` para renovar (o item renovado já está na conta).
    limite = leitor["limite"]
    estourou = (estado["abertos"] > limite) if renovacao else (estado["abertos"] >= limite)
    if estourou:
        impedimentos.append(_motivo(
            "limite_atingido",
            f"{estado['abertos']} em aberto, limite {limite} "
            f"({leitor['tipo'] or 'sem tipo'})"))

    # Daqui para baixo: o BibLivre não checa nada disto. Só avisa.
    if estado["atrasados"] > 0:
        avisos.append(_motivo(
            "leitor_com_atraso",
            f"{estado['atrasados']} devolução(ões) vencida(s)"))
    if estado["multas"] > 0:
        avisos.append(_motivo(
            "multa_em_aberto",
            f"R$ {estado['multas']:.2f} em {estado['multas_qtd']} multa(s)"))

    if obra and obra.get("record_id") is not None:
        reservas = _tentar(cur, _SQL_RESERVAS_DE_OUTROS,
                           (obra["record_id"], user_id)) or []
        for (_rid, ruser, rnome, _expira, _criada) in reservas[:1]:
            avisos.append(_motivo("reserva_de_outro_leitor",
                                  f"reservada por {rnome or ruser}"))

    previsto = calcular_prazo(hoje, leitor["dias_prazo"], dias_uteis(cur))

    return {"exemplar": exemplar, "obra": obra, "emprestimo": aberto,
            "leitor": leitor, "situacao": estado,
            "previsto_para": previsto.isoformat(),
            "impedimentos": impedimentos, "avisos": avisos}


def checar(con, holding_id: int, user_id: int) -> dict:
    """
    Este leitor pode levar este exemplar?

    -> {"pode": bool, "impedimentos": [...], "avisos": [...], "previsto_para": "AAAA-MM-DD"}

    Impedimento barra (o router devolve 409); aviso passa com `forcar_avisos`.
    Só leitura, e sem trava de propósito: entre esta resposta e o clique o
    estado pode mudar — quem garante é a revalidação de `emprestar`.
    """
    with con.cursor() as cur:
        analise = _analisar(cur, holding_id, user_id)
    return {
        "ok": True,
        "pode": not analise["impedimentos"],
        "impedimentos": analise["impedimentos"],
        "avisos": analise["avisos"],
        "previsto_para": analise["previsto_para"],
        "exemplar": analise["exemplar"],
        "obra": analise["obra"],
        "leitor": analise["leitor"],
        "situacao": analise["situacao"],
    }


def _travar_exemplar(cur, holding_id: int):
    """
    `SELECT ... FOR UPDATE` no exemplar — a trava que segura a operação.

    Enquanto a transação estiver aberta, ninguém (nem o BibLivre no PC ao lado)
    fecha outra operação sobre este exemplar. A revalidação vem depois, porque
    a linha travada não é a resposta: a resposta é "ainda está emprestado?", e
    ela mora em `lendings`.
    """
    cur.execute("SELECT id, record_id, availability FROM biblio_holdings "
                "WHERE id = %s FOR UPDATE", (holding_id,))
    return cur.fetchone()


_SQL_INSERIR_EMPRESTIMO = """
INSERT INTO lendings (holding_id, user_id, previous_lending_id,
                      expected_return_date, created_by)
VALUES (%s, %s, %s, %s, %s)
RETURNING id, created, expected_return_date
"""

# `ReservationDAO.delete(userId, recordId)`, ipsis litteris: apaga UMA reserva,
# a que expira primeiro — o leitor pode ter reservado mais de uma cópia.
_SQL_APAGAR_RESERVA = """
DELETE FROM reservations WHERE id IN (
    SELECT id FROM reservations
     WHERE user_id = %s AND record_id = %s AND expires > localtimestamp
     ORDER BY expires ASC LIMIT 1)
"""


def emprestar(con, holding_id: int, user_id: int, operador_id: int,
              previsto_para=None, forcar_avisos: bool = False) -> dict:
    """
    Grava o empréstimo. Não commita.

    Sequência: trava o exemplar, REVALIDA tudo dentro da transação, grava com
    id vindo da sequence e `created_by` = operador, e apaga a reserva do
    próprio leitor para aquela obra (é o que `LendingBO.doLend` faz depois de
    gravar).

    `previsto_para` sobrescreve o prazo calculado — é o caso do balcão que
    combina outra data; sem ele vale a regra do tipo de usuário.
    """
    if not operador_id:
        return _erro("sem_operador")

    data_prevista = None
    if previsto_para:
        data_prevista = _data(previsto_para)
        if data_prevista is None:
            return _erro("conflito",
                         f"Data de devolução prevista inválida: {previsto_para!r}. "
                         "Use AAAA-MM-DD.")

    with con.cursor() as cur:
        if _travar_exemplar(cur, holding_id) is None:
            return _erro("exemplar_nao_encontrado",
                         f"Exemplar {holding_id} não existe em biblio_holdings.")

        analise = _analisar(cur, holding_id, user_id)
        if analise["impedimentos"]:
            primeiro = analise["impedimentos"][0]
            return _erro(primeiro["codigo"], primeiro["mensagem"],
                         impedimentos=analise["impedimentos"],
                         avisos=analise["avisos"])

        if analise["avisos"] and not forcar_avisos:
            primeiro = analise["avisos"][0]
            return _erro(primeiro["codigo"], primeiro["mensagem"],
                         impedimentos=[], avisos=analise["avisos"],
                         confirmavel=True)

        prevista = (data_prevista.isoformat() if data_prevista
                    else analise["previsto_para"])

        cur.execute(_SQL_INSERIR_EMPRESTIMO,
                    (holding_id, user_id, None, prevista, operador_id))
        lending_id, criado, gravada = cur.fetchone()

        record_id = analise["exemplar"]["record_id"]
        if record_id is not None:
            _tentar(cur, _SQL_APAGAR_RESERVA, (user_id, record_id))

    return {
        "ok": True,
        "emprestimo": {
            "id": lending_id,
            "lending_id": lending_id,
            "holding_id": holding_id,
            "user_id": user_id,
            "tombo": analise["exemplar"]["tombo"],
            "titulo": analise["obra"]["titulo"] if analise["obra"] else "",
            "autor": analise["obra"]["autor"] if analise["obra"] else "",
            "leitor": analise["leitor"]["nome"],
            "previsto_para": _iso(gravada) or prevista,
            "emprestado_em": _iso_hora(criado),
            "operador_id": operador_id,
            "renovacao": False,
        },
        "avisos": analise["avisos"],
    }


_SQL_FECHAR_EMPRESTIMO = """
UPDATE lendings SET return_date = now()
 WHERE id = %s AND return_date IS NULL
RETURNING return_date, expected_return_date, user_id, holding_id
"""

_SQL_INSERIR_MULTA = """
INSERT INTO lending_fines (user_id, lending_id, fine_value, payment_date,
                           created_by)
VALUES (%s, %s, %s, NULL, %s)
RETURNING id
"""


def devolver(con, holding_id: int = None, lending_id: int = None,
             operador_id: int = 1) -> dict:
    """
    Fecha o empréstimo, calcula atraso e multa. Não commita.

    Aceita o exemplar (`holding_id`, o caminho do bipe) ou o empréstimo
    (`lending_id`, o caminho da ficha do leitor). A multa reproduz
    `LendingFineBO`: dias corridos de atraso × `users_types.fine_value`,
    gravada só quando o valor é maior que zero, com `payment_date` nulo — quem
    dá baixa no pagamento continua sendo a tela do BibLivre.

    O `operador_id=1` do padrão está no contrato, mas quem chama deve passar o
    operador de verdade: é ele que fica em `lending_fines.created_by`.
    """
    if holding_id is None and lending_id is None:
        return _erro("exemplar_nao_encontrado",
                     "Informe o exemplar (holding_id) ou o empréstimo (lending_id).")

    with con.cursor() as cur:
        if holding_id is None:
            cur.execute("SELECT holding_id, return_date FROM lendings WHERE id = %s",
                        (lending_id,))
            linha = cur.fetchone()
            if linha is None:
                return _erro("conflito",
                             f"Empréstimo {lending_id} não existe em lendings.")
            if linha[1] is not None:
                return _erro("conflito", "Este empréstimo já foi devolvido em "
                                         f"{_iso_hora(linha[1])}.")
            holding_id = linha[0]

        if _travar_exemplar(cur, holding_id) is None:
            return _erro("exemplar_nao_encontrado",
                         f"Exemplar {holding_id} não existe em biblio_holdings.")

        # Revalidação dentro da transação: entre a leitura e o clique o
        # BibLivre do PC ao lado pode ter dado baixa neste mesmo empréstimo.
        dados = _ler_exemplar(cur, "h.id = %s", holding_id)
        aberto = dados["emprestimo"] if dados else None
        if aberto is None:
            return _erro("conflito",
                         "Este exemplar não está emprestado (alguém pode ter "
                         "devolvido pelo BibLivre agora há pouco).")
        if lending_id is not None and aberto["lending_id"] != lending_id:
            return _erro("conflito",
                         "O empréstimo em aberto deste exemplar é outro "
                         f"(#{aberto['lending_id']}).")

        lending_id = aberto["lending_id"]
        cur.execute(_SQL_FECHAR_EMPRESTIMO, (lending_id,))
        fechado = cur.fetchone()
        if fechado is None:
            return _erro("conflito",
                         "A devolução não pegou: o empréstimo foi fechado por "
                         "outra tela no meio da operação.")
        devolvido_em, previsto, user_id, _hid = fechado

        leitor = _ler_leitor(cur, user_id)
        atraso = _atraso_em_dias(previsto)
        valor_dia = leitor["multa_por_dia"] if leitor else 0.0
        valor = round(atraso * valor_dia, 2)

        multa = None
        if valor > 0:
            linhas = _tentar(cur, _SQL_INSERIR_MULTA,
                             (user_id, lending_id, valor, operador_id))
            multa = {
                "id": linhas[0][0] if linhas else None,
                "valor": valor,
                "dias": atraso,
                "valor_dia": valor_dia,
                "paga": False,
                "gravada": bool(linhas),
            }

        reserva = None
        record_id = dados["exemplar"]["record_id"]
        if record_id is not None:
            linhas = _tentar(cur, _SQL_PROXIMA_RESERVA, (record_id,))
            if linhas:
                _rid, ruser, rnome, rexpira = linhas[0]
                reserva = {"user_id": ruser, "leitor": rnome or "",
                           "expira_em": _iso(rexpira)}

    return {
        "ok": True,
        "devolucao": {
            "lending_id": lending_id,
            "holding_id": holding_id,
            "user_id": user_id,
            "tombo": dados["exemplar"]["tombo"],
            "titulo": dados["obra"]["titulo"] if dados["obra"] else "",
            "leitor": leitor["nome"] if leitor else "",
            "previsto_para": _iso(previsto),
            "devolvido_em": _iso_hora(devolvido_em),
            "operador_id": operador_id,
        },
        "multa": multa,
        "reserva": reserva,
        "atraso_dias": atraso,
    }


def renovar(con, lending_id: int, operador_id: int) -> dict:
    """
    Renova reproduzindo `LendingBO.doRenew`. Não commita.

    O BibLivre NÃO faz UPDATE de `expected_return_date`: ele fecha o empréstimo
    (`return_date = now()`) e abre uma LINHA NOVA com `previous_lending_id`
    apontando para a anterior — é essa cadeia que o recibo dele usa para
    separar "renovações" de "empréstimos". Reproduzido aqui, inclusive o prazo
    recalculado a partir de HOJE (não da data prevista antiga).

    Quirk do fonte, reproduzido de propósito: renovação não gera multa, mesmo
    atrasada, porque `doRenew` chama o `doReturn` do DAO sem passar por
    `LendingFineBO`. O atraso volta em `atraso_dias` e como aviso, para o
    balcão saber o que está deixando passar.
    """
    if not operador_id:
        return _erro("sem_operador")

    with con.cursor() as cur:
        cur.execute("SELECT holding_id, user_id, return_date, expected_return_date "
                    "FROM lendings WHERE id = %s", (lending_id,))
        linha = cur.fetchone()
        if linha is None:
            return _erro("conflito",
                         f"Empréstimo {lending_id} não existe em lendings.")
        holding_id, user_id, devolvido, previsto_antigo = linha
        if devolvido is not None:
            return _erro("conflito", "Este empréstimo já foi devolvido em "
                                     f"{_iso_hora(devolvido)} — não há o que renovar.")

        if _travar_exemplar(cur, holding_id) is None:
            return _erro("exemplar_nao_encontrado",
                         f"Exemplar {holding_id} não existe em biblio_holdings.")

        analise = _analisar(cur, holding_id, user_id, renovacao=True,
                            lending_atual=lending_id)
        if analise["impedimentos"]:
            primeiro = analise["impedimentos"][0]
            return _erro(primeiro["codigo"], primeiro["mensagem"],
                         impedimentos=analise["impedimentos"],
                         avisos=analise["avisos"])

        atraso = _atraso_em_dias(previsto_antigo)

        cur.execute(_SQL_FECHAR_EMPRESTIMO, (lending_id,))
        if cur.fetchone() is None:
            return _erro("conflito",
                         "A renovação não pegou: o empréstimo foi fechado por "
                         "outra tela no meio da operação.")

        cur.execute(_SQL_INSERIR_EMPRESTIMO,
                    (holding_id, user_id, lending_id,
                     analise["previsto_para"], operador_id))
        novo_id, criado, gravada = cur.fetchone()

    avisos = list(analise["avisos"])
    if atraso > 0:
        avisos.append(_motivo(
            "leitor_com_atraso",
            f"renovado com {atraso} dia(s) de atraso; o BibLivre não cobra "
            "multa em renovação"))

    return {
        "ok": True,
        "emprestimo": {
            "id": novo_id,
            "lending_id": novo_id,
            "anterior_id": lending_id,
            "holding_id": holding_id,
            "user_id": user_id,
            "tombo": analise["exemplar"]["tombo"],
            "titulo": analise["obra"]["titulo"] if analise["obra"] else "",
            "leitor": analise["leitor"]["nome"],
            "previsto_para": _iso(gravada) or analise["previsto_para"],
            "emprestado_em": _iso_hora(criado),
            "operador_id": operador_id,
            "renovacao": True,
        },
        "atraso_dias": atraso,
        "avisos": avisos,
    }


# ---------------------------------------------------------------- pendências

_FILTROS_PENDENCIA = {
    "atrasados": "l.expected_return_date < now()",
    "hoje": "l.expected_return_date::date = current_date",
    "abertos": "TRUE",
}

_SQL_PENDENCIAS = """
SELECT l.id, l.holding_id, l.user_id, l.expected_return_date, l.created,
       l.previous_lending_id, h.accession_number, h.record_id, r.iso2709,
       u.name, coalesce(t.fine_value, 0)
  FROM lendings l
  JOIN biblio_holdings h ON h.id = l.holding_id
  LEFT JOIN biblio_records r ON r.id = h.record_id
  LEFT JOIN users u ON u.id = l.user_id
  LEFT JOIN users_types t ON t.id = u.type
 WHERE l.return_date IS NULL AND {filtro}
 ORDER BY l.expected_return_date ASC, l.id ASC
 LIMIT %s
"""

_SQL_PENDENCIAS_TOTAL = """
SELECT count(*) FROM lendings l
 WHERE l.return_date IS NULL AND {filtro}
"""


def pendencias(con, tipo: str = "atrasados", limite: int = 50) -> dict:
    """
    O relatório que hoje obriga a abrir o BibLivre: quem está devendo o quê.

    `tipo`: "atrasados" (vencidos), "hoje" (vencem hoje) ou "abertos" (tudo em
    aberto). A multa estimada usa a mesma conta da tela do BibLivre
    (`dailyFine * daysLate`) e é ESTIMATIVA: `lending_fines` só ganha linha na
    devolução.
    """
    filtro = _FILTROS_PENDENCIA.get(tipo)
    if filtro is None:
        return _erro("conflito",
                     f"Tipo de pendência desconhecido: {tipo!r}. "
                     f"Use um de {sorted(_FILTROS_PENDENCIA)}.")
    limite = max(1, min(int(limite or 50), 500))
    hoje = _dt.date.today()

    with con.cursor() as cur:
        cur.execute(_SQL_PENDENCIAS_TOTAL.format(filtro=filtro))
        (total,) = cur.fetchone()
        cur.execute(_SQL_PENDENCIAS.format(filtro=filtro), (limite,))
        linhas = cur.fetchall()

    itens = []
    for (lid, hid, uid, previsto, criado, anterior, tombo, record_id, iso,
         nome, multa_dia) in linhas:
        titulo, autor = _titulo_autor(iso)
        atraso = _atraso_em_dias(previsto, hoje)
        itens.append({
            "lending_id": lid,
            "holding_id": hid,
            "record_id": record_id,
            "tombo": tombo or "",
            "titulo": titulo,
            "autor": autor,
            "user_id": uid,
            "leitor": nome or "",
            "matricula": str(uid).zfill(5) if uid is not None else "",
            "previsto_para": _iso(previsto),
            "emprestado_em": _iso_hora(criado),
            "renovacao": bool(anterior),
            "atraso_dias": atraso,
            "atrasado": atraso > 0,
            "multa_estimada": round(atraso * float(multa_dia or 0.0), 2),
        })

    return {"ok": True, "tipo": tipo, "itens": itens,
            "total": int(total or 0), "limite": limite,
            "exibidos": len(itens)}
