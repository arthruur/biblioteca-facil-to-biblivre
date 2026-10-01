"""Informações do próprio servidor: URL de acesso, QR code e saúde."""

import io

from fastapi import APIRouter
from fastapi.responses import Response

from biblio.catalogacao import config

router = APIRouter(tags=["sistema"])


@router.get("/sistema/info", summary="URL de acesso e o que a tela precisa saber ao subir")
async def info():
    """
    A tela do PC mostra esta URL num QR code para o celular abrir. Antes o valor
    era substituído no HTML na hora de servir; agora vem por aqui, porque o
    frontend é um bundle estático e não dá mais para reescrever a página.
    """
    return {
        "server_url": config.SERVER_URL,
        "data_dir": str(config.DATA_DIR),
        "ocr_disponivel": config.tesseract_cmd() is not None,
    }


# As telas que o celular abre direto pelo QR. Lista fechada: o QR é impresso
# na tela do PC, e um parâmetro livre viraria QR para qualquer endereço.
TELAS_DO_CELULAR = {"": "", "circulacao": "/circulacao"}


@router.get("/qrcode", summary="QR code da URL do servidor, para abrir no celular")
async def qrcode(tela: str = ""):
    """
    `tela=circulacao` aponta o QR para `/circulacao` — o celular cai direto no
    balcão, em vez da captura de ISBN que a raiz abre.
    """
    import qrcode
    import qrcode.image.svg

    if tela not in TELAS_DO_CELULAR:
        return Response(status_code=400, content=f"tela desconhecida: {tela}")
    url = config.SERVER_URL.rstrip("/") + TELAS_DO_CELULAR[tela]
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@router.get("/saude", summary="Liveness — não toca no banco")
async def saude():
    return {"status": "ok"}
