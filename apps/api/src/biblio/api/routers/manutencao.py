"""
Os passos que sobravam fora do app: reindexar, caches, conferência, backup.

ESQUELETO DO INTEGRADOR — dono é o pacote **A8**. Duas regras que a
implementação não pode perder de vista:

  * reindex e backup **disparam e voltam**; o progresso é rota separada. São
    minutos de trabalho do lado do Tomcat, e a tela precisa de barra, não de
    requisição pendurada;
  * a senha do admin do BibLivre segue a regra da senha do Postgres: memória,
    nunca disco, nunca de volta na resposta.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/manutencao", tags=["manutencao"])


def _pendente(rota: str):
    return JSONResponse(
        {"status": "erro", "codigo": "nao_implementado",
         "mensagem": f"{rota}: pendente (pacote A8 do plano de agentes)"},
        status_code=501)


@router.get("", summary="Estado: BibLivre configurado, reindex, backup")
async def estado():
    return _pendente("GET /manutencao")


@router.post("/biblivre", summary="URL e credencial de admin do BibLivre")
async def configurar_biblivre():
    return _pendente("POST /manutencao/biblivre")


@router.post("/reindexar", summary="Dispara o reindex da base bibliográfica")
async def reindexar():
    return _pendente("POST /manutencao/reindexar")


@router.get("/reindexar", summary="Progresso do reindex")
async def progresso_reindex():
    return _pendente("GET /manutencao/reindexar")


@router.post("/caches", summary="Derruba os caches estáticos sem reiniciar o Tomcat")
async def caches():
    return _pendente("POST /manutencao/caches")


@router.post("/conferencia", summary="Conferência pós-carga (só leitura)")
async def conferencia():
    return _pendente("POST /manutencao/conferencia")


@router.post("/backup", summary="Gera o .b5bz pelo próprio BibLivre")
async def backup():
    return _pendente("POST /manutencao/backup")


@router.get("/backup", summary="Estado do backup")
async def estado_backup():
    return _pendente("GET /manutencao/backup")
