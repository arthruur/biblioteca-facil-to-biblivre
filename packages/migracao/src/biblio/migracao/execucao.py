"""
A execução de migração: uma por vez, em segundo plano, com estado consultável.

POR QUE EM SEGUNDO PLANO
------------------------
Uma migração real são ~14 mil obras, ~16 mil exemplares, ~2,7 mil leitores e
~19 mil empréstimos. A consolidação com pandas e a geração do MARC levam
dezenas de segundos; a transação leva mais. Uma requisição HTTP segurando isso
morreria no timeout do navegador com a transação aberta do outro lado — e a
tela não teria como dizer em que passo está. Então o POST devolve na hora, o
trabalho corre numa thread e a tela busca `estado()` em laço, do mesmo jeito
que o painel de lotes busca `versao()` (ver `biblio.catalogacao.lotes`).

POR QUE UMA SÓ
--------------
Duas migrações simultâneas gravariam ids sobrepostos na mesma base. Não é um
caso a suportar: é um caso a recusar, com mensagem clara, antes de começar.

POR QUE PERSISTIDA
------------------
O relatório é o que a pessoa lê para decidir gravar, e a gravação é
irreversível pela tela. Um F5 no meio, ou um restart do uvicorn em
desenvolvimento, não pode apagar o que foi conferido — o estado mora em
`data/migracao/<id>/estado.json` e volta na subida do processo, como a fila.

Se o processo cair *durante* a gravação, a execução volta como erro dizendo
exatamente isso: ninguém aqui sabe se a transação chegou a commitar, e fingir
que sabe seria pior do que mandar conferir as contagens no BibLivre.
"""

import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from biblio.biblivre import conexao
from biblio.catalogacao.config import DATA_DIR

from . import pipeline
from .pipeline import Opcoes

MIGRACAO_DIR = DATA_DIR / "migracao"
ARQ_ESTADO = "estado.json"
ARQ_BACKUP = "backup.bkp"

# 500 MB. O maior `.bkp` visto em campo tem alguns megabytes; o limite não
# existe para acomodar backup grande, e sim para um upload errado (um vídeo,
# um `.b5bz`) parar antes de encher o disco da biblioteca.
LIMITE_UPLOAD = 500 * 1024 * 1024

# Os passos que a tela desenha, na ordem em que acontecem. Chave igual à que o
# `pipeline` manda no callback de progresso — é o que liga um ao outro.
PASSOS_CONFERENCIA = [
    ("consolidar", "Consolidar o acervo", "acervo"),
    ("marc", "Gerar o MARC21 e os exemplares", "acervo"),
    ("leitores", "Montar os leitores", "leitores"),
    ("circulacao", "Casar a circulação", "circulacao"),
    ("destino", "Conferir o BibLivre", None),
]
PASSOS_GRAVACAO = [
    ("obras", "Gravar os registros bibliográficos", "acervo"),
    ("exemplares", "Criar os exemplares e emitir os tombos", "acervo"),
    ("leitores", "Gravar os leitores", "leitores"),
    ("circulacao", "Gravar empréstimos, multas e reservas", "circulacao"),
    ("commit", "Fechar a transação", None),
]

_lock = threading.RLock()
_estado: dict | None = None
_thread: threading.Thread | None = None


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------- leitura

def estado() -> dict:
    """O estado corrente, sempre com `versao` — é o que a tela busca em laço."""
    with _lock:
        if _estado is None:
            return {"fase": "vazio", "versao": 0, "ocupado": False}
        atual = json.loads(json.dumps(_estado, ensure_ascii=False))
    atual["ocupado"] = ocupado()
    atual["artefatos"] = _artefatos(Path(atual["pasta"]))
    return atual


def versao() -> int:
    with _lock:
        return 0 if _estado is None else _estado["versao"]


def ocupado() -> bool:
    return _thread is not None and _thread.is_alive()


def _artefatos(pasta: Path) -> list[dict]:
    """Os arquivos de conferência que a execução deixou, para download."""
    if not pasta.is_dir():
        return []
    nomes = (pipeline.CONSOLIDADO, pipeline.ARQ_MRC, pipeline.ARQ_EXEMPLARES,
             pipeline.MAPA_EXEMPLARES, pipeline.MAPA_LEITORES)
    return [{"nome": n, "bytes": (pasta / n).stat().st_size}
            for n in nomes if (pasta / n).exists()]


