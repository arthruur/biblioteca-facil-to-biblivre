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


class PedidoExport(BaseModel):
    """
    `executar=False` só gera os arquivos de conferência; `True` grava no banco.

    Sem `ids`, exporta tudo que está pendente ou revisado. Com `ids`, só o que
    a tela selecionou — é o que faz o rodapé dizer "3 itens (seleção)".
    """

    executar: bool = False
    ids: list[str] | None = None
    db: ConexaoDb | None = None
