"""
Deixa o servidor rodando sozinho, subindo junto com o Windows.

    python scripts/inicializacao.py instalar     # uma vez, no PC da biblioteca
    python scripts/inicializacao.py status
    python scripts/inicializacao.py reiniciar
    python scripts/inicializacao.py parar | iniciar
    python scripts/inicializacao.py remover

`python scripts/dev.py` é para quem está mexendo no código: reload, Vite,
terminal aberto. Na biblioteca ninguém deveria precisar abrir terminal — o
computador liga, alguém entra no Windows e o balcão já responde em
https://<IP-DO-PC>:8000.

COMO
----
`instalar` builda o frontend (se ainda não houver `apps/web/dist`), cria uma
tarefa agendada do Windows que roda no logon deste usuário e já a dispara. A
tarefa chama `pythonw` — o Python sem janela de console — com
`inicializacao.py rodar`, que sobe o mesmo `biblio-servidor` de produção (sem
reload, servindo o bundle buildado) e escreve o log em `data/logs/servidor.log`,
já que não há console para ler.

Por que tarefa agendada e não serviço do Windows: serviço exige administrador e
uma ferramenta a mais (NSSM), e roda numa sessão sem área de trabalho. A tarefa
se cria sem administrador, é reiniciada pelo próprio Windows se o processo
cair, e aparece no Agendador de Tarefas com o nome `BiblioFacil` para quem
quiser conferir ou desligar. Se a política da máquina não deixar criar tarefa,
cai para um atalho na pasta Inicializar do usuário — sobe igual no logon, só
não se reinicia sozinho.

A senha do Postgres vem do `.env` da raiz, como no resto do projeto: a tarefa
não guarda credencial nenhuma.

Também deixa na Área de Trabalho um atalho que abre o sistema no navegador.
"""

import argparse
import ctypes
import getpass
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "apps" / "web"
LOGS = RAIZ / "data" / "logs"
LOG = LOGS / "servidor.log"
LOG_MAXIMO = 5 * 1024 * 1024        # passou disso, o log vira .1 na subida

TAREFA = "BiblioFacil"
ATALHO_INICIAR = "BiblioFacil.vbs"
ATALHO_ABRIR = "BiblioFácil.url"
WINDOWS = os.name == "nt"


def _console_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _pythonw() -> str:
    """O Python sem console, ao lado do que está rodando este script."""
    candidato = Path(sys.executable).with_name("pythonw.exe")
    return str(candidato if candidato.exists() else sys.executable)


def _oem(saida: bytes) -> str:
    """`schtasks` fala na codepage OEM do console (cp850 num Windows em pt-BR)."""
    try:
        pagina = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except (AttributeError, OSError):
        pagina = "utf-8"
    return saida.decode(pagina, errors="replace").strip()


def _schtasks(*args) -> tuple[int, str]:
    r = subprocess.run(["schtasks", *args], capture_output=True)
    return r.returncode, _oem(r.stdout or r.stderr)


def _pasta_especial(csidl: int) -> Path:
    """Área de Trabalho e Inicializar, mesmo quando o OneDrive as redireciona."""
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


def _area_de_trabalho() -> Path:
    return _pasta_especial(0x10)            # CSIDL_DESKTOPDIRECTORY


def _inicializar() -> Path:
    return _pasta_especial(0x07)            # CSIDL_STARTUP


def _porta_aberta(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=1):
            return True
    except OSError:
        return False


# ------------------------------------------------------------------ build

def _garantir_bundle(rebuildar: bool) -> None:
    """
    O servidor de produção serve `apps/web/dist`. Sem ele a API responde, mas
    o navegador não tem tela nenhuma para mostrar.
    """
    if (WEB / "dist" / "index.html").exists() and not rebuildar:
        print("  frontend: apps/web/dist já existe (use --rebuildar para refazer)")
        return
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit(
            "  ERRO: o frontend não está buildado e o npm não foi encontrado.\n"
            "  Instale o Node.js (nodejs.org) e rode de novo, ou copie a pasta\n"
            "  apps/web/dist de outra máquina.")
    if not (WEB / "node_modules").exists():
        print("  frontend: npm install…")
        subprocess.run([npm, "install"], cwd=WEB, check=True)
    print("  frontend: npm run build…")
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


# ---------------------------------------------------------- tarefa e atalhos

