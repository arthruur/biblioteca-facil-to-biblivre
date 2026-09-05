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

ESQUELETO DO INTEGRADOR
-----------------------
As assinaturas abaixo são o contrato que as telas e os routers já consomem
(docs/PLANO_AGENTES.html, §4.1). A implementação é do pacote **A3**; mudança de
assinatura passa pelo integrador, porque tem gente codificando contra ela.
"""

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

_FALTA = "biblio.biblivre.emprestimo: pendente (pacote A3 do plano de agentes)"


def resolver(con, codigo: str) -> dict:
    """
    O que o balcão acabou de bipar ou digitar?

    Ordem de tentativa: tombo exato → ISBN (via `acervo`, que casa ISBN-10 com
    ISBN-13) → id/matrícula de leitor. No caminho do ISBN devolve **todos** os
    exemplares da obra com o estado de cada um: é assim que se empresta o livro
    cuja etiqueta nunca foi impressa, que é o caso comum do acervo migrado.

    -> {"tipo": "tombo"|"isbn"|"leitor"|"desconhecido", ...}
    """
    raise NotImplementedError(_FALTA)


def buscar_exemplar(con, holding_id: int) -> dict:
    """Exemplar + obra + empréstimo em aberto, se houver."""
    raise NotImplementedError(_FALTA)


def exemplares_da_obra(con, record_id: int) -> list:
    """Os exemplares de uma obra, com estado — o caminho do ISBN."""
    raise NotImplementedError(_FALTA)


def buscar_leitor(con, user_id: int) -> dict:
    """Ficha do leitor + situação + empréstimos."""
    raise NotImplementedError(_FALTA)


def procurar_leitores(con, busca: str, limite: int = 20) -> list:
    """Busca por nome, no mesmo critério do `UserDAO` (ascii + ilike)."""
    raise NotImplementedError(_FALTA)


def situacao(con, user_id: int) -> dict:
    """-> {"abertos", "atrasados", "multas", "limite", "pode_levar"}"""
    raise NotImplementedError(_FALTA)


def checar(con, holding_id: int, user_id: int) -> dict:
    """
    Este leitor pode levar este exemplar?

    -> {"pode": bool, "impedimentos": [...], "avisos": [...], "previsto_para": "AAAA-MM-DD"}

    Impedimento barra (o router devolve 409); aviso passa com `forcar_avisos`.
    """
    raise NotImplementedError(_FALTA)


def emprestar(con, holding_id: int, user_id: int, operador_id: int,
              previsto_para=None, forcar_avisos: bool = False) -> dict:
    """Grava o empréstimo. Não commita."""
    raise NotImplementedError(_FALTA)


def devolver(con, holding_id: int = None, lending_id: int = None,
             operador_id: int = 1) -> dict:
    """Fecha o empréstimo, calcula atraso e multa. Não commita."""
    raise NotImplementedError(_FALTA)


def renovar(con, lending_id: int, operador_id: int) -> dict:
    """Renova no comportamento do BibLivre (a confirmar no fonte). Não commita."""
    raise NotImplementedError(_FALTA)


def pendencias(con, tipo: str = "atrasados", limite: int = 50) -> dict:
    """O relatório que hoje obriga a abrir o BibLivre: quem está devendo o quê."""
    raise NotImplementedError(_FALTA)
