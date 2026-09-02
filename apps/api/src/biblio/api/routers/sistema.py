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


@router.get("/qrcode", summary="QR code da URL do servidor, para abrir no celular")
async def qrcode():
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(config.SERVER_URL, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@router.get("/saude", summary="Liveness — não toca no banco")
async def saude():
    return {"status": "ok"}
