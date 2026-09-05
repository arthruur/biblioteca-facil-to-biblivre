"""
O outro canal: HTTP contra o próprio BibLivre, não SQL.

    from biblio.biblivre import web

    web.configurar("http://localhost:8080/Biblivre5/", "admin", "...")
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
`BackupBO`, não formato de intercâmbio) e para derrubar os caches estáticos
(`Translations`/`UserFields`) sem reiniciar o Tomcat.

DUAS COISAS QUE O IMPLEMENTADOR PRECISA RESPEITAR
-------------------------------------------------
  * `reindexar()` **não bloqueia**: 14 mil registros em lotes de 30, com heap de
    256 MB, é chamada longa. Dispara em thread e devolve; quem acompanha é
    `progresso_reindex()`.
  * A senha do admin segue a regra da senha do Postgres: memória, nunca disco,
    nunca de volta em `estado()`.

ESQUELETO DO INTEGRADOR
-----------------------
Contrato em docs/PLANO_AGENTES.html §4.1; implementação é do pacote **A1**,
que também confirma no fonte a rota exata e se o reset de `UserFields` existe —
é o que decide se o restart do Tomcat pode morrer.
"""

_FALTA = "biblio.biblivre.web: pendente (pacote A1 do plano de agentes)"


def configurar(url: str, usuario: str, senha: str) -> dict:
    """URL base da instalação + credencial de admin. Só memória."""
    raise NotImplementedError(_FALTA)


def estado() -> dict:
    """-> {"configurado", "url", "conectado", "erro"} — sem a senha dentro."""
    raise NotImplementedError(_FALTA)


def entrar() -> dict:
    """Login; guarda o cookie de sessão. Sessão expirada tenta uma vez de novo."""
    raise NotImplementedError(_FALTA)


def reindexar(record_type: str = "biblio") -> dict:
    """Dispara o reindex da base bibliográfica. Não bloqueia."""
    raise NotImplementedError(_FALTA)


def progresso_reindex() -> dict:
    """-> {"rodando", "atual", "total", "pct"}"""
    raise NotImplementedError(_FALTA)


def resetar_caches() -> dict:
    """Traduções e campos de usuário, sem reiniciar o Tomcat — se der."""
    raise NotImplementedError(_FALTA)


def gerar_backup(tipo: str = "full") -> dict:
    """Administração → Backup → Full: o `.b5bz` feito pelo próprio BibLivre."""
    raise NotImplementedError(_FALTA)


def estado_backup() -> dict:
    raise NotImplementedError(_FALTA)
