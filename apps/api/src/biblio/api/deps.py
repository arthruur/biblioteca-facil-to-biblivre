"""Utilitários compartilhados pelos routers."""

from starlette.concurrency import run_in_threadpool


async def em_thread(func, *args, **kwargs):
    """
    Roda uma função bloqueante fora do event loop.

    Quase tudo aqui é bloqueante — psycopg2, urllib nos lookups de ISBN, OpenCV
    no OCR. Sem isto, um lookup lento de 10s no celular travaria o servidor
    inteiro, inclusive a tela de revisão no PC.
    """
    return await run_in_threadpool(lambda: func(*args, **kwargs))
