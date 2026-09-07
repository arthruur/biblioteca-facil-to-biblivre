"""
Corpos de requisição, em Pydantic.

Só entram aqui os corpos que o cliente envia — as respostas continuam sendo os
dicts que os módulos de domínio devolvem, porque tipá-las agora congelaria um
contrato que ainda está mudando e não daria nada em troca (a tela já consome
esses dicts). Ver docs/SPEC_UI.md, seção 6.
"""

from pydantic import BaseModel, Field


class ConexaoDb(BaseModel):
    """Credenciais do Postgres do BibLivre. A senha nunca é persistida."""

    senha: str | None = None
    host: str | None = None
    port: int | None = None
    dbname: str | None = None
    user: str | None = None
    schema_: str | None = Field(default=None, alias="schema")

    model_config = {"populate_by_name": True}

    def para_config(self) -> dict:
        dados = self.model_dump(exclude_none=True, by_alias=True)
        return dados


class LoteEntrada(BaseModel):
    isbn: str = ""


class Quantidade(BaseModel):
    quantidade: int | None = None
    exemplares: int | None = None

    def valor(self) -> int:
        return max(1, int(self.quantidade or self.exemplares or 1))


class AcaoEmLote(BaseModel):
    ids: list[str] = []
    acao: str = ""


class OpcoesMigracao(BaseModel):
    """
    As escolhas da tela de migração — todas opcionais, e `None` quer dizer
    "não mexi nisso".

    Os padrões de verdade moram em `biblio.migracao.Opcoes`, que é onde os CLIs
    de `scripts/` também os documentam. Repeti-los aqui daria duas listas para
    manter em sincronia, e a que a tela veria seria a errada.
    """

    acervo: bool | None = None
    leitores: bool | None = None
    circulacao: bool | None = None

    incluir_excluidos: bool | None = None
    prefixo_tombo: str | None = None
    ano_tombo: int | None = None
    biblioteca: str | None = None

    campos_extras: str | None = None
    offset_id: int | None = None
    email_obrigatorio: bool | None = None

    apenas_abertos: bool | None = None
    incluir_movimentacoes_excluidas: bool | None = None
    sem_reservas: bool | None = None
    reservas_desde: int | None = None

    permitir_existentes: bool | None = None


class PedidoMigracao(BaseModel):
    """
    Corpo de `/migracao/conferir` e `/migracao/executar`.

    `confirmado` só é olhado na gravação: é a confirmação explícita que a spec
    exige antes de qualquer escrita no acervo, e a rota recusa sem ela.
    """

    opcoes: OpcoesMigracao | None = None
    db: ConexaoDb | None = None
    confirmado: bool = False

    def opcoes_dict(self) -> dict:
        if self.opcoes is None:
            return {}
        return self.opcoes.model_dump(exclude_none=True)


class PedidoExport(BaseModel):
    """
    `executar=False` só gera os arquivos de conferência; `True` grava no banco.

    Sem `ids`, exporta tudo que está pendente ou revisado. Com `ids`, só o que
    a tela selecionou — é o que faz o rodapé dizer "3 itens (seleção)".
    """

    executar: bool = False
    ids: list[str] | None = None
    db: ConexaoDb | None = None


# --- Circulação, sessão e manutenção (pacote A8) -------------------------
#
# Acrescentados pelo A8: são os corpos das rotas do balcão. Continuam valendo
# as duas regras do topo deste arquivo — só entra o que o cliente ENVIA, e a
# resposta continua sendo o dict que o módulo de domínio devolveu.


class Credenciais(BaseModel):
    """
    Corpo de `POST /api/sessao`: o login do próprio BibLivre.

    A senha em claro morre dentro de `operador.autenticar` (que compara o
    SHA-1 + Base64 e não a guarda). Ela não é logada, não vai para disco e não
    volta na resposta — a resposta leva só o token e quem é o operador.
    """

    usuario: str = ""
    senha: str = ""


class PedidoEmprestimo(BaseModel):
    """
    Corpo de `POST /api/circulacao/emprestimos`.

    Não existe `operador_id` aqui, e isso é de propósito: quem empresta sai da
    sessão (`X-Sessao`), nunca do corpo. Aceitar o operador pelo corpo seria
    deixar qualquer celular do wi-fi gravar empréstimo em nome de outra pessoa
    — exatamente o que a decisão §1.4 do plano existe para impedir.

    `forcar_avisos` é a confirmação explícita do balcão depois de um 409 que
    veio só com avisos (leitor em atraso, multa em aberto, reserva de
    terceiro). Impedimento de verdade não passa nem com ele.
    """

    holding_id: int | None = None
    user_id: int | None = None
    forcar_avisos: bool = False
    previsto_para: str | None = None


class PedidoDevolucao(BaseModel):
    """
    Corpo de `POST /api/circulacao/devolucoes`: o exemplar OU o empréstimo.

    `holding_id` é o caminho do bipe (o livro está na mão de quem atende);
    `lending_id` é o caminho da ficha do leitor. Um dos dois basta — a rota
    recusa quando os dois vêm vazios, porque devolver "alguma coisa" não é
    operação que se adivinhe.
    """

    holding_id: int | None = None
    lending_id: int | None = None


class PedidoRenovacao(BaseModel):
    """Corpo de `POST /api/circulacao/renovacoes`."""

    lending_id: int | None = None


class ConfigBiblivre(BaseModel):
    """
    Corpo de `POST /api/manutencao/biblivre`: URL e admin da instalação.

    Mesma regra da senha do Postgres (`ConexaoDb`): memória, nunca disco,
    nunca de volta na resposta.
    """

    url: str = ""
    usuario: str = ""
    senha: str = ""


class PedidoBackup(BaseModel):
    """Corpo de `POST /api/manutencao/backup`. `full` é o que gera o `.b5bz`."""

    tipo: str = "full"
