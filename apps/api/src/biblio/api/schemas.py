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
