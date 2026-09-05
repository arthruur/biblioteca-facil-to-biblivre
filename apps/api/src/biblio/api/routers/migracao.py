"""
Migração de acervo legado: o `.bkp` do Biblioteca Fácil vira acervo no BibLivre.

Este router é casca fina como os outros — quem sabe fazer é `biblio.migracao`,
que por sua vez só orquestra `biblio.legado` e `biblio.biblivre`, as mesmas
funções que os CLIs de `scripts/` usam.

A postura aqui é a da fila, não a da captura: **nada é apressado e nada escreve
sem confirmação explícita**. São três passos separados de propósito — enviar o
backup, conferir (não toca no banco) e gravar (uma transação só) — porque a
gravação não tem desfazer pela tela.
"""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from biblio.biblivre import conexao
from biblio.migracao import execucao

from ..deps import em_thread
from ..schemas import PedidoMigracao

router = APIRouter(prefix="/migracao", tags=["migracao"])


def _erro(mensagem: str, status: int):
    return JSONResponse({"status": "erro", "mensagem": mensagem},
                        status_code=status)


def _credenciais(dados: PedidoMigracao) -> dict:
    """
    A senha segue a regra do export: entra em memória, nunca em disco.

    Informar a senha aqui também liga a checagem de ISBN da catalogação — é a
    mesma configuração de conexão, e ter duas seria pedir divergência.
    """
    db_args = dados.db.para_config() if dados.db else None
    if db_args and db_args.get("senha"):
        conexao.definir_db(db_args)
    return {**conexao.db_config(), **(db_args or {})}


@router.get("", summary="Estado da execução corrente (fase, passos, relatório)")
async def estado():
    return execucao.estado()


@router.get("/versao", summary="Só o contador — para laço de baixo custo")
async def versao():
    return {"versao": execucao.versao(), "ocupado": execucao.ocupado()}


@router.post("/backup", summary="Envia o .bkp e extrai as 16 tabelas")
async def enviar_backup(arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read()
    try:
        return await em_thread(execucao.iniciar,
                               execucao.nome_seguro(arquivo.filename), conteudo)
    except RuntimeError as e:
        return _erro(str(e), 409)
    except Exception as e:
        return _erro(str(e), 400)


@router.post("/conferir", summary="Dry-run: relatório completo, sem escrever nada")
async def conferir(dados: PedidoMigracao | None = None):
    """
    Gera os arquivos de conferência e conta o que a gravação faria.

    Roda sem senha do Postgres: o que depende do banco (contagens do destino,
    prefixo de tombo, base já ocupada) fica como aviso no relatório, em vez de
    o passo inteiro falhar.
    """
    dados = dados or PedidoMigracao()
    try:
        return execucao.conferir(dados.opcoes_dict(), _credenciais(dados))
    except RuntimeError as e:
        return _erro(str(e), 409)


@router.post("/executar", summary="Grava no BibLivre — uma transação, sem desfazer")
async def executar(dados: PedidoMigracao | None = None):
    """
    O único caminho desta área que escreve no acervo.

    Exige conferência feita (é dela que saem o MRC e o CSV que entram no
    banco), nenhum impedimento em aberto e confirmação explícita da tela.
    """
    dados = dados or PedidoMigracao()
    if not dados.confirmado:
        return _erro("A gravação precisa de confirmação explícita.", 400)
    try:
        return execucao.executar(dados.opcoes_dict(), _credenciais(dados))
    except RuntimeError as e:
        return _erro(str(e), 409)


@router.delete("", summary="Descarta a execução e apaga os arquivos do backup")
async def descartar():
    """
    O `.bkp` e os CSVs têm nome, CPF e endereço de leitores. Descartar apaga a
    pasta inteira, não só a referência.
    """
    try:
        return execucao.descartar()
    except RuntimeError as e:
        return _erro(str(e), 409)


@router.get("/arquivos/{nome}", summary="Baixa um arquivo de conferência")
async def arquivo(nome: str):
    try:
        caminho = execucao.caminho_de_artefato(nome)
    except FileNotFoundError as e:
        return _erro(str(e), 404)
    return FileResponse(caminho, filename=nome,
                        media_type="application/octet-stream")
