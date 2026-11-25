"""
MatheCafé - Instalador do agente com tela (10.11)

Vira o MatheCafe-Instalador.exe (gerar_instalador.bat, PyInstaller): um arquivo
só, com o Python e o Tkinter dentro, que pede administrador ao abrir. Faz os
mesmos passos do instalar.bat e do desinstalar.bat, em telas passo a passo no
visual da Área do Cliente:

  Instalar:    usuário "cliente" -> autologin -> Python do agente (python.org)
               -> agente e dependências -> agente.cfg -> tarefa -> políticas
  Desinstalar: fecha o agente -> tarefas -> autologin -> Python do agente
               -> usuário e perfil -> C:\\MatheCafe

O agente.py vai do servidor (/api/agente/download, a versão liberada); sem
servidor, o que foi embutido no .exe. Um servidor.txt ao lado do .exe troca o
endereço sugerido sem gerar o .exe de novo.

  python instalador.py              instala/desinstala de verdade (como admin)
  python instalador.py --simular    só as telas: cada passo vira uma espera e
                                    nada no Windows é alterado
"""
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

import tkinter as tk
from tkinter import font as tkfont

VERSAO_INSTALADOR = "1.0.0"
DESTINO = r"C:\MatheCafe"
# o mesmo Python do instalar.bat (para trocar, mude nos dois; um teste confere)
PY_VERSAO = "3.13.17"
ARQUIVOS_DO_AGENTE = ("agente.py", "requirements.txt", "iniciar.bat", "registrar_tarefa.ps1",
                      "registrar_politicas.ps1", "politicas_cliente.ps1", "desinstalar.bat")
NOME_DO_EXE = "MatheCafe-Instalador.exe"
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW: os comandos rodam sem piscar console
SIMULAR = "--simular" in sys.argv
DESINSTALAR = "--desinstalar" in sys.argv

# ── cores e fonte: as da Área do Cliente (agente.py, 9.11-9.14) ──
FUNDO, SUPERFICIE, SUPERFICIE2, BORDA = "#09090b", "#18181b", "#27272a", "#27272a"
TEXTO, TEXTO2, FRACO = "#e4e4e7", "#a1a1aa", "#71717a"
AZUL, AZUL_CLARO, TEXTO_CLARO = "#2563eb", "#3b82f6", "#f4f4f5"
ROSA, ROSA_CLARO, ROSA_TEXTO = "#e11d48", "#f43f5e", "#fb7185"
EMERALD, EMERALD_TEXTO, AMBAR = "#10b981", "#34d399", "#f59e0b"
FONTE = "Segoe UI"


# ════════════════════════════════════════════════════════════════════
#  Regras de dados (testadas em server/tests/test_instalador.py)
# ════════════════════════════════════════════════════════════════════

def normalizar_endereco(texto):
    """O endereço como o usuário digitou -> "host:porta" (sem protocolo nem barra)."""
    s = (texto or "").replace(" ", "").strip()
    for prefixo in ("https://", "http://", "wss://", "ws://"):
        if s.lower().startswith(prefixo):
            s = s[len(prefixo):]
    return s.rstrip("/")


def nome_da_estacao(texto, padrao):
    """Vazio = o nome do Windows; o servidor guarda até 20 caracteres."""
    return ((texto or "").strip() or padrao)[:20]


def ler_pisos(texto):
    """A resposta de /api/agente/pisos: uma linha "id;nome" por piso."""
    pisos = []
    for linha in (texto or "").splitlines():
        if ";" in linha:
            pid, nome = linha.split(";", 1)
            if pid.strip() and nome.strip():
                pisos.append((pid.strip(), nome.strip()))
    return pisos


def conteudo_cfg(servidor, estacao, id_pc, piso):
    linhas = ["# MatheCafe - configuracao da estacao (gerado automaticamente)",
              f"SERVIDOR=ws://{servidor}", f"ESTACAO={estacao}"]
    if id_pc:
        linhas.append(f"ID={id_pc}")
    if piso:
        linhas.append(f"PISO={piso}")
    return "\n".join(linhas) + "\n"


def ler_cfg(texto):
    dados = {}
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            dados[chave.strip()] = valor.strip()
    return dados


def id_para_manter(id_antigo, piso_escolhido, resposta_estacao):
    """Reinstalação: mantém o ID do agente.cfg (é por ele que o servidor
    reconhece o PC), menos quando ele é hoje uma estação de OUTRO piso (10.13):
    aí o PC entra no piso escolhido como computador novo."""
    if not id_antigo:
        return None
    piso_atual = (resposta_estacao or "").split(";", 1)[0].strip()
    if piso_escolhido and piso_atual and piso_atual != str(piso_escolhido):
        return None
    return id_antigo


def problema_na_senha(senha, confirmacao):
    if not senha:
        return "Escolha uma senha para o usuário cliente."
    if senha != confirmacao:
        return "As duas senhas não são iguais."
    return None


# ════════════════════════════════════════════════════════════════════
#  Arquivos e servidor
# ════════════════════════════════════════════════════════════════════

