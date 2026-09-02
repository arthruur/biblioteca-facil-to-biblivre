"""
Sobe o ambiente de desenvolvimento inteiro num comando só, sem Docker.

    python scripts/dev.py
    python scripts/dev.py --porta 8000 --porta-web 5173
    python scripts/dev.py --so-api          # sem o dev server do Vite

Dois processos, um terminal:

  [api]  uvicorn com --reload  (https://<ip>:8000)  — reinicia ao salvar .py
  [web]  vite dev server       (https://<ip>:5173)  — HMR no JSX/CSS

Trabalhe pela porta 5173: o Vite faz proxy de /api para o backend, então o
frontend recarrega em milissegundos sem `npm run build`. A 8000 continua
servindo o bundle buildado, quando existir — é o que a biblioteca usa.

O container não entra nesse laço. Ele existe para a instalação na biblioteca,
onde o valor é embutir Tesseract e OpenCV numa imagem só; em desenvolvimento
ele só acrescenta um rebuild entre você e o efeito da linha que acabou de
escrever.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "apps" / "web"
WINDOWS = os.name == "nt"

_processos: list[subprocess.Popen] = []
_encerrando = threading.Event()

# O Vite escreve "➜" e o uvicorn escreve acento; num console do Windows com
# codepage legada (cp1252) o repasse dessas linhas morre em UnicodeEncodeError
# e mata a thread que le a saida — o log do processo simplesmente para.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _argumentos():
    p = argparse.ArgumentParser(description="Desenvolvimento: API + Vite")
    p.add_argument("--porta", type=int, default=8000, help="porta da API")
    p.add_argument("--porta-web", type=int, default=5173, help="porta do Vite")
    p.add_argument("--so-api", action="store_true", help="não sobe o Vite")
    p.add_argument("--sem-ssl", action="store_true",
                   help="API em HTTP (a câmera do celular não funciona)")
    return p.parse_args()


def _eco(rotulo: str, proc: subprocess.Popen) -> None:
    """Repassa a saída do processo com prefixo, para os dois logs conviverem."""
    for linha in proc.stdout:
        if _encerrando.is_set():
            return
        sys.stdout.write(f"  [{rotulo}] {linha.rstrip()}\n")
        sys.stdout.flush()


def _subir(rotulo: str, comando: list[str], cwd: Path) -> subprocess.Popen:
    # Grupo próprio no Windows: o npm.cmd sobe um node filho, e matar só o
    # .cmd deixaria o dev server vivo segurando a porta 5173.
    extra = {}
    if WINDOWS:
        extra["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        extra["start_new_session"] = True

    # O worker do reload e um subprocesso que o uvicorn cria — ele nao passa
    # pelo `reconfigure` do servidor.py, e no Windows sairia em cp1252. Como
    # lemos como UTF-8, "Índice" chegaria aqui como caractere de substituicao.
    # Sem PYTHONUNBUFFERED a saida do filho e bufferizada em bloco (o stdout
    # dele e um pipe, nao um terminal) e o banner com a URL do servidor so
    # apareceria segundos depois — justo a linha que voce precisa ler primeiro.
    ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1"}

    proc = subprocess.Popen(
        comando, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        env=ambiente, **extra)
    _processos.append(proc)
    threading.Thread(target=_eco, args=(rotulo, proc), daemon=True).start()
    return proc


def _matar_todos() -> None:
    _encerrando.set()
    for proc in _processos:
        if proc.poll() is not None:
            continue
        try:
            if WINDOWS:
                # /T mata a árvore: o uvicorn tem o worker do reload, o npm
                # tem o node. Sem isso sobra órfão segurando a porta.
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _npm() -> str | None:
    return shutil.which("npm") or shutil.which("npm.cmd")


def _garantir_node_modules(npm: str) -> bool:
    if (WEB / "node_modules").is_dir():
        return True
    print("  [web] node_modules ausente — rodando npm install (uma vez só)…")
    return subprocess.run([npm, "install", "--no-audit", "--no-fund"],
                          cwd=str(WEB)).returncode == 0


def main() -> int:
    args = _argumentos()

    # Ctrl+C ja cai no KeyboardInterrupt, mas um SIGTERM (o `timeout` de um
    # script, o botao de parar do editor) mataria so este processo e deixaria
    # o uvicorn e o node vivos segurando as portas.
    def _ao_terminar(_sinal, _quadro):
        _encerrando.set()

    for _sinal in (signal.SIGTERM, getattr(signal, "SIGBREAK", None)):
        if _sinal is not None:
            try:
                signal.signal(_sinal, _ao_terminar)
            except (ValueError, OSError):
                pass

    comando_api = [sys.executable, str(RAIZ / "scripts" / "servidor.py"),
                   "--reload", "--porta", str(args.porta)]
    if args.sem_ssl:
        comando_api.append("--sem-ssl")

    print("")
    print("  === Desenvolvimento (sem Docker) ===")
    _subir("api", comando_api, RAIZ)

    if not args.so_api:
        npm = _npm()
        if not npm:
            print("  [web] npm não encontrado no PATH — subindo só a API.")
        elif not _garantir_node_modules(npm):
            print("  [web] npm install falhou — subindo só a API.")
        else:
            # O vite.config.js le BIBLIO_API para montar o proxy de /api; o
            # filho herda o ambiente daqui.
            esquema = "http" if args.sem_ssl else "https"
            os.environ["BIBLIO_API"] = f"{esquema}://localhost:{args.porta}"
            # Sem isto o Vite subiria em HTTPS (o certificado existe em
            # data/certs) enquanto a API esta em HTTP, e o proxy nao fecharia.
            os.environ["BIBLIO_SEM_SSL"] = "1" if args.sem_ssl else ""
            _subir("web", [npm, "run", "dev", "--", "--port",
                           str(args.porta_web)], WEB)
            print(f"  Trabalhe em {esquema}://localhost:{args.porta_web}"
                  "  (HMR + proxy para a API)")

    print("  Ctrl+C encerra os dois.")
    print("")

    try:
        # Se um dos dois morrer, não vale manter o outro de pé fingindo que
        # está tudo bem: o erro precisa aparecer.
        while not _encerrando.wait(0.5):
            for proc in list(_processos):
                codigo = proc.poll()
                if codigo is not None:
                    print(f"\n  Um dos processos saiu (código {codigo}) — "
                          "encerrando o outro.")
                    return codigo or 1
        return 0
    except KeyboardInterrupt:
        print("\n  Encerrando…")
        return 0
    finally:
        _matar_todos()


if __name__ == "__main__":
    sys.exit(main())
