"""
Sobe o servidor de catalogação.

    python scripts/servidor.py                    # https://0.0.0.0:8000
    python scripts/servidor.py --reload           # reinicia ao salvar (dev)
    python scripts/servidor.py --sem-ssl          # http://localhost:8000
    python scripts/servidor.py --db-senha SENHA   # liga a checagem de ISBN

Em desenvolvimento, `python scripts/dev.py` sobe este servidor com --reload e
o dev server do Vite ao mesmo tempo — é o comando do dia a dia.

Casca fina: a aplicação está em `biblio.api`. Depois de `pip install -r
requirements.txt` o mesmo servidor também sobe pelo comando `biblio-servidor`.
"""

from biblio.api.servidor import main

if __name__ == "__main__":
    main()