def pasta_embutida():
    """Onde estão os arquivos do agente: dentro do .exe (PyInstaller) ou ao lado do .py."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "arquivos")
    return os.path.dirname(os.path.abspath(__file__))


def pasta_do_programa():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def servidor_sugerido():
    """1ª linha do servidor.txt ao lado do .exe; senão o que foi embutido."""
    for pasta in (pasta_do_programa(), pasta_embutida()):
        try:
            with open(os.path.join(pasta, "servidor.txt"), encoding="utf-8-sig") as f:
                return normalizar_endereco(f.readline())
        except OSError:
            continue
    return ""


def pedir(url, timeout=5):
    """GET direto (a rede tem proxy, mas o servidor é interno): texto ou None."""
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with abridor.open(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def sou_administrador():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def cfg_instalado():
    try:
        with open(os.path.join(DESTINO, "agente.cfg"), encoding="utf-8-sig") as f:
            return ler_cfg(f.read())
    except OSError:
        return None


class ErroDeInstalacao(Exception):
    pass


# ════════════════════════════════════════════════════════════════════
#  Os passos (rodam numa thread; a tela recebe os avisos por uma fila)
# ════════════════════════════════════════════════════════════════════

class Execucao:
    def __init__(self, dados, avisar, simular=False):
        self.dados = dados
        self.avisar = avisar  # avisar(tipo, *valores) -> fila da tela
        self.simular = simular
        self.destino = os.path.join(tempfile.gettempdir(), "MatheCafe-simulado") if simular else DESTINO

    # ── ferramentas ──
    def rodar(self, comando, env=None, timeout=900, cwd=None):
        """Um comando do Windows, sem janela. Devolve (código, saída)."""
        if self.simular:
            time.sleep(0.35)
            return 0, ""
        try:
            r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               creationflags=SEM_JANELA, env=env, timeout=timeout, cwd=cwd)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)

    def ps(self, script, env=None):
        return self.rodar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], env=env)

    def ps_arquivo(self, arquivo, *args, env=None):
        return self.rodar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           os.path.join(self.destino, arquivo), *args], env=env)

    def detalhe(self, texto):
        self.avisar("detalhe", texto)

    def fechar_o_agente(self):
        self.ps(f"Get-Process | Where-Object {{ $_.Path -like '{self.destino}\\*' }} | Stop-Process -Force")

    # ── instalar ──
    def passos_instalar(self):
        return [("Usuário Windows \"cliente\"", self.criar_usuario),
                ("Entrar sozinho ao ligar (autologin)", self.autologin),
                ("Python do agente", self.python_do_agente),
                ("Agente e dependências", self.agente_e_dependencias),
                ("Configuração da estação", self.configuracao),
                ("Abrir o agente sozinho", self.tarefa),
                ("Travar o Ctrl+Alt+Del do cliente", self.politicas)]

    def criar_usuario(self):
        senha = self.dados["senha"]
        existe, _ = self.rodar(["net", "user", "cliente"])
        if existe == 0 and not self.simular:
            self.detalhe("O usuário já existe: trocando a senha")
            codigo, saida = self.rodar(["net", "user", "cliente", senha])
        else:
            codigo, saida = self.rodar(["net", "user", "cliente", senha, "/add", "/fullname:Cliente",
                                        "/comment:Usuario restrito MatheCafe"])
        if codigo != 0:
            raise ErroDeInstalacao("Não foi possível criar o usuário cliente.\n" + saida.strip()[:300])
        # senha que expira derruba o autologin
        self.ps("Set-LocalUser -Name cliente -PasswordNeverExpires $true")
        for grupo in ("Administradores", "Administrators"):  # garantia
            self.rodar(["net", "localgroup", grupo, "cliente", "/delete"])

    def autologin(self):
        chave = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
        for nome, valor in (("AutoAdminLogon", "1"), ("DefaultUserName", "cliente"),
                            ("DefaultPassword", self.dados["senha"]), ("DefaultDomainName", ".")):
            codigo, saida = self.rodar(["reg", "add", chave, "/v", nome, "/t", "REG_SZ", "/d", valor, "/f"])
            if codigo != 0:
                raise ErroDeInstalacao("Não foi possível ligar o autologin.\n" + saida.strip()[:300])

    def _python_pronto(self):
        if self.simular:
            return False
        exe = os.path.join(self.destino, "python", "python.exe")
        if not os.path.exists(exe):
            return False
        codigo, _ = self.rodar([exe, "-c", "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 11) else 1)"])
        return codigo == 0

    def python_do_agente(self):
        os.makedirs(self.destino, exist_ok=True)
        self.fechar_o_agente()  # reinstalação: o agente aberto prende os arquivos
        if self._python_pronto():
            self.detalhe("Já estava instalado em " + os.path.join(self.destino, "python"))
            return
        instalador = os.path.join(tempfile.gettempdir(), f"mathecafe-python-{PY_VERSAO}-amd64.exe")
        url = f"https://www.python.org/ftp/python/{PY_VERSAO}/python-{PY_VERSAO}-amd64.exe"
        self.baixar(url, instalador)
        self.detalhe("Instalando o Python (1 a 3 minutos)")
        self.avisar("progresso_passo", None)  # sem porcentagem: barra correndo
        alvo = os.path.join(self.destino, "python")
        self.rodar([instalador, "/quiet", "InstallAllUsers=1", f"TargetDir={alvo}", "Include_launcher=0",
                    "InstallLauncherAllUsers=0", "PrependPath=0", "Shortcuts=0", "AssociateFiles=0",
                    "Include_test=0", "Include_doc=0", "Include_tcltk=1", "Include_pip=1", "CompileAll=0"])
        try:
            os.remove(instalador)
        except OSError:
            pass
        if self.simular:
            return
        if not os.path.exists(os.path.join(alvo, "python.exe")):
            # a mesma versão já estava em outro lugar: o instalador só "modifica" aquela
            self.copiar_python_existente(alvo)
        if not self._python_pronto():
            raise ErroDeInstalacao(f"O Python não ficou pronto em {alvo}.\nInstale o Python {PY_VERSAO} "
                                   "pelo python.org (com tcl/tk) e rode o instalador de novo.")

    def baixar(self, url, arquivo):
        """Download com porcentagem pelo proxy do Windows; se falhar, pelo PowerShell (proxy com PAC)."""
        self.detalhe(f"Baixando o Python {PY_VERSAO} do python.org (cerca de 30 MB)")
        if self.simular:
            for i in range(21):
                time.sleep(0.08)
                self.avisar("progresso_passo", i / 20)
            return
        try:
            with urllib.request.urlopen(url, timeout=30) as r, open(arquivo, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                feito = 0
                while True:
                    bloco = r.read(256 * 1024)
                    if not bloco:
                        break
                    f.write(bloco)
                    feito += len(bloco)
                    if total:
                        self.avisar("progresso_passo", feito / total)
            return
        except (urllib.error.URLError, OSError):
            pass
        self.avisar("progresso_passo", None)
        self.ps("$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol="
                "[Net.SecurityProtocolType]::Tls12; $w=New-Object Net.WebClient; "
                "$w.Proxy=[Net.WebRequest]::GetSystemWebProxy(); "
                "$w.Proxy.Credentials=[Net.CredentialCache]::DefaultCredentials; "
                f"$w.DownloadFile('{url}', '{arquivo}')")
        if not os.path.exists(arquivo):
            raise ErroDeInstalacao("Não foi possível baixar o Python.\n"
                                   "Confira a internet deste PC e o proxy da rede.")

    def copiar_python_existente(self, alvo):
        import winreg
        maior_menor = ".".join(PY_VERSAO.split(".")[:2])
        base = None
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(raiz, rf"SOFTWARE\Python\PythonCore\{maior_menor}\InstallPath") as k:
                    base = winreg.QueryValue(k, None).rstrip("\\")
                    break
            except OSError:
                continue
        if base:
            self.detalhe(f"Copiando o Python que já existia ({base})")
            self.rodar(["robocopy", base, alvo, "/MIR", "/XD", os.path.join(base, "Lib", "site-packages"),
                        "__pycache__", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"])

    def proxy_do_windows(self):
        """O pip não usa o proxy do Windows sozinho: o mesmo do navegador."""
        codigo, saida = self.ps("$u=[Uri]'https://pypi.org/'; $p=[Net.WebRequest]::GetSystemWebProxy().GetProxy($u); "
                                "if ($p.AbsoluteUri -ne $u.AbsoluteUri) { $p.AbsoluteUri.TrimEnd('/') }")
        saida = saida.strip()
        return saida if codigo == 0 and saida.startswith("http") else None

    def agente_e_dependencias(self):
        origem = pasta_embutida()
        os.makedirs(self.destino, exist_ok=True)
        if os.path.normcase(os.path.abspath(origem)) != os.path.normcase(os.path.abspath(self.destino)):
            for nome in ARQUIVOS_DO_AGENTE:
                if os.path.exists(os.path.join(origem, nome)):
                    shutil.copy2(os.path.join(origem, nome), os.path.join(self.destino, nome))
        # a versão liberada no servidor (a do .exe pode ser mais antiga)
        if self.dados.get("servidor_ok"):
            novo = pedir(f"http://{self.dados['servidor']}/api/agente/download", timeout=20)
            if novo and "VERSAO" in novo and "class AgenteApp" in novo:
                with open(os.path.join(self.destino, "agente.py"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(novo)
                self.detalhe("Agente na versão do servidor")
        # uma cópia do instalador fica na pasta: é por ela que se desinstala
        if getattr(sys, "frozen", False):
            copia = os.path.join(self.destino, NOME_DO_EXE)
            if os.path.normcase(sys.executable) != os.path.normcase(copia):
                try:
                    shutil.copy2(sys.executable, copia)
                except OSError:
                    pass
        env = dict(os.environ)
        proxy = None if self.simular else self.proxy_do_windows()
        if proxy:
            self.detalhe("Usando o proxy da rede: " + proxy)
            env["HTTPS_PROXY"] = env["HTTP_PROXY"] = proxy
        venv = os.path.join(self.destino, "venv")
        if os.path.exists(venv) and not self.simular:
            shutil.rmtree(venv, ignore_errors=True)
        self.detalhe("Criando o ambiente do agente")
        codigo, saida = self.rodar([os.path.join(self.destino, "python", "python.exe"), "-m", "venv", venv])
        if codigo != 0:
            raise ErroDeInstalacao(f"Não foi possível criar o ambiente Python em {venv}.\n" + saida.strip()[:300])
        py = os.path.join(venv, "Scripts", "python.exe")
        self.detalhe("Instalando websockets, psutil e Pillow")
        self.rodar([py, "-m", "pip", "install", "--upgrade", "pip", "-q"], env=env)
        codigo, saida = self.rodar([py, "-m", "pip", "install", "-r",
                                    os.path.join(self.destino, "requirements.txt"), "-q"], env=env)
        if codigo != 0:
            raise ErroDeInstalacao("Falha ao instalar as dependências (websockets, psutil, Pillow).\n"
                                   "Confira a internet deste PC e o proxy da rede.\n" + saida.strip()[-300:])

    def configuracao(self):
        caminho = os.path.join(self.destino, "agente.cfg")
        antigo = {}
        try:
            with open(caminho, encoding="utf-8-sig") as f:
                antigo = ler_cfg(f.read())
        except OSError:
            pass
        id_pc = antigo.get("ID")
        piso = self.dados.get("piso")
        if id_pc and piso and self.dados.get("servidor_ok"):
            resposta = pedir(f"http://{self.dados['servidor']}/api/agente/estacao?id={id_pc}") or ""
            if id_para_manter(id_pc, piso, resposta) is None:
                nome_antigo = resposta.split(";", 1)[-1]
                self.avisar("aviso", f"Este PC era a estação {nome_antigo} de outro piso: entra no piso escolhido "
                                     f"como computador novo. A {nome_antigo} antiga fica no mapa (exclua no painel).")
                id_pc = None
        with open(caminho, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(conteudo_cfg(self.dados["servidor"], self.dados["estacao"], id_pc, piso))
        # o agente roda como "cliente" e grava na pasta: agente.cfg e a atualização
        self.rodar(["icacls", self.destino, "/grant", "cliente:(OI)(CI)M", "/T", "/Q"])

    def tarefa(self):
        codigo, saida = self.ps_arquivo("registrar_tarefa.ps1", "-Pasta", self.destino)
        if codigo != 0:
            raise ErroDeInstalacao("Não foi possível criar a tarefa que abre o agente.\n" + saida.strip()[-300:])

    def politicas(self):
        codigo, saida = self.ps_arquivo("registrar_politicas.ps1", "-Pasta", self.destino)
        if codigo != 0:
            raise ErroDeInstalacao("Não foi possível criar a tarefa das políticas (Ctrl+Alt+Del).\n"
                                   + saida.strip()[-300:])
        env = dict(os.environ, MC_SENHA=self.dados["senha"])
        codigo, _ = self.ps_arquivo("politicas_cliente.ps1", env=env)
        if codigo != 0:
            self.avisar("aviso", "As políticas entram no primeiro logon do cliente (pela tarefa).")

    # ── desinstalar ──
    def passos_desinstalar(self):
        return [("Fechar o agente e a sessão do cliente", self.fechar_tudo),
                ("Tirar as tarefas agendadas", self.tirar_tarefas),
                ("Desligar o autologin", self.desligar_autologin),
                ("Remover o Python do agente", self.remover_python),
                ("Apagar o usuário cliente e o perfil", self.apagar_usuario),
                ("Apagar " + DESTINO, self.apagar_pasta)]

    def fechar_tudo(self):
        self.rodar(["schtasks", "/end", "/tn", "MatheCafe-Agente"])
        self.fechar_o_agente()
        # o perfil só sai com o cliente deslogado
        self.ps("foreach ($l in (query user 2>$null)) { if ($l -match '^\\s*>?cliente\\s+(?:\\S+\\s+)?(\\d+)\\s') "
                "{ logoff $Matches[1] } }")
        self.rodar(["taskkill", "/f", "/fi", "USERNAME eq cliente"])

    def tirar_tarefas(self):
        self.rodar(["schtasks", "/delete", "/tn", "MatheCafe-Agente", "/f"])
        self.rodar(["schtasks", "/delete", "/tn", "MatheCafe_Agente", "/f"])
        self.rodar(["schtasks", "/delete", "/tn", "MatheCafe-Politicas", "/f"])

    def desligar_autologin(self):
        chave = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
        self.rodar(["reg", "add", chave, "/v", "AutoAdminLogon", "/t", "REG_SZ", "/d", "0", "/f"])
        self.rodar(["reg", "delete", chave, "/v", "DefaultPassword", "/f"])
        codigo, saida = self.rodar(["reg", "query", chave, "/v", "DefaultUserName"])
        if codigo == 0 and "cliente" in saida.lower().split():
            self.rodar(["reg", "delete", chave, "/v", "DefaultUserName", "/f"])

    def remover_python(self):
        # só o Python registrado na pasta do agente; um que a máquina já tinha fica
        alvo = os.path.join(self.destino, "python")
        if not self.simular and not os.path.exists(os.path.join(alvo, "python.exe")):
            return
        self.ps(f"$alvo = '{alvo}'.TrimEnd('\\'); $nosso = Get-ChildItem 'HKLM:\\SOFTWARE\\Python\\PythonCore' "
                "-ErrorAction SilentlyContinue | Where-Object { ((Get-ItemProperty ($_.PSPath + '\\InstallPath') "
                "-ErrorAction SilentlyContinue).'(default)' -replace '\\\\$','') -ieq $alvo }; if ($nosso) { "
                "$ver = (Get-Item ($alvo + '\\python.exe')).VersionInfo.ProductVersion; $chaves = "
                "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; $pacote = "
                "Get-ItemProperty $chaves -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "
                "('Python ' + $ver + ' (64-bit)') -and $_.QuietUninstallString } | Select-Object -First 1; "
                "if ($pacote) { Start-Process cmd.exe -ArgumentList ('/c ' + $pacote.QuietUninstallString) "
                "-Wait -WindowStyle Hidden } }")

    def apagar_usuario(self):
        self.ps("$u = Get-LocalUser -Name cliente -ErrorAction SilentlyContinue; if ($u) { Get-CimInstance "
                "Win32_UserProfile | Where-Object { $_.SID -eq $u.SID.Value } | Remove-CimInstance "
                "-ErrorAction SilentlyContinue }")
        self.rodar(["net", "user", "cliente", "/delete"])
        if not self.simular and os.path.exists(r"C:\Users\cliente"):
            shutil.rmtree(r"C:\Users\cliente", ignore_errors=True)
            if os.path.exists(r"C:\Users\cliente"):
                self.avisar("aviso", r"C:\Users\cliente ficou: reinicie o PC e desinstale de novo para apagar.")

    def apagar_pasta(self):
        if self.simular:
            time.sleep(0.4)
            return
        shutil.rmtree(self.destino, ignore_errors=True)
        if os.path.exists(self.destino):
            self.avisar("aviso", f"{self.destino} não saiu inteira (arquivo em uso). Reinicie o PC e apague à mão.")

    # ── rodar uma lista de passos ──
    def executar(self, passos):
        for i, (_, funcao) in enumerate(passos):
            self.avisar("passo", i, "fazendo")
            try:
                funcao()
            except ErroDeInstalacao as e:
                self.avisar("passo", i, "erro")
                self.avisar("fim", False, str(e))
                return
            except Exception as e:  # qualquer outra falha também para aqui, com o motivo
                self.avisar("passo", i, "erro")
                self.avisar("fim", False, f"Erro inesperado: {e}")
                return
            self.avisar("passo", i, "ok")
        self.avisar("fim", True, "")


# ════════════════════════════════════════════════════════════════════
#  Peças da tela (desenhadas em Canvas, como no agente)
# ════════════════════════════════════════════════════════════════════

def retangulo(c, x1, y1, x2, y2, r, **opcoes):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pontos = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pontos, smooth=True, **opcoes)


class Botao:
    """Botão rounded-xl: "primario" (azul), "perigo" (rosa) ou "neutro"."""
    CORES = {"primario": (AZUL, AZUL_CLARO, TEXTO_CLARO), "perigo": (ROSA, ROSA_CLARO, TEXTO_CLARO),
             "neutro": (SUPERFICIE, SUPERFICIE2, TEXTO)}

    def __init__(self, pai, texto, comando, tipo="primario", largura=150, altura=40):
        self.texto, self.comando, self.tipo, self.altura = texto, comando, tipo, altura
        self.ativo, self.sobre = True, False
        self.canvas = tk.Canvas(pai, width=largura, height=altura, bg=FUNDO, highlightthickness=0, cursor="hand2")
        self.canvas.bind("<Enter>", lambda e: self._mouse(True))
        self.canvas.bind("<Leave>", lambda e: self._mouse(False))
        self.canvas.bind("<Button-1>", lambda e: self.comando() if self.ativo else None)
        self.desenhar()

    def _mouse(self, sim):
        self.sobre = sim
        self.desenhar()

    def config(self, ativo=None, texto=None):
        if ativo is not None:
            self.ativo = ativo
        if texto is not None:
            self.texto = texto
        self.desenhar()

    def desenhar(self):
        c = self.canvas
        w, h = int(c.cget("width")), self.altura
        c.delete("all")
        normal, hover, cor_texto = self.CORES[self.tipo]
        if not self.ativo:
            fundo, cor_texto = SUPERFICIE2, FRACO
        else:
            fundo = hover if self.sobre else normal
        if self.tipo == "neutro":
            retangulo(c, 0, 0, w - 1, h - 1, 12, fill=BORDA, outline="")
            retangulo(c, 1, 1, w - 2, h - 2, 11, fill=fundo, outline="")
        else:
            retangulo(c, 0, 0, w - 1, h - 1, 12, fill=fundo, outline="")
        c.create_text(w / 2, h / 2, text=self.texto, fill=cor_texto, font=(FONTE, 10, "bold"))
        c.config(cursor="hand2" if self.ativo else "arrow")


class Campo:
    """Campo de texto rounded-xl: borda zinc, azul com o foco (como no login do PC)."""

    def __init__(self, pai, valor="", senha=False, largura=380):
        self.largura = largura
        self.canvas = tk.Canvas(pai, width=largura, height=42, bg=FUNDO, highlightthickness=0)
        self.var = tk.StringVar(value=valor)
        self.entry = tk.Entry(self.canvas, textvariable=self.var, font=(FONTE, 11), bg=SUPERFICIE, fg=TEXTO,
                              insertbackground=TEXTO, relief="flat", highlightthickness=0, show="•" if senha else "")
        self.canvas.create_window(14, 21, window=self.entry, anchor="w", width=largura - 28)
        self.foco = False
        self.entry.bind("<FocusIn>", lambda e: self._foco(True))
        self.entry.bind("<FocusOut>", lambda e: self._foco(False))
        self.desenhar()

    def _foco(self, sim):
        self.foco = sim
        self.desenhar()

    def desenhar(self):
        c, w = self.canvas, self.largura
        c.delete("fundo")
        retangulo(c, 0, 0, w - 1, 41, 12, fill="#1e3a8a" if self.foco else BORDA, outline="", tags="fundo")
        retangulo(c, 1, 1, w - 2, 40, 11, fill=SUPERFICIE, outline="", tags="fundo")
        c.tag_lower("fundo")

    def get(self):
        return self.var.get()


# ════════════════════════════════════════════════════════════════════
#  A janela: menu de etapas à esquerda, página à direita
# ════════════════════════════════════════════════════════════════════

class Instalador:
    LARGURA, ALTURA = 860, 580
    SUBTITULO = "Instalador do agente"  # o do servidor (server/instalador_servidor.py) troca
    ETAPAS_INSTALAR = ["Início", "Servidor", "Estação", "Instalação", "Pronto"]
    ETAPAS_DESINSTALAR = ["Início", "Confirmar", "Desinstalação", "Pronto"]

    def __init__(self):
        global FONTE
        self.root = tk.Tk()
        if "Inter" in tkfont.families():
            FONTE = "Inter"
        self.root.title("MatheCafé - Instalador" + (" (simulação)" if SIMULAR else ""))
        self.root.configure(bg=FUNDO)
        self.root.resizable(False, False)
        x = (self.root.winfo_screenwidth() - self.LARGURA) // 2
        y = (self.root.winfo_screenheight() - self.ALTURA) // 3
        self.root.geometry(f"{self.LARGURA}x{self.ALTURA}+{max(0, x)}+{max(0, y)}")
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)

        self.instalado = None if SIMULAR else cfg_instalado()
        self.modo = "instalar"
        self.etapa = 0
        self.dados = {"servidor": "", "servidor_ok": False, "piso": None, "pisos": [],
                      "estacao": "", "senha": ""}
        self.rodando = False
        self.fila = queue.Queue()

        self.menu = tk.Canvas(self.root, width=230, height=self.ALTURA, bg=SUPERFICIE, highlightthickness=0)
        self.menu.pack(side="left", fill="y")
        self.corpo = tk.Frame(self.root, bg=FUNDO)
        self.corpo.pack(side="left", fill="both", expand=True)
        if DESINSTALAR:
            self.modo = "desinstalar"
            self.pagina_confirmar()
        else:
            self.pagina_inicio()

    # ── estrutura comum ──
    def desenhar_menu(self):
        c = self.menu
        c.delete("all")
        c.create_line(229, 0, 229, self.ALTURA, fill=BORDA)
        retangulo(c, 24, 26, 58, 60, 10, fill=AZUL, outline="")
        c.create_text(41, 43, text="M", fill=TEXTO_CLARO, font=(FONTE, 13, "bold"))
        c.create_text(70, 35, anchor="w", text="MatheCafé", fill=TEXTO, font=(FONTE, 11, "bold"))
        c.create_text(70, 52, anchor="w", text=self.SUBTITULO, fill=TEXTO2, font=(FONTE, 8))
        c.create_text(24, 104, anchor="w", text="DESINSTALAR" if self.modo == "desinstalar" else "INSTALAR",
                      fill=FRACO, font=(FONTE, 7, "bold"))
        etapas = self.ETAPAS_DESINSTALAR if self.modo == "desinstalar" else self.ETAPAS_INSTALAR
        for i, nome in enumerate(etapas):
            y = 136 + i * 44
            if i < self.etapa:
                c.create_oval(24, y - 11, 46, y + 11, fill=EMERALD, outline="")
                c.create_text(35, y, text="\u2713", fill=FUNDO, font=(FONTE, 9, "bold"))
                cor = TEXTO2
            elif i == self.etapa:
                retangulo(c, 14, y - 18, 214, y + 18, 12, fill="#172554", outline="")
                c.create_oval(24, y - 11, 46, y + 11, fill=AZUL, outline="")
                c.create_text(35, y, text=str(i + 1), fill=TEXTO_CLARO, font=(FONTE, 8, "bold"))
                cor = TEXTO
            else:
                c.create_oval(24, y - 11, 46, y + 11, fill="", outline=SUPERFICIE2, width=2)
                c.create_text(35, y, text=str(i + 1), fill=FRACO, font=(FONTE, 8, "bold"))
                cor = FRACO
            if i < len(etapas) - 1:
                c.create_line(35, y + 13, 35, y + 31, fill=EMERALD if i < self.etapa else SUPERFICIE2, width=2)
            c.create_text(58, y, anchor="w", text=nome, fill=cor,
                          font=(FONTE, 10, "bold" if i == self.etapa else "normal"))
        c.create_text(24, self.ALTURA - 26, anchor="w", text=f"Instalador v{VERSAO_INSTALADOR}" +
                      ("  ·  simulação" if SIMULAR else ""), fill=FRACO, font=("Consolas", 8))

    def nova_pagina(self, etapa, titulo, subtitulo=""):
        self.etapa = etapa
        self.desenhar_menu()
        for w in self.corpo.winfo_children():
            w.destroy()
        area = tk.Frame(self.corpo, bg=FUNDO)
        area.pack(fill="both", expand=True, padx=44, pady=(38, 0))
        tk.Label(area, text=titulo, font=(FONTE, 17, "bold"), fg=TEXTO, bg=FUNDO, anchor="w",
                 justify="left").pack(fill="x")
        if subtitulo:
            tk.Label(area, text=subtitulo, font=(FONTE, 10), fg=TEXTO2, bg=FUNDO, anchor="w", justify="left",
                     wraplength=540).pack(fill="x", pady=(6, 0))
        conteudo = tk.Frame(area, bg=FUNDO)
        conteudo.pack(fill="both", expand=True, pady=(24, 0))
        self.rodape = tk.Frame(self.corpo, bg=FUNDO)
        self.rodape.pack(fill="x", padx=44, pady=(0, 30))
        return conteudo

    def rotulo(self, pai, texto):
        tk.Label(pai, text=texto.upper(), font=(FONTE, 7, "bold"), fg=FRACO, bg=FUNDO).pack(anchor="w", pady=(0, 6))

    def dica(self, pai, texto, cor=FRACO, pady=(6, 14)):
        lbl = tk.Label(pai, text=texto, font=(FONTE, 9), fg=cor, bg=FUNDO, anchor="w", justify="left",
                       wraplength=540)
        lbl.pack(fill="x", pady=pady)
        return lbl

    def lista(self, pai, itens, cor=AZUL_CLARO):
        for item in itens:
            linha = tk.Frame(pai, bg=FUNDO)
            linha.pack(fill="x", pady=4)
            tk.Label(linha, text="\u25CF", font=(FONTE, 7), fg=cor, bg=FUNDO).pack(side="left", padx=(2, 10), anchor="n",
                                                                                pady=4)
            tk.Label(linha, text=item, font=(FONTE, 10), fg=TEXTO, bg=FUNDO, anchor="w", justify="left",
                     wraplength=500).pack(side="left", fill="x")

    def botoes(self, *especificacoes):
        """(texto, comando, tipo) da direita para a esquerda; devolve os Botao."""
        criados = []
        for texto, comando, tipo in especificacoes:
            b = Botao(self.rodape, texto, comando, tipo, largura=max(120, 16 + 9 * len(texto)))
            b.canvas.pack(side="right", padx=(10, 0))
            criados.append(b)
        return criados

    # ── Início ──
    def pagina_inicio(self):
        self.modo = "instalar"
        if not SIMULAR and not sou_administrador():
            pag = self.nova_pagina(0, "Abra como administrador",
                                   "O instalador cria um usuário, liga o autologin e grava tarefas do Windows: "
                                   "só funciona como administrador.")
            self.dica(pag, "Feche e abra de novo com o botão direito \u2192 Executar como administrador.", TEXTO2)
            self.botoes(("Fechar", self.root.destroy, "neutro"))
            return
        if self.instalado:
            pag = self.nova_pagina(0, "Este computador já tem o MatheCafé",
                                   "Dá para reinstalar (atualiza tudo e mantém a estação) ou desinstalar.")
            cartao = tk.Frame(pag, bg=SUPERFICIE, highlightthickness=1, highlightbackground=BORDA)
            cartao.pack(fill="x")
            for chave, valor in (("Estação", self.instalado.get("ESTACAO", "?")),
                                 ("Servidor", normalizar_endereco(self.instalado.get("SERVIDOR", "")) or "?"),
                                 ("Pasta", DESTINO)):
                linha = tk.Frame(cartao, bg=SUPERFICIE)
                linha.pack(fill="x", padx=18, pady=6)
                tk.Label(linha, text=chave, font=(FONTE, 9), fg=TEXTO2, bg=SUPERFICIE, width=10,
                         anchor="w").pack(side="left")
                tk.Label(linha, text=valor, font=(FONTE, 10, "bold"), fg=TEXTO, bg=SUPERFICIE).pack(side="left")
            self.botoes(("Reinstalar", self.pagina_servidor, "primario"),
                        ("Desinstalar", self.ir_para_desinstalar, "perigo"))
            return
        pag = self.nova_pagina(0, "Instalar o MatheCafé neste computador",
                               "Em poucos passos este PC vira uma estação da biblioteca.")
        self.lista(pag, ["Cria o usuário Windows \u201ccliente\u201d, que entra sozinho quando o PC liga",
                         f"Instala o agente em {DESTINO}, com um Python só dele (baixa da internet)",
                         "Abre o agente sozinho e trava o Ctrl+Alt+Del para o cliente",
                         "Liga o PC ao servidor: ele aparece no painel em Mapa \u2192 Novas estações para aprovar"])
        self.botoes(("Começar", self.pagina_servidor, "primario"))

    # ── Servidor e piso ──
    def pagina_servidor(self):
        pag = self.nova_pagina(1, "Servidor", "O endereço do servidor do MatheCafé (IP e porta). "
                                              "O instalador confere na hora se ele responde.")
        self.rotulo(pag, "Endereço do servidor")
        linha = tk.Frame(pag, bg=FUNDO)
        linha.pack(anchor="w")
        sugerido = self.dados["servidor"] or normalizar_endereco((self.instalado or {}).get("SERVIDOR", "")) \
            or servidor_sugerido()
        self.campo_servidor = Campo(linha, sugerido, largura=320)
        self.campo_servidor.canvas.pack(side="left")
        self.campo_servidor.entry.bind("<Return>", lambda e: self.testar_servidor())
        Botao(linha, "Testar", self.testar_servidor, "neutro", largura=100).canvas.pack(side="left", padx=(10, 0))
        self.lbl_teste = self.dica(pag, "Ex.: 10.26.31.77:8000")
        self.area_pisos = tk.Frame(pag, bg=FUNDO)
        self.area_pisos.pack(fill="x")
        self.var_sem_servidor = tk.BooleanVar(value=False)
        self.chk_sem_servidor = None
        self.btn_avancar, = self.botoes(("Avançar", self.pagina_estacao, "primario"))
        Botao(self.rodape, "Voltar", self.pagina_inicio, "neutro", largura=110).canvas.pack(side="left")
        self.btn_avancar.config(ativo=False)
        self.root.after(150, self.testar_servidor)

    def testar_servidor(self):
        endereco = normalizar_endereco(self.campo_servidor.get())
        for w in self.area_pisos.winfo_children():
            w.destroy()
        self.dados.update(servidor=endereco, servidor_ok=False, pisos=[])
        self.btn_avancar.config(ativo=False)
        if not endereco:
            self.lbl_teste.config(text="Digite o endereço do servidor.", fg=ROSA_TEXTO)
            return
        self.lbl_teste.config(text=f"\u25CF  Testando http://{endereco} ...", fg=AMBAR)

        def testar():
            ok = pedir(f"http://{endereco}/health") is not None
            pisos = ler_pisos(pedir(f"http://{endereco}/api/agente/pisos") or "") if ok else []
            self.root.after(0, lambda: self._servidor_testado(endereco, ok, pisos))

        threading.Thread(target=testar, daemon=True).start()

    def _servidor_testado(self, endereco, ok, pisos):
        if not self.root.winfo_exists() or normalizar_endereco(self.campo_servidor.get()) != endereco:
            return
        self.dados.update(servidor_ok=ok, pisos=pisos)
        if ok:
            self.lbl_teste.config(text="\u25CF  O servidor respondeu.", fg=EMERALD_TEXTO)
            self.mostrar_pisos(pisos)
        else:
            self.lbl_teste.config(text=f"\u25CF  O servidor não respondeu em http://{endereco}. Confira o endereço, "
                                       "se ele está ligado e se este PC está na rede.", fg=ROSA_TEXTO)
            self.var_sem_servidor.set(False)
            tk.Checkbutton(self.area_pisos, text="Continuar assim mesmo (o PC aparece no painel quando conseguir "
                                                 "falar com o servidor)", variable=self.var_sem_servidor,
                           command=self.conferir_avancar, font=(FONTE, 9), fg=TEXTO2, bg=FUNDO,
                           selectcolor=SUPERFICIE, activebackground=FUNDO, activeforeground=TEXTO,
                           wraplength=520, justify="left", anchor="w").pack(fill="x")
        self.conferir_avancar()

    def mostrar_pisos(self, pisos):
        if not pisos:
            self.dados["piso"] = None
            return
        antigo = (self.instalado or {}).get("PISO")
        if self.dados["piso"] not in [p for p, _ in pisos]:
            self.dados["piso"] = antigo if antigo in [p for p, _ in pisos] else (pisos[0][0] if len(pisos) == 1 else None)
        self.rotulo(self.area_pisos, "Em qual piso fica este computador?")
        fila = tk.Frame(self.area_pisos, bg=FUNDO)
        fila.pack(anchor="w")
        self._pilulas_piso = []
        for pid, nome in pisos:
            cv = tk.Canvas(fila, width=max(110, 34 + 9 * len(nome)), height=40, bg=FUNDO, highlightthickness=0,
                           cursor="hand2")
            cv.pack(side="left", padx=(0, 10))
            cv.bind("<Button-1>", lambda e, p=pid: self.escolher_piso(p))
            self._pilulas_piso.append((pid, nome, cv))
        self.pintar_pisos()
        self.dica(self.area_pisos, "O mesmo nome pode existir no Adulto e no Infantil: o piso diz de qual mapa é "
                                   "este PC.")

    def pintar_pisos(self):
        for pid, nome, cv in self._pilulas_piso:
            cv.delete("all")
            w = int(cv.cget("width"))
            if pid == self.dados["piso"]:
                retangulo(cv, 0, 0, w - 1, 39, 12, fill=AZUL, outline="")
                cor = TEXTO_CLARO
            else:
                retangulo(cv, 0, 0, w - 1, 39, 12, fill=BORDA, outline="")
                retangulo(cv, 1, 1, w - 2, 38, 11, fill=SUPERFICIE, outline="")
                cor = TEXTO2
            cv.create_text(w / 2, 20, text=nome, fill=cor, font=(FONTE, 10, "bold"))

    def escolher_piso(self, pid):
        self.dados["piso"] = pid
        self.pintar_pisos()
        self.conferir_avancar()

    def conferir_avancar(self):
        if self.dados["servidor_ok"]:
            pronto = not self.dados["pisos"] or self.dados["piso"] is not None
        else:
            pronto = self.var_sem_servidor.get()
            self.dados["piso"] = None
        self.btn_avancar.config(ativo=pronto)

    # ── Estação e senha ──
    def pagina_estacao(self):
        pag = self.nova_pagina(2, "Estação", "O nome deste PC no painel e a senha da conta Windows do cliente.")
        padrao = (self.instalado or {}).get("ESTACAO") or os.environ.get("COMPUTERNAME", "PC")
        self.rotulo(pag, "Nome da estação")
        self.campo_nome = Campo(pag, self.dados["estacao"] or padrao)
        self.campo_nome.canvas.pack(anchor="w")
        self.dica(pag, "Até 20 caracteres. Dá para trocar depois no painel.")
        self.rotulo(pag, "Senha do usuário cliente")
        self.campo_senha = Campo(pag, self.dados["senha"], senha=True)
        self.campo_senha.canvas.pack(anchor="w")
        self.dica(pag, "O PC entra sozinho com essa conta quando liga.", pady=(6, 10))
        self.rotulo(pag, "Repita a senha")
        self.campo_senha2 = Campo(pag, self.dados["senha"], senha=True)
        self.campo_senha2.canvas.pack(anchor="w")
        self.lbl_erro = self.dica(pag, "", ROSA_TEXTO, pady=(8, 0))
        self.campo_senha2.entry.bind("<Return>", lambda e: self.comecar_instalacao())
        self.botoes(("Instalar", self.comecar_instalacao, "primario"))
        Botao(self.rodape, "Voltar", self.pagina_servidor, "neutro", largura=110).canvas.pack(side="left")
        self.campo_senha.entry.focus_set()

    def comecar_instalacao(self):
        problema = problema_na_senha(self.campo_senha.get(), self.campo_senha2.get())
        if problema:
            self.lbl_erro.config(text=problema)
            return
        self.dados["estacao"] = nome_da_estacao(self.campo_nome.get(), os.environ.get("COMPUTERNAME", "PC"))
        self.dados["senha"] = self.campo_senha.get()
        self.execucao = self.nova_execucao()
        self.pagina_execucao(3, "Instalando", "Pode levar alguns minutos (o Python vem da internet). "
                                              "Não desligue o computador.", self.execucao.passos_instalar(),
                             self.pagina_pronto)

    def nova_execucao(self):
        """Cada execução marca os seus avisos: os de uma anterior que ainda
        estejam na fila são ignorados."""
        self.geracao = getattr(self, "geracao", 0) + 1
        geracao = self.geracao
        return Execucao(self.dados, lambda *a: self.fila.put((geracao,) + a), simular=SIMULAR)

    # ── Desinstalar ──
    def ir_para_desinstalar(self):
        # rodando de dentro de C:\MatheCafe: a pasta será apagada; continua de uma cópia
        if getattr(sys, "frozen", False) and os.path.normcase(sys.executable).startswith(
                os.path.normcase(DESTINO) + "\\"):
            copia = os.path.join(tempfile.gettempdir(), NOME_DO_EXE)
            try:
                shutil.copy2(sys.executable, copia)
                subprocess.Popen([copia, "--desinstalar"], creationflags=SEM_JANELA)
                self.root.destroy()
                return
            except OSError:
                pass
        self.modo = "desinstalar"
        self.pagina_confirmar()

    def pagina_confirmar(self):
        pag = self.nova_pagina(1, "Desinstalar o MatheCafé", "Deixa o PC como antes da instalação.")
        self.dica(pag, "Isto vai apagar deste computador:", TEXTO2, pady=(0, 6))
        self.lista(pag, ["O usuário Windows \u201ccliente\u201d e tudo o que está no perfil dele",
                         f"A pasta {DESTINO} (agente, Python do agente e configuração)",
                         "O início automático do agente e o autologin"], cor=ROSA_TEXTO)
        self.dica(pag, "A estação continua cadastrada no painel. Para reinstalar com o mesmo nome, exclua a "
                       "estação no Mapa ou use \u201cSubstitui a X\u201d em Novas estações.", pady=(14, 14))
        self.var_entendi = tk.BooleanVar(value=False)
        tk.Checkbutton(pag, text="Entendi: o usuário cliente e os arquivos dele serão apagados",
                       variable=self.var_entendi, command=lambda: self.btn_desinstalar.config(
                           ativo=self.var_entendi.get()), font=(FONTE, 10), fg=TEXTO, bg=FUNDO,
                       selectcolor=SUPERFICIE, activebackground=FUNDO, activeforeground=TEXTO).pack(anchor="w")
        self.btn_desinstalar, = self.botoes(("Desinstalar tudo", self.comecar_desinstalacao, "perigo"))
        self.btn_desinstalar.config(ativo=False)
        if not DESINSTALAR:
            Botao(self.rodape, "Voltar", self.pagina_inicio, "neutro", largura=110).canvas.pack(side="left")

    def comecar_desinstalacao(self):
        self.execucao = self.nova_execucao()
        self.pagina_execucao(2, "Desinstalando", "Fechando o agente e apagando o que a instalação criou.",
                             self.execucao.passos_desinstalar(), self.pagina_desinstalado)

    # ── Execução (instalar ou desinstalar) ──
    def pagina_execucao(self, etapa, titulo, subtitulo, passos, ao_terminar):
        pag = self.nova_pagina(etapa, titulo, subtitulo)
        self.passos, self.ao_terminar = passos, ao_terminar
        self.estados = ["espera"] * len(passos)
        self.progresso_passo = 0.0
        self.avisos = []
        self.cv_passos = tk.Canvas(pag, width=560, height=len(passos) * 34, bg=FUNDO, highlightthickness=0)
        self.cv_passos.pack(anchor="w")
        self.cv_barra = tk.Canvas(pag, width=560, height=8, bg=FUNDO, highlightthickness=0)
        self.cv_barra.pack(anchor="w", pady=(18, 8))
        self.lbl_detalhe = tk.Label(pag, text="", font=(FONTE, 9), fg=TEXTO2, bg=FUNDO, anchor="w",
                                    justify="left", wraplength=560)
        self.lbl_detalhe.pack(fill="x")
        self.lbl_resultado = tk.Label(pag, text="", font=(FONTE, 9), fg=ROSA_TEXTO, bg=FUNDO, anchor="w",
                                      justify="left", wraplength=560)
        self.lbl_resultado.pack(fill="x", pady=(8, 0))
        self.fase = 0
        self.desenhar_passos()
        self.rodando = True
        threading.Thread(target=self.execucao.executar, args=(passos,), daemon=True).start()
        self.root.after(60, self.ler_fila)

    def desenhar_passos(self):
        c = self.cv_passos
        c.delete("all")
        for i, (nome, _) in enumerate(self.passos):
            y = 17 + i * 34
            estado = self.estados[i]
            if estado == "ok":
                c.create_oval(2, y - 10, 22, y + 10, fill=EMERALD, outline="")
                c.create_text(12, y, text="\u2713", fill=FUNDO, font=(FONTE, 9, "bold"))
                cor = TEXTO2
            elif estado == "fazendo":
                c.create_oval(2, y - 10, 22, y + 10, outline=SUPERFICIE2, width=2)
                inicio = (self.fase * 12) % 360
                c.create_arc(2, y - 10, 22, y + 10, start=inicio, extent=100, style="arc", outline=AZUL_CLARO,
                             width=2)
                cor = TEXTO
            elif estado == "erro":
                c.create_oval(2, y - 10, 22, y + 10, fill=ROSA, outline="")
                c.create_text(12, y, text="\u2715", fill=TEXTO_CLARO, font=(FONTE, 8, "bold"))
                cor = ROSA_TEXTO
            else:
                c.create_oval(3, y - 9, 21, y + 9, outline=SUPERFICIE2, width=2)
                cor = FRACO
            c.create_text(36, y, anchor="w", text=nome, fill=cor,
                          font=(FONTE, 10, "bold" if estado == "fazendo" else "normal"))
        # barra: passos prontos + o pedaço do passo atual
        b = self.cv_barra
        b.delete("all")
        retangulo(b, 0, 0, 559, 7, 4, fill=SUPERFICIE2, outline="")
        feitos = sum(1 for e in self.estados if e == "ok")
        if self.progresso_passo is None:  # sem porcentagem: um trecho correndo no passo atual
            parte = 0.5
        else:
            parte = self.progresso_passo if "fazendo" in self.estados else 0
        total = (feitos + parte) / len(self.passos)
        if total > 0:
            retangulo(b, 0, 0, max(8, 559 * total), 7, 4, fill=EMERALD if total >= 1 else AZUL, outline="")

    def ler_fila(self):
        if not self.root.winfo_exists():
            return
        try:
            while True:
                geracao, *aviso = self.fila.get_nowait()
                if geracao != self.geracao:
                    continue
                tipo = aviso[0]
                if tipo == "passo":
                    _, i, estado = aviso
                    self.estados[i] = estado
                    self.progresso_passo = 0.0
                    if estado == "fazendo":
                        self.lbl_detalhe.config(text="")
                elif tipo == "detalhe":
                    self.lbl_detalhe.config(text=aviso[1])
                elif tipo == "progresso_passo":
                    self.progresso_passo = aviso[1]
                    if aviso[1] is not None and "Baixando" in self.lbl_detalhe.cget("text"):
                        base = self.lbl_detalhe.cget("text").split("  ·  ")[0]
                        self.lbl_detalhe.config(text=f"{base}  ·  {int(aviso[1] * 100)}%")
                elif tipo == "aviso":
                    self.avisos.append(aviso[1])
                    self.lbl_resultado.config(text="\n".join("\u26A0  " + a for a in self.avisos), fg=AMBAR)
                elif tipo == "fim":
                    self.rodando = False
                    self.desenhar_passos()
                    if aviso[1]:
                        self.root.after(500, self.ao_terminar)
                    else:
                        self.mostrar_erro(aviso[2])
                    return
        except queue.Empty:
            pass
        self.fase += 1
        self.desenhar_passos()
        self.root.after(60, self.ler_fila)

    def mostrar_erro(self, mensagem):
        self.lbl_detalhe.config(text="")
        texto = "\n".join("\u26A0  " + a for a in self.avisos)
        self.lbl_resultado.config(text=(texto + "\n\n" if texto else "") + mensagem, fg=ROSA_TEXTO)
        for w in self.rodape.winfo_children():
            w.destroy()
        de_novo = self.comecar_instalacao_de_novo if self.modo == "instalar" else self.comecar_desinstalacao
        self.botoes(("Tentar de novo", de_novo, "primario"), ("Fechar", self.root.destroy, "neutro"))

    def comecar_instalacao_de_novo(self):
        self.execucao = self.nova_execucao()
        self.pagina_execucao(3, "Instalando", "Os passos que já estavam prontos são refeitos sem problema.",
                             self.execucao.passos_instalar(), self.pagina_pronto)

    # ── Pronto ──
    def pagina_pronto(self):
        pag = self.nova_pagina(4, "Instalação concluída", f"A estação {self.dados['estacao']} está pronta.")
        passos = ["Reinicie o PC: ele entra sozinho como \u201ccliente\u201d e o agente abre"]
        if self.dados["servidor_ok"]:
            passos.append(f"No painel, em Mapa \u2192 Novas estações, aprove \u201c{self.dados['estacao']}\u201d e "
                          "escolha o mapa (se já existir no mapa do piso, entra direto nela)")
        else:
            passos.append("Quando o servidor responder, o PC aparece no painel em Mapa \u2192 Novas estações")
        passos.append(f"Para desinstalar: {DESTINO}\\{NOME_DO_EXE} (como administrador)")
        self.lista(pag, passos, cor=EMERALD_TEXTO)
        if self.avisos:
            self.dica(pag, "\n".join("\u26A0  " + a for a in self.avisos), AMBAR, pady=(16, 0))
        self.botoes(("Reiniciar agora", self.reiniciar, "primario"), ("Fechar", self.root.destroy, "neutro"))

    def pagina_desinstalado(self):
        pag = self.nova_pagina(3, "Desinstalado", "O MatheCafé saiu deste computador.")
        self.lista(pag, ["Reinicie o PC para terminar de limpar",
                         "A estação continua no painel (Mapa): exclua lá se o PC não vai voltar"], cor=EMERALD_TEXTO)
        if self.avisos:
            self.dica(pag, "\n".join("\u26A0  " + a for a in self.avisos), AMBAR, pady=(16, 0))
        self.botoes(("Reiniciar agora", self.reiniciar, "primario"), ("Fechar", self.root.destroy, "neutro"))

    def reiniciar(self):
        if not SIMULAR:
            subprocess.Popen(["shutdown", "/r", "/t", "5"], creationflags=SEM_JANELA)
        self.root.destroy()

    def fechar(self):
        if self.rodando:
            return  # no meio dos passos não fecha (deixaria o PC pela metade)
        self.root.destroy()

    def rodar(self):
        self.root.mainloop()


if __name__ == "__main__":
    Instalador().rodar()
