"""API HTTP do sistema de acervo. A app fica em `main.create_app()`."""

from .main import app, create_app

__all__ = ["app", "create_app"]