def caminho_de_artefato(nome: str) -> Path:
    """
    Resolve um nome de artefato para um caminho dentro da execução corrente.

    A lista é branca de propósito: o parâmetro vem da URL, e "só sanitizar o
    nome" é como se escreve um path traversal sem perceber. O `.bkp` enviado
    não entra — ele já está na máquina de quem o enviou, e devolvê-lo só
    aumentaria a superfície de dado pessoal trafegando.
    """
    with _lock:
        if _estado is None:
            raise FileNotFoundError("Não há execução de migração.")
        pasta = Path(_estado["pasta"])
    permitidos = {a["nome"] for a in _artefatos(pasta)}
    if nome not in permitidos:
        raise FileNotFoundError(f"{nome} não é um arquivo desta execução.")
    return pasta / nome


# ------------------------------------------------------------- mutação

def _mudou(**campos) -> dict:
    """Aplica mudanças no estado, sobe a versão e persiste. Requer `_lock`."""
    global _estado
    if _estado is None:
        raise RuntimeError("Não há execução de migração.")
    _estado.update(campos)
    _estado["versao"] += 1
    _estado["atualizado_em"] = _agora()
    _salvar()
    return _estado


def _salvar() -> None:
    """Requer `_lock`. Falha de disco não pode derrubar a execução em curso."""
    try:
        pasta = Path(_estado["pasta"])
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / ARQ_ESTADO).write_text(
            json.dumps(_estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _passos(modelo, opcoes: Opcoes) -> list[dict]:
    return [{"chave": chave, "rotulo": rotulo, "status": "pendente",
             "detalhe": ""}
            for chave, rotulo, etapa in modelo
            if etapa is None or getattr(opcoes, etapa)]


def _marcar(chave: str, detalhe: str = "") -> None:
    """
    Fecha o passo que estava rodando e abre este. É o callback do pipeline.

    Fechar o anterior aqui (em vez de o pipeline avisar duas vezes) é o que
    mantém `pipeline` sem saber que existe uma tela do outro lado.
    """
    with _lock:
        if _estado is None:
            return
        for passo in _estado["passos"]:
            if passo["status"] == "rodando":
                passo["status"] = "ok"
            if passo["chave"] == chave:
                passo["status"] = "rodando"
                passo["detalhe"] = detalhe
        _mudou()


def _fechar_passos(status_restante: str) -> None:
    with _lock:
        if _estado is None:
            return
        for passo in _estado["passos"]:
            if passo["status"] == "rodando":
                passo["status"] = "ok"
            elif passo["status"] == "pendente":
                passo["status"] = status_restante


# ------------------------------------------------------- ciclo de vida

def iniciar(nome_arquivo: str, conteudo: bytes) -> dict:
    """
    Recebe o `.bkp`, cria a execução e extrai as tabelas.

    Bloqueante de propósito: a extração é zlib de alguns megabytes e a tela
    precisa do inventário para mostrar o que veio dentro antes de perguntar
    qualquer coisa. Quem chama roda isto fora do event loop.
    """
    global _estado
    if ocupado():
        raise RuntimeError("Já existe uma migração em andamento.")
    if not conteudo:
        raise ValueError("Arquivo vazio.")
    if len(conteudo) > LIMITE_UPLOAD:
        raise ValueError(
            f"Arquivo de {len(conteudo) / 1048576:.0f} MB acima do limite de "
            f"{LIMITE_UPLOAD // 1048576} MB.")

    ident = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta = MIGRACAO_DIR / ident
    (pasta / pipeline.PASTA_TABELAS).mkdir(parents=True, exist_ok=True)
    (pasta / ARQ_BACKUP).write_bytes(conteudo)

    with _lock:
        _estado = {
            "id": ident,
            "versao": 0,
            "fase": "extraindo",
            "pasta": str(pasta),
            "arquivo": nome_arquivo or ARQ_BACKUP,
            "tamanho": len(conteudo),
            "criado_em": _agora(),
            "atualizado_em": _agora(),
            "tabelas": [],
            "opcoes": Opcoes().como_dict(),
            "passos": [],
            "relatorio": None,
            "resultado": None,
            # Etapas ja commitadas nesta execucao. Existe para uma coisa so:
            # impedir que a mesma etapa entre duas vezes. Ver `executar`.
            "gravadas": [],
            "erro": None,
        }
        _salvar()

    try:
        info = pipeline.extrair(pasta / ARQ_BACKUP, pasta / pipeline.PASTA_TABELAS)
    except Exception as e:
        with _lock:
            _mudou(fase="erro", erro=f"Não foi possível ler o backup: {e}")
        raise

    with _lock:
        _mudou(fase="pronto", tabelas=info["tabelas"])
    return estado()


def conferir(opcoes: dict | None = None, db_args: dict | None = None) -> dict:
    """Dispara a conferência (dry-run) em segundo plano."""
    return _disparar("conferindo", PASSOS_CONFERENCIA, _rodar_conferencia,
                     opcoes, db_args)


def executar(opcoes: dict | None = None, db_args: dict | None = None) -> dict:
    """
    Dispara a gravação em segundo plano.

    Exige conferência antes: o `obras.mrc` e o `exemplares.csv` que vão para o
    banco são os que ela gerou. Gravar sem ter conferido seria gravar algo que
    ninguém viu.
    """
    with _lock:
        if _estado is None:
            raise RuntimeError("Não há backup carregado.")
        if _estado.get("relatorio") is None:
            raise RuntimeError(
                "Rode a conferência antes de gravar: é ela que gera os "
                "arquivos que entram no banco.")
        impedimentos = _estado["relatorio"].get("impedimentos") or []
        pedidas = Opcoes.de_dict({**_estado["opcoes"],
                                  **{k: v for k, v in (opcoes or {}).items()
                                     if v is not None}}).etapas()
        repetidas = sorted(set(_estado.get("gravadas") or []) & set(pedidas))
    if impedimentos:
        raise RuntimeError("A conferência apontou impedimentos: "
                           + " ".join(impedimentos))
    # A checagem de base ocupada cobre isto quando há banco conectado, mas ela
    # depende do banco — e o caminho sem senha na conferência é justamente o
    # comum. Duas cargas da mesma etapa duplicam um acervo inteiro; barrar aqui
    # não depende de nada externo.
    if repetidas:
        raise RuntimeError(
            f"Esta execução já gravou: {', '.join(repetidas)}. Desmarque essas "
            f"etapas ou descarte a execução e comece outra.")
    return _disparar("gravando", PASSOS_GRAVACAO, _rodar_gravacao,
                     opcoes, db_args)


def _disparar(fase, modelo, alvo, opcoes, db_args) -> dict:
    global _thread
    with _lock:
        if _estado is None:
            raise RuntimeError("Não há backup carregado.")
        if ocupado():
            raise RuntimeError("Já existe uma migração em andamento.")
        op = Opcoes.de_dict({**_estado["opcoes"],
                             **{k: v for k, v in (opcoes or {}).items()
                                if v is not None}})
        # Uma nova conferência descarta o relatório anterior: o que está na
        # tela tem de corresponder às opções que acabaram de ser escolhidas.
        anteriores = {"resultado": None}
        if fase == "conferindo":
            anteriores["relatorio"] = None
        _mudou(fase=fase, erro=None, opcoes=op.como_dict(),
               passos=_passos(modelo, op), **anteriores)
        pasta = Path(_estado["pasta"])

    _thread = threading.Thread(target=alvo, args=(pasta, op, dict(db_args or {})),
                               name=f"migracao-{fase}", daemon=True)
    _thread.start()
    return estado()


def descartar() -> dict:
    """Esquece a execução e apaga a pasta — o `.bkp` tem dado pessoal dentro."""
    global _estado
    with _lock:
        if ocupado():
            raise RuntimeError("Há uma migração em andamento.")
        if _estado is None:
            return {"status": "vazio"}
        pasta = Path(_estado["pasta"])
        _estado = None
    shutil.rmtree(pasta, ignore_errors=True)
    return {"status": "ok"}


# ---------------------------------------------------------- os trabalhos

def _conectar(db_args: dict, obrigatorio: bool):
    """
    Conexão para o trabalho, ou None quando não há senha e ela é opcional.

    Timeout maior que o da tela: aqui a conexão fica aberta por minutos, e a
    sonda de 5s existe para não travar a pílula do topo.
    """
    cfg = {**conexao.db_config(), **(db_args or {})}
    if not (cfg.get("senha") or cfg.get("password")):
        if obrigatorio:
            raise RuntimeError(
                "Senha do PostgreSQL não informada — a gravação precisa dela.")
        return None, cfg
    return conexao.conectar(cfg, timeout=30), cfg


def _rodar_conferencia(pasta: Path, opcoes: Opcoes, db_args: dict) -> None:
    con = None
    try:
        con, cfg = _conectar(db_args, obrigatorio=False)
        relatorio = pipeline.analisar(
            pasta, opcoes, con=con,
            schema=cfg.get("schema") or conexao.SCHEMA_PADRAO,
            progresso=_marcar)
        _fechar_passos("pulado")
        with _lock:
            _mudou(fase="conferido", relatorio=relatorio)
    except Exception as e:
        _fechar_passos("pendente")
        with _lock:
            _mudou(fase="erro", erro=str(e))
    finally:
        _fechar(con)


def _rodar_gravacao(pasta: Path, opcoes: Opcoes, db_args: dict) -> None:
    con = None
    try:
        con, cfg = _conectar(db_args, obrigatorio=True)
        resultado = pipeline.gravar(
            pasta, opcoes, con,
            schema=cfg.get("schema") or conexao.SCHEMA_PADRAO,
            progresso=_marcar)
        _fechar_passos("pulado")
        with _lock:
            gravadas = set(_estado.get("gravadas") or []) | set(resultado["etapas"])
            _mudou(fase="concluido", resultado=resultado,
                   gravadas=sorted(gravadas))
    except Exception as e:
        _fechar_passos("pendente")
        with _lock:
            # A primeira pergunta de quem lê um erro aqui é "entrou metade?".
            # A resposta é não, e ela vem junto: o commit é a última linha de
            # `pipeline.gravar`, e qualquer falha antes dele dá rollback.
            _mudou(fase="erro",
                   erro=f"{e} Nada foi gravado — a transação só é confirmada "
                        f"no fim, e falha antes disso desfaz tudo.")
    finally:
        _fechar(con)


def _fechar(con) -> None:
    if con is None:
        return
    try:
        con.close()
    except Exception:
        pass


# ------------------------------------------------------- reidratação

def carregar_do_disco() -> dict | None:
    """
    Recupera a execução mais recente na subida do processo.

    Uma execução interrompida no meio volta como erro. No caso da gravação a
    mensagem é explícita quanto ao que não se sabe: o processo morreu com a
    transação aberta, e daqui não dá para afirmar se o banco a recebeu.
    """
    global _estado
    if not MIGRACAO_DIR.is_dir():
        return None
    pastas = sorted((p for p in MIGRACAO_DIR.iterdir() if p.is_dir()),
                    key=lambda p: p.name, reverse=True)
    for pasta in pastas:
        arquivo = pasta / ARQ_ESTADO
        if not arquivo.exists():
            continue
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dados["pasta"] = str(pasta)  # a pasta pode ter mudado de máquina
        if dados.get("fase") in ("conferindo", "extraindo"):
            dados["fase"] = "erro"
            dados["erro"] = ("O servidor foi reiniciado durante a conferência. "
                             "Rode a conferência de novo.")
        elif dados.get("fase") == "gravando":
            dados["fase"] = "erro"
            dados["erro"] = (
                "O servidor foi reiniciado durante a gravação. Não é possível "
                "afirmar daqui se a transação chegou a ser confirmada — "
                "confira as contagens no BibLivre antes de tentar de novo.")
        with _lock:
            _estado = dados
        return estado()
    return None


_SEGURO = re.compile(r"^[0-9A-Za-z_.-]+$")


def nome_seguro(nome: str) -> str:
    """Nome de arquivo enviado pelo navegador, reduzido ao que é exibível."""
    base = Path(nome or "").name
    return base if _SEGURO.match(base or "") else ARQ_BACKUP
