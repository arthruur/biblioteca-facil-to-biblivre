"""
Carrega um `.env` do repositorio para o ambiente do processo.

Existe porque o `docker compose` le `.env` sozinho e o Python nao — e era isso
que empurrava o desenvolvimento para dentro do container: sem as variaveis
`PG*` no ambiente, a checagem de ISBN ja catalogado fica desligada e todo
livro bipado parece obra nova. Rodar local passava a exigir exportar cinco
variaveis a cada terminal novo, ou passar `--db-senha` em cada comando.

Duas regras que nao podem ser quebradas:

1. **O ambiente ja existente sempre vence.** Se `PGPASSWORD` veio do shell, do
   compose ou de um secret, o `.env` nao sobrescreve. Isso mantem o container
   com o comportamento que ele sempre teve.
2. **Sem dependencia nova.** Um parser de `chave=valor` cabe em 30 linhas, e
   nao vale acrescentar `python-dotenv` ao runtime de uma instalacao de
   biblioteca por causa dele.

E chamado por `conexao.py` no import, antes de montar a configuracao do banco,
para que a API e os CLIs de migracao peguem o mesmo `.env` sem que nenhum deles
precise se lembrar de fazer isso.
"""

import os
from pathlib import Path

# .../packages/biblivre-client/src/biblio/biblivre/ambiente.py -> raiz do repo
_RAIZ_PROVAVEL = Path(__file__).resolve().parents[5]


def _desligado() -> bool:
    """
    `BIBLIO_SEM_ENV=1` ignora o `.env`.

    O teste de fumaca precisa disto: ele promete rodar sem banco e sem rede, e
    um `.env` com a senha do Postgres na maquina do desenvolvedor mudava o
    resultado — a checagem de ISBN ligava sozinha e os casos de "obra nova"
    passavam a bater no acervo real.
    """
    return os.environ.get("BIBLIO_SEM_ENV") == "1"


def _candidatos() -> list[Path]:
    """Onde procurar, em ordem de precedencia."""
    do_ambiente = os.environ.get("BIBLIO_ENV_FILE")
    if do_ambiente:
        return [Path(do_ambiente)]

    # O cwd e as pastas acima cobrem quem roda de dentro de scripts/ ou apps/;
    # a raiz provavel cobre o pacote instalado em modo editavel.
    aqui = Path.cwd().resolve()
    return [p / ".env" for p in (aqui, *list(aqui.parents)[:3])] + [
        _RAIZ_PROVAVEL / ".env"
    ]


def _analisar(linha: str) -> tuple[str, str] | None:
    linha = linha.strip()
    if not linha or linha.startswith("#") or "=" not in linha:
        return None
    # `export PGHOST=...` e valido num .env copiado de um shell script.
    if linha.startswith("export "):
        linha = linha[len("export "):]
    chave, _, valor = linha.partition("=")
    chave = chave.strip()
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1]
    if not chave:
        return None
    return chave, valor


def carregar_env(caminho: str | Path | None = None) -> list[str]:
    """
    Aplica o `.env` ao `os.environ`. Devolve as chaves que foram definidas.

    Idempotente: chamar duas vezes nao muda nada, porque a segunda passada ja
    encontra as variaveis definidas e nao sobrescreve.
    """
    if _desligado():
        return []
    arquivos = [Path(caminho)] if caminho else _candidatos()
    for arquivo in arquivos:
        try:
            if not arquivo.is_file():
                continue
            texto = arquivo.read_text(encoding="utf-8")
        except OSError:
            continue

        definidas = []
        for linha in texto.splitlines():
            par = _analisar(linha)
            if par is None:
                continue
            chave, valor = par
            if chave in os.environ:  # o ambiente existente sempre vence
                continue
            os.environ[chave] = valor
            definidas.append(chave)
        return definidas
    return []


__all__ = ["carregar_env"]
