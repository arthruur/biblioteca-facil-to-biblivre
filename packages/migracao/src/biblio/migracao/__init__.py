"""
Migração de acervo legado: do `.bkp` do Biblioteca Fácil ao BibLivre 5.

Dois módulos, com responsabilidades separadas de propósito:

  `pipeline`  o que fazer — chama `biblio.legado` e `biblio.biblivre` na mesma
              ordem dos CLIs de `scripts/`, sem reimplementar nenhum deles.
  `execucao`  quando e para quem — a execução única, o estado que a tela busca
              em laço e a persistência que faz o relatório sobreviver a F5.
"""

from . import execucao, pipeline  # noqa: F401
from .pipeline import Opcoes  # noqa: F401

__all__ = ["pipeline", "execucao", "Opcoes"]
