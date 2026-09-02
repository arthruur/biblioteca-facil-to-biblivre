"""
Sobe o servidor de catalogação.

    python scripts/servidor.py                    # https://0.0.0.0:8000
    python scripts/servidor.py --sem-ssl          # http://localhost:8000
    python scripts/servidor.py --db-senha SENHA   # liga a checagem de ISBN

Casca fina: a aplicação está em `biblio.api`. Depois de `pip install -r
requirements.txt` o mesmo servidor também sobe pelo comando `biblio-servidor`.
"""

from biblio.api.servidor import main

if __name__ == "__main__":
    main()