def _comando(argumentos_servidor: list[str]) -> tuple[str, str]:
    script = Path(__file__).resolve()
    extras = " ".join(f'"{a}"' for a in argumentos_servidor)
    return _pythonw(), f'"{script}" rodar {extras}'.strip()


def _xml_da_tarefa(comando: str, argumentos: str) -> str:
    """
    Logon deste usuário, sem limite de duração (o padrão do Windows mata a
    tarefa em 72h), reiniciada a cada minuto se o processo cair, e sem desistir
    por estar na bateria — num notebook de balcão isso desligaria o sistema.
    """
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\{getpass.getuser()}".lstrip("\\")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Servidor do BiblioFácil (catalogação, migração e balcão do BibLivre). Criado por scripts/inicializacao.py.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{escape(usuario)}</UserId>
      <Delay>PT15S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(usuario)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(comando)}</Command>
      <Arguments>{escape(argumentos)}</Arguments>
      <WorkingDirectory>{escape(str(RAIZ))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _criar_tarefa(comando: str, argumentos: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                     encoding="utf-16") as f:
        f.write(_xml_da_tarefa(comando, argumentos))
        caminho = f.name
    try:
        codigo, saida = _schtasks("/Create", "/TN", TAREFA, "/XML", caminho, "/F")
    finally:
        os.remove(caminho)
    return codigo == 0, saida


def _tarefa_existe() -> bool:
    return _schtasks("/Query", "/TN", TAREFA)[0] == 0


def _criar_atalho_inicializar(comando: str, argumentos: str) -> Path:
    """O plano B: um .vbs na pasta Inicializar, que sobe sem janela."""
    destino = _inicializar() / ATALHO_INICIAR
    linha = f'"{comando}" {argumentos}'.replace('"', '""')
    destino.write_text(
        "' Criado por scripts/inicializacao.py: sobe o BiblioFácil no logon.\r\n"
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.CurrentDirectory = "{RAIZ}"\r\n'
        f'shell.Run "{linha}", 0, False\r\n',
        encoding="utf-16")
    return destino


def _criar_atalho_abrir(porta: int, sem_ssl: bool) -> Path:
    destino = _area_de_trabalho() / ATALHO_ABRIR
    url = f"{'http' if sem_ssl else 'https'}://localhost:{porta}/"
    destino.write_text(f"[InternetShortcut]\r\nURL={url}\r\n", encoding="utf-8")
    return destino


# --------------------------------------------------------------- comandos

def instalar(args) -> None:
    print("Instalando o BiblioFácil para subir com o Windows")
    _garantir_bundle(args.rebuildar)

    servidor = ["--porta", str(args.porta)] + (["--sem-ssl"] if args.sem_ssl else [])
    comando, argumentos = _comando(servidor)

    criada, saida = _criar_tarefa(comando, argumentos)
    if criada:
        print(f"  tarefa agendada '{TAREFA}' criada: sobe no logon de "
              f"{getpass.getuser()} e se reinicia se cair")
        antigo = _inicializar() / ATALHO_INICIAR
        if antigo.exists():
            antigo.unlink()     # não deixar dois caminhos subindo o mesmo servidor
    else:
        print(f"  a tarefa agendada não pôde ser criada ({saida})")
        destino = _criar_atalho_inicializar(comando, argumentos)
        print(f"  plano B: atalho em {destino}")

    atalho = _criar_atalho_abrir(args.porta, args.sem_ssl)
    print(f"  atalho para abrir o sistema: {atalho}")

    if not (RAIZ / ".env").exists():
        print("  ATENÇÃO: não há .env na raiz. Sem a senha do Postgres o balcão "
              "não grava — copie .env.example para .env e preencha.")

    if _porta_aberta(args.porta):
        print(f"  a porta {args.porta} já está ocupada — se for um servidor "
              f"antigo, rode 'reiniciar' depois de fechá-lo.")
    else:
        iniciar(args, silencioso=True)
    status(args)


def remover(args) -> None:
    if _tarefa_existe():
        _schtasks("/End", "/TN", TAREFA)
        codigo, saida = _schtasks("/Delete", "/TN", TAREFA, "/F")
        print(f"  tarefa '{TAREFA}': {'removida' if codigo == 0 else saida}")
    for destino in (_inicializar() / ATALHO_INICIAR,
                    _area_de_trabalho() / ATALHO_ABRIR):
        if destino.exists():
            destino.unlink()
            print(f"  removido: {destino}")
    print("O servidor não sobe mais com o Windows. Os dados em data/ ficaram.")


def iniciar(args, silencioso: bool = False) -> None:
    if _tarefa_existe():
        codigo, saida = _schtasks("/Run", "/TN", TAREFA)
        if codigo != 0:
            raise SystemExit(f"  não deu para iniciar a tarefa: {saida}")
    else:
        comando, argumentos = _comando(
            ["--porta", str(args.porta)] + (["--sem-ssl"] if args.sem_ssl else []))
        subprocess.Popen(f'"{comando}" {argumentos}', cwd=RAIZ,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    print("  subindo… (a primeira subida monta o índice de ISBN e leva alguns segundos)")
    for _ in range(40):
        if _porta_aberta(args.porta):
            break
        time.sleep(0.5)
    if not silencioso:
        status(args)


def parar(args) -> None:
    if not _tarefa_existe():
        raise SystemExit(f"  a tarefa '{TAREFA}' não existe — feche o servidor "
                         f"pelo Gerenciador de Tarefas (pythonw.exe).")
    _schtasks("/End", "/TN", TAREFA)
    for _ in range(20):
        if not _porta_aberta(args.porta):
            break
        time.sleep(0.5)
    print("  parado" if not _porta_aberta(args.porta)
          else f"  a porta {args.porta} continua respondendo — há outro servidor de pé?")


def reiniciar(args) -> None:
    parar(args)
    iniciar(args)


def status(args) -> None:
    tarefa = _tarefa_existe()
    plano_b = (_inicializar() / ATALHO_INICIAR).exists() if WINDOWS else False
    no_ar = _porta_aberta(args.porta)
    print(f"  sobe com o Windows: "
          f"{'sim (tarefa agendada)' if tarefa else 'sim (pasta Inicializar)' if plano_b else 'não'}")
    print(f"  no ar agora:        {'sim' if no_ar else 'não'} (porta {args.porta})")
    if no_ar:
        from biblio.catalogacao.rede import obter_ip_local
        esquema = "http" if args.sem_ssl else "https"
        print(f"  no PC:              {esquema}://localhost:{args.porta}/")
        print(f"  no celular:         {esquema}://{obter_ip_local()}:{args.porta}/")
    if LOG.exists():
        print(f"  log:                {LOG}")


def rodar(servidor: list[str]) -> None:
    """
    O que a tarefa executa. Sem console (`pythonw`), então tudo vai para o
    log — inclusive o traceback de uma subida que falhou, que é a primeira
    coisa que alguém vai querer ler.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > LOG_MAXIMO:
        LOG.replace(LOG.with_suffix(".log.1"))
    saida = open(LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = saida
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} subindo ===")
    os.chdir(RAIZ)

    from biblio.api.servidor import main
    sys.argv = ["biblio-servidor", *servidor]
    try:
        main()
    except BaseException:
        import traceback
        traceback.print_exc()
        raise


def _argumentos():
    p = argparse.ArgumentParser(
        description="Sobe o BiblioFácil junto com o Windows (sem terminal aberto)")
    sub = p.add_subparsers(dest="acao", required=True)
    for nome, ajuda in (("instalar", "cria a tarefa, o atalho e já sobe"),
                        ("remover", "tira da inicialização"),
                        ("status", "diz se está instalado e no ar"),
                        ("iniciar", "sobe agora"),
                        ("parar", "derruba agora"),
                        ("reiniciar", "parar + iniciar (depois de atualizar o código)")):
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("--porta", type=int, default=8000)
        s.add_argument("--sem-ssl", action="store_true",
                       help="HTTP em localhost (a câmera do celular não funciona)")
        if nome == "instalar":
            s.add_argument("--rebuildar", action="store_true",
                           help="refaz o build do frontend mesmo se já existir")
    # `rodar` (uso interno da tarefa) é tratado antes do argparse em `main`:
    # tudo depois dele vai cru para o biblio-servidor.
    return p.parse_args()


def main():
    if sys.argv[1:2] == ["rodar"]:
        rodar(sys.argv[2:])
        return
    _console_utf8()
    args = _argumentos()
    if not WINDOWS:
        raise SystemExit("Isto é para o Windows da biblioteca. No Linux, use o "
                         "docker compose (restart: unless-stopped).")
    acoes = {"instalar": instalar, "remover": remover, "status": status,
             "iniciar": iniciar, "parar": parar, "reiniciar": reiniciar}
    acoes[args.acao](args)


if __name__ == "__main__":
    main()
