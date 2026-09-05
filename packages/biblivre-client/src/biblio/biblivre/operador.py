"""
Quem está no balcão: autenticação contra a tabela `logins` do BibLivre.

    from biblio.biblivre import conexao, operador

    con = conexao.conectar()
    quem = operador.autenticar(con, "bibliotecaria", "...")
    token = operador.abrir_sessao(quem)     # vive em memória, some no restart

POR QUE ISTO PASSOU A EXISTIR
-----------------------------
O app não tinha login, e não precisava: ele catalogava, e catálogo errado se
conserta. Registrar empréstimo muda duas coisas.

  * `lendings.created_by` precisa dizer **quem** emprestou. A migração grava
    `1` (o admin do instalador, ver `conexao.USUARIO_PADRAO`), e para o dia a
    dia isso é perder informação de balcão.
  * Sem barreira nenhuma, qualquer celular na rede da biblioteca registra
    empréstimo em nome de qualquer leitor.

A saída é não inventar cadastro: o BibLivre já tem `logins`. Autenticar contra
ela dá o `logins.id` verdadeiro — o `created_by` passa a fazer sentido dentro
do próprio BibLivre — e é uma senha a menos para a biblioteca administrar.

ESQUELETO DO INTEGRADOR
-----------------------
Contrato em docs/PLANO_AGENTES.html §4.1; implementação é do pacote **A4**.
A sessão vive em memória, com expiração por inatividade, pela mesma razão que a
senha do Postgres nunca vai para disco (ver `conexao.py`).
"""

_FALTA = "biblio.biblivre.operador: pendente (pacote A4 do plano de agentes)"


def hash_senha(senha: str) -> str:
    """
    O mesmo hash que o BibLivre grava em `logins.password` (SHA-1 + Base64).

    Prova barata da implementação inteira: o par do instalador
    (`admin` / `abracadabra`) tem de bater com o hash do SQL de criação.
    """
    raise NotImplementedError(_FALTA)


def autenticar(con, usuario: str, senha: str) -> dict | None:
    """-> {"id", "login", "nome"} ou None. Não diga qual metade falhou."""
    raise NotImplementedError(_FALTA)


def abrir_sessao(operador: dict) -> str:
    """Token opaco. Reiniciar o servidor desloga todo mundo, e tudo bem."""
    raise NotImplementedError(_FALTA)


def sessao(token: str) -> dict | None:
    """A sessão, renovando o 'visto por último'. None se expirou ou não existe."""
    raise NotImplementedError(_FALTA)


def encerrar(token: str) -> None:
    raise NotImplementedError(_FALTA)


def ativas() -> list:
    """Quem está no balcão agora — para a tela do PC."""
    raise NotImplementedError(_FALTA)
