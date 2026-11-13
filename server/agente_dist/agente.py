"""
MatheCafé - Agente da Estação

Conecta a estação ao servidor via WebSocket e oferece:
- Tela de login do cliente
- Countdown da sessão
- Encerramento manual ou automático (tempo esgotado)
- Launcher de apps com grade visual
- Modo manutenção autenticado pelo servidor (Ctrl+Shift+M)
- Log de comunicação enviado ao servidor (painel > estação > Log)

Uso:
    python agente.py --servidor ws://localhost:8000 --estacao PC-01
    python agente.py --servidor wss://mathecafe.onrender.com --estacao PC-01

IMPORTANTE:
- A estação precisa estar cadastrada no painel com o MESMO NOME de --estacao.
- Rode como Administrador para que o bloqueio de processos funcione.
"""
# Versao do agente — incrementar a cada publicacao de update.
# Unica declaracao: o servidor le a primeira linha VERSAO deste arquivo.
VERSAO = "1.24.0"

import asyncio
import json
import threading
import queue
import argparse
import time
import os
import subprocess
import ctypes
import atexit
import hashlib
import re
import math
import hmac
from datetime import datetime
from io import BytesIO
import urllib.parse
import uuid
import webbrowser
import urllib.request
import sys
import traceback
from collections import deque
import tkinter as tk
from tkinter import font as tkfont, simpledialog

# Com pythonw (tarefa agendada) não há console: qualquer erro fatal vai para
# agente_erro.log, ao lado deste arquivo, e aparece numa janela.
ARQUIVO_ERRO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agente_erro.log")


def registrar_erro(tipo, valor, tb, mostrar=True):
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    try:
        with open(ARQUIVO_ERRO, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{texto}")
    except OSError:
        pass
    if not mostrar:
        return
    try:
        from tkinter import messagebox
        messagebox.showerror("MatheCafe - erro no agente",
                             f"{valor}\n\nDetalhes em:\n{ARQUIVO_ERRO}")
    except Exception:
        pass


sys.excepthook = registrar_erro


def servidor_na_rede_local(url: str) -> bool:
    """localhost, nome sem ponto ou IP privado (10.x, 172.16-31.x, 192.168.x)."""
    import ipaddress
    host = urllib.parse.urlsplit(url).hostname or ""
    if host == "localhost" or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # nome de domínio, ex.: mathecafe.onrender.com
    return ip.is_private or ip.is_loopback


# O Windows aplica o proxy do usuário a tudo, inclusive a IPs internos: o
# usuário "cliente" da rede da biblioteca nunca chegava ao servidor.
_SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def abrir_url(url, timeout):
    if servidor_na_rede_local(url):
        return _SEM_PROXY.open(url, timeout=timeout)
    return urllib.request.urlopen(url, timeout=timeout)

import websockets
import psutil

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def carregar_imagem_url(url, largura=160, altura=140):
    if not PIL_AVAILABLE:
        return None
    try:
        with abrir_url(url, timeout=5) as response:
            data = response.read()
        img = Image.open(BytesIO(data))
        img = img.resize((largura, altura), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def icone_do_app(dados, lado, raio, fundo):
    """Ícone do dock a partir da capa do app: o quadrado do centro da imagem, de
    cantos arredondados, já aplicado sobre a cor do fundo do dock (a janela do
    dock é transparente por cor-chave: uma borda semitransparente ficaria com
    franja). Devolve uma imagem PIL RGB de lado x lado, ou None."""
    if not PIL_AVAILABLE or not dados:
        return None
    try:
        img = Image.open(BytesIO(dados)).convert("RGBA")
        menor = min(img.width, img.height)
        x0, y0 = (img.width - menor) // 2, (img.height - menor) // 2
        escala = 4  # desenha grande e reduz: cantos lisos
        img = img.crop((x0, y0, x0 + menor, y0 + menor)).resize((lado * escala, lado * escala), Image.LANCZOS)
        mascara = Image.new("L", img.size, 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, img.width - 1, img.height - 1), raio * escala, fill=255)
        base = Image.new("RGBA", img.size, fundo)
        base.paste(img, (0, 0), mascara)
        return base.convert("RGB").resize((lado, lado), Image.LANCZOS)
    except Exception:
        return None


# Processos essenciais do Windows — NUNCA serão encerrados.
PROCESSOS_SEGUROS = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe", "ctfmon.exe",
    "taskhostw.exe", "sihost.exe", "runtimebroker.exe", "shellexperiencehost.exe",
    "searchhost.exe", "searchapp.exe", "startmenuexperiencehost.exe",
    "applicationframehost.exe", "textinputhost.exe", "dllhost.exe",
    "audiodg.exe", "spoolsv.exe", "wmiprvse.exe", "conhost.exe",
    "securityhealthsystray.exe", "securityhealthservice.exe",
    "nvcontainer.exe", "nvdisplay.container.exe",
    "python.exe", "pythonw.exe",
}

# Processos sempre bloqueados durante a sessão (terminais, interpretadores).
PROCESSOS_SEMPRE_BLOQUEADOS = {
    "cmd.exe", "powershell.exe", "powershell_ise.exe",
    "wt.exe",
    "mshta.exe", "wscript.exe", "cscript.exe",
    "regedit.exe", "taskmgr.exe",
}

# Encerrados também na tela de login (fora do modo manutenção)
PROCESSOS_BLOQUEADOS_NO_LOGIN = {"taskmgr.exe"}

# Processos seguros que hospedam janelas de apps: fecha-se a janela, não o
# processo (explorer.exe é a área de trabalho; o ApplicationFrameHost é a
# moldura de Configurações, Calculadora e dos apps da Loja)
JANELAS_DE_PROCESSOS_SEGUROS = {
    "explorer.exe": ("CabinetWClass", "Explorador de Arquivos"),
    "applicationframehost.exe": ("ApplicationFrameWindow", "app do Windows"),
}


# ── Meus arquivos (9.5): os downloads da sessão ─────────────────────────────
# Só documentos e imagens abrem pela tela (executáveis e scripts só aparecem
# para excluir; mesmo que rodassem, a whitelist os encerraria).
EXTENSOES_DOCUMENTOS = {
    ".pdf", ".txt", ".rtf", ".csv",
    ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
}


def pasta_downloads():
    """Pasta Downloads do usuário (a do Windows, mesmo se foi movida)."""
    try:
        guid = (ctypes.c_byte * 16).from_buffer_copy(
            bytes.fromhex("90E24D373F126545916439C4925E467B"))  # FOLDERID_Downloads
        caminho = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(caminho)) == 0:
            pasta = caminho.value
            ctypes.windll.ole32.CoTaskMemFree(caminho)
            if pasta:
                return pasta
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


# Vigia do Explorador (9.5): o cliente usa a pasta Downloads no Explorador de
# verdade; este PowerShell escondido (COM Shell.Application, que o Windows ja
# tem) traz de volta para Downloads qualquer janela que saia dela. Termina
# sozinho se o agente cair.
def script_vigia(pasta, pid_agente):
    pasta_ps = pasta.rstrip("\\").replace("'", "''")
    return f"""
$pasta = '{pasta_ps}'
$shell = New-Object -ComObject Shell.Application
while ($true) {{
    if (-not (Get-Process -Id {int(pid_agente)} -ErrorAction SilentlyContinue)) {{ exit }}
    foreach ($w in @($shell.Windows())) {{
        try {{
            if ($w.FullName -notlike '*explorer.exe') {{ continue }}
            $p = $w.Document.Folder.Self.Path
            if (-not $p -or -not ($p -ieq $pasta -or $p.StartsWith($pasta + '\\', [StringComparison]::OrdinalIgnoreCase))) {{
                $w.Navigate2($pasta)
            }}
        }} catch {{}}
    }}
    Start-Sleep -Milliseconds 500
}}
"""


def iniciar_vigia(pasta):
    """Sobe o vigia (sem janela) e devolve o processo."""
    import base64
    codigo = base64.b64encode(script_vigia(pasta, os.getpid()).encode("utf-16-le")).decode("ascii")
    return subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", codigo],
        creationflags=0x08000000)  # CREATE_NO_WINDOW


def listar_arquivos(pasta):
    """Arquivos da pasta (sem subpastas, ocultos ou downloads pela metade), mais novos primeiro."""
    arquivos = []
    try:
        entradas = list(os.scandir(pasta))
    except OSError:
        return arquivos
    for e in entradas:
        nome = e.name
        if not e.is_file() or nome.lower() in ("desktop.ini", "thumbs.db") or nome.startswith((".", "~$")):
            continue
        if nome.lower().endswith((".crdownload", ".part", ".tmp", ".partial")):
            continue
        try:
            info = e.stat()
        except OSError:
            continue
        arquivos.append({"nome": nome, "caminho": e.path, "tamanho": info.st_size, "quando": info.st_mtime})
    return sorted(arquivos, key=lambda a: a["quando"], reverse=True)


def limpar_pasta(pasta):
    """Apaga tudo dentro da pasta (não a pasta). Recusa a pasta do usuário, as
    de cima dela e a raiz do disco. Devolve quantos itens apagou."""
    import shutil
    pasta = os.path.normpath(os.path.abspath(pasta))
    casa = os.path.normpath(os.path.expanduser("~")).lower()
    if not os.path.isdir(pasta) or os.path.dirname(pasta) == pasta or casa.startswith(pasta.lower()):
        return 0
    apagados = 0
    for e in list(os.scandir(pasta)):
        try:
            if e.is_dir(follow_symlinks=False):
                shutil.rmtree(e.path)
            else:
                os.remove(e.path)
            apagados += 1
        except OSError:
            continue  # em uso: fica para a próxima limpeza
    return apagados


def pode_abrir_arquivo(nome):
    return os.path.splitext(nome)[1].lower() in EXTENSOES_DOCUMENTOS


def tamanho_legivel(n):
    if n < 1024 * 1024:
        return f"{max(1, round(n / 1024))} KB"
    return f"{n / (1024 * 1024):.1f} MB".replace(".", ",")


def programa_que_abre(caminho):
    """Executável que o Windows usa para abrir o arquivo (None se nenhum)."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        r = ctypes.windll.shell32.FindExecutableW(caminho, None, buf)
        return buf.value if r > 32 and buf.value else None
    except Exception:
        return None


# ── Janelas abertas ──────────────────────────────────────────────────────────
try:
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    _u32.EnumWindows.argtypes = [_WNDENUMPROC, ctypes.c_void_p]
    _u32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _u32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    _u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    _u32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _u32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _u32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    _u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    from ctypes import wintypes as _wt
    _u32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    _u32.FindWindowW.restype = ctypes.c_void_p
    _u32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    _u32.FindWindowExW.restype = ctypes.c_void_p
    _u32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_wt.RECT)]
    _u32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _u32.IsIconic.argtypes = [ctypes.c_void_p]
    _u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    _u32.GetForegroundWindow.restype = ctypes.c_void_p
    _dwm = ctypes.WinDLL("dwmapi")
    _dwm.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
except (AttributeError, OSError):
    _u32 = None  # fora do Windows


def _camuflada(hwnd):
    """Janela "visível" que o usuário não vê (app UWP suspenso, Iniciar, Widgets)."""
    valor = ctypes.c_int(0)
    _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(valor), ctypes.sizeof(valor))  # DWMWA_CLOAKED
    return valor.value != 0


def janelas_visiveis():
    """{pid: [(hwnd, classe), ...]} das janelas de primeiro nível visíveis e com título."""
    resultado = {}
    if _u32 is None:
        return resultado

    def _cada(hwnd, _):
        if _u32.IsWindowVisible(hwnd) and _u32.GetWindowTextLengthW(hwnd) > 0 and not _camuflada(hwnd):
            pid = ctypes.c_ulong()
            _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            classe = ctypes.create_unicode_buffer(256)
            _u32.GetClassNameW(hwnd, classe, 256)
            resultado.setdefault(pid.value, []).append((hwnd, classe.value))
        return True

    _u32.EnumWindows(_WNDENUMPROC(_cada), None)
    return resultado


def fechar_janela(hwnd):
    _u32.PostMessageW(hwnd, 0x0010, None, None)  # WM_CLOSE


def botoes_janela(hwnd, ativo):
    """Mostra ou tira os botões de minimizar e maximizar/restaurar e a borda de
    redimensionar: na sessão o cliente não pode diminuir o agente."""
    if _u32 is None:
        return
    GWL_STYLE = -16
    WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_THICKFRAME = 0x00020000, 0x00010000, 0x00040000
    travados = WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_THICKFRAME
    estilo = _u32.GetWindowLongW(hwnd, GWL_STYLE)
    estilo = estilo | travados if ativo else estilo & ~travados
    _u32.SetWindowLongW(hwnd, GWL_STYLE, estilo)
    # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED: redesenha a moldura
    _u32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)


# ── Barra de tarefas do Windows e janelas dos apps ───────────────────────────
# Na sessão a barra do Windows some (sem Iniciar) e a do MatheCafé fica no
# lugar dela. O espaço que o Windows reserva para a barra continua reservado,
# então um app maximizado para em cima da nossa barra em vez de cobri-la.
def _barras_do_windows():
    if _u32 is None:
        return []
    barras = []
    principal = _u32.FindWindowW("Shell_TrayWnd", None)
    if principal:
        barras.append(principal)
    outra = None
    while True:  # uma por monitor a mais
        outra = _u32.FindWindowExW(None, outra, "Shell_SecondaryTrayWnd", None)
        if not outra:
            break
        barras.append(outra)
    return barras


def barra_do_windows(visivel):
    for h in _barras_do_windows():
        _u32.ShowWindow(h, 5 if visivel else 0)  # SW_SHOW / SW_HIDE


def barra_do_windows_visivel():
    return any(_u32.IsWindowVisible(h) for h in _barras_do_windows())


def area_da_barra_do_windows():
    """(x, y, largura, altura) da barra principal do Windows, ou None."""
    h = _u32.FindWindowW("Shell_TrayWnd", None) if _u32 else None
    if not h:
        return None
    r = _wt.RECT()
    _u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def titulo_da_janela(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def trazer_para_frente(hwnd):
    if _u32.IsIconic(hwnd):
        _u32.ShowWindow(hwnd, 9)  # SW_RESTORE
    _u32.SetForegroundWindow(hwnd)


def janela_em_foco():
    return _u32.GetForegroundWindow() if _u32 else None


# ── Tema (o cliente escolhe na tela do agente) ───────────────────────────────
# Mesmas chaves nas duas; dentro de cada uma, sem cores repetidas (a troca
# substitui cada cor da paleta antiga pela da nova, widget por widget).
PALETAS = {
    # tokens Zinc (9.11): fundo zinc-950 / cards zinc-900 no escuro; zinc-50 / branco no claro
    "escuro": {
        "fundo": "#09090b", "superficie": "#18181b", "superficie2": "#27272a", "superficie3": "#3f3f46",
        "borda": "#222226", "texto": "#e4e4e7", "texto2": "#a1a1aa", "fraco": "#71717a",
        "destaque": "#6366f1", "destaque_forte": "#4f46e5",
    },
    "claro": {
        "fundo": "#fafafa", "superficie": "#ffffff", "superficie2": "#f4f4f5", "superficie3": "#d4d4d8",
        "borda": "#e4e4e7", "texto": "#27272a", "texto2": "#52525b", "fraco": "#8b8b94",
        "destaque": "#4f46e5", "destaque_forte": "#4338ca",
    },
}
ROTULO_TEMA = {"escuro": "☀  Tema claro", "claro": "☾  Tema escuro"}
# o computador acima do login: conectando, online, offline
COR_CONECTANDO, COR_ONLINE, COR_OFFLINE = "#f97316", "#22c55e", "#ef4444"
# acabamento da Área do Cliente (9.12, padrão shadcn): sem branco puro nem vermelho vivo
ZINC_950, ZINC_900 = "#09090b", "#18181b"
AZUL, AZUL_CLARO = "#2563eb", "#3b82f6"  # blue-600 / blue-500: Abrir, banner, contador
ROSA, ROSA_CLARO, ROSA_TEXTO = "#e11d48", "#f43f5e", "#fb7185"  # Encerrar sessão
TEXTO_CLARO = "#f4f4f5"  # zinc-100, no lugar do branco puro
EMERALD, EMERALD_TEXTO = "#10b981", "#34d399"  # Online, app aberto, tempo no dock
# fonte da interface: a Inter quando estiver instalada no PC (AgenteApp.__init__), senão a Segoe UI
FONTE = "Segoe UI"
# botão de tema do dock: o sol leva ao claro, a lua ao escuro
ICONE_TEMA = {"escuro": "\uE706", "claro": "\uE708"}

CORES_DOS_WIDGETS = ("background", "foreground", "activebackground", "activeforeground",
                     "highlightbackground", "highlightcolor", "insertbackground",
                     "selectbackground", "disabledforeground", "troughcolor")


def escurecer(cor, fator=0.82):
    """#rrggbb um pouco mais escura (o "destaque_forte" de uma cor de piso)."""
    try:
        r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, TypeError):
        return cor
    return "#%02x%02x%02x" % tuple(max(0, int(v * fator)) for v in (r, g, b))


def misturar(cor, fundo, quanto):
    """`cor` sobre `fundo` com opacidade `quanto` (0 a 1): o bg-cor/15 do Tailwind."""
    try:
        a = [int(cor[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(fundo[i:i + 2], 16) for i in (1, 3, 5)]
    except (ValueError, TypeError):
        return cor
    return "#%02x%02x%02x" % tuple(round(x * quanto + y * (1 - quanto)) for x, y in zip(a, b))


def cor_valida(cor):
    return isinstance(cor, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", cor) is not None


def trocar_cores(widget, mapa):
    """Troca as cores (de `mapa`) neste widget e em todos os de dentro."""
    for opcao in CORES_DOS_WIDGETS:
        try:
            valor = str(widget.cget(opcao)).lower()
        except tk.TclError:
            continue
        if valor in mapa:
            try:
                widget.configure({opcao: mapa[valor]})
            except tk.TclError:
                pass
    for filho in widget.winfo_children():
        trocar_cores(filho, mapa)


# ── Bloqueio de atalhos do Windows ───────────────────────────────────────────
VK_TAB, VK_ESCAPE, VK_F4, VK_LWIN, VK_RWIN = 0x09, 0x1B, 0x73, 0x5B, 0x5C
VK_SHIFT, VK_CONTROL = 0x10, 0x11


class BloqueioTeclado:
    """Hook de teclado de baixo nível (WH_KEYBOARD_LL): engole os atalhos que
    tiram o cliente do agente (Win, Alt+Tab, Ctrl+Shift+Esc...). Não precisa de
    admin. Ctrl+Alt+Del não passa por aqui; esse fica com as políticas do
    usuário "cliente" gravadas pelo instalar.bat.

    Roda numa thread com loop de mensagens próprio: se o callback demorar
    (Tkinter ocupado), o Windows desliga o hook sem avisar.
    """

    def __init__(self, deve_bloquear):
        # deve_bloquear(vk, alt, ctrl, shift) -> bool
        self.deve_bloquear = deve_bloquear
        self.ativo = False
        try:
            from ctypes import wintypes
            self._wt = wintypes
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError):
            return  # fora do Windows

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]
        self._KBD = KBDLLHOOKSTRUCT

        lresult = ctypes.c_ssize_t
        self._HOOKPROC = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u = self._user32
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, self._HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        u.SetWindowsHookExW.restype = wintypes.HHOOK
        u.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        u.CallNextHookEx.restype = lresult
        u.GetAsyncKeyState.restype = ctypes.c_short
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        # referência guardada: se o callback for coletado, o processo cai
        self._proc = self._HOOKPROC(self._callback)
        threading.Thread(target=self._thread, daemon=True).start()

    def _callback(self, n_code, wparam, lparam):
        if n_code == 0:
            try:
                k = ctypes.cast(lparam, ctypes.POINTER(self._KBD)).contents
                alt = bool(k.flags & 0x20)  # LLKHF_ALTDOWN
                ctrl = bool(self._user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                shift = bool(self._user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
                if self.deve_bloquear(k.vkCode, alt, ctrl, shift):
                    return 1
            except Exception:
                pass  # nunca derrubar o teclado do PC por um erro aqui
        return self._user32.CallNextHookEx(None, n_code, wparam, lparam)

    def _thread(self):
        hook = self._user32.SetWindowsHookExW(13, self._proc, self._kernel32.GetModuleHandleW(None), 0)
        if not hook:
            return
        self.ativo = True
        msg = self._wt.MSG()
        while self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))


class Pilula:
    """Botão (ou rótulo) de cantos arredondados desenhado num Canvas: o Tk não
    arredonda Button nem pinta borda colorida. `estilo(sobre)` devolve
    (fundo, borda, texto) com as cores do tema na hora (troca de tema e piso).
    config(text=..., fg=...) muda o texto ou a cor dele, como num Label."""

    def __init__(self, pai, texto, fonte, estilo, fundo_pai, comando=None, padx=12, altura=30, raio=10):
        self.texto, self.fonte, self.estilo, self.fundo_pai = texto, fonte, estilo, fundo_pai
        self.comando, self.padx, self.altura, self.raio = comando, padx, altura, raio
        self.fg = None  # cor do texto fixada por config(fg=)
        self.sobre = False
        self.canvas = tk.Canvas(pai, height=altura, highlightthickness=0, bd=0,
                                cursor="hand2" if comando else "arrow")
        if comando:
            self.canvas.bind("<Enter>", lambda e: self._mouse(True))
            self.canvas.bind("<Leave>", lambda e: self._mouse(False))
            self.canvas.bind("<Button-1>", lambda e: self.comando())
        self.desenhar()

    def pack(self, **opcoes):
        self.canvas.pack(**opcoes)

    def config(self, text=None, fg=None, **_):
        if text is not None:
            self.texto = text
        if fg is not None:
            self.fg = fg or None  # "" volta a cor do estilo
        self.desenhar()

    configure = config

    def _mouse(self, sim):
        self.sobre = sim
        self.desenhar()

    def desenhar(self):
        c = self.canvas
        fundo, borda, cor_texto = self.estilo(self.sobre)
        largura = self.fonte.measure(self.texto) + 2 * self.padx
        c.config(width=largura, bg=self.fundo_pai())
        c.delete("all")
        BarraSessao._retangulo(c, 0, 0, largura - 1, self.altura - 1, self.raio, fill=borda, outline="")
        BarraSessao._retangulo(c, 1, 1, largura - 2, self.altura - 2, self.raio - 1, fill=fundo, outline="")
        c.create_text(largura / 2, self.altura / 2, text=self.texto, font=self.fonte, fill=self.fg or cor_texto)


class BarraSessao:
    """Dock do MatheCafé na sessão, no lugar da barra do Windows (9.4).

    Ocupa só a faixa da barra do Windows (a que os apps maximizados já
    respeitam), sem invadir a tela. No meio, o dock: Início e os apps
    liberados que estão abertos (o em foco com bolinha); com o mouse em cima o
    ícone ganha um contorno e o nome aparece num balão. À direita, um bloco com
    o sininho das notificações, relógio, tempo restante, tema e Encerrar. Fora
    do desenho a janela é transparente.

    Sem animação: o canvas só é redesenhado quando algo muda (redesenhar a cada
    quadro fazia o dock piscar na estação).
    """
    CHAVE = "#010203"  # cor que vira transparente
    ALTURA = 48  # sem a barra do Windows para copiar
    ICONE = 18  # px: ícone dentro da aba do app
    ESPACO = 8
    CORES_APPS = ("#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6")

    def __init__(self, app):
        self.app = app
        p = app.paleta
        self.altura = self.ALTURA
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=self.CHAVE)
        try:
            self.top.attributes("-transparentcolor", self.CHAVE)
        except tk.TclError:
            pass  # fora do Windows o fundo fica liso
        self.canvas = tk.Canvas(self.top, bg=self.CHAVE, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Motion>", self._ao_mover)
        self.canvas.bind("<Leave>", self._ao_sair)
        self.canvas.bind("<Button-1>", self._ao_clicar)

        # balão com o nome, numa janelinha acima do ícone (só durante o mouse em cima)
        self.balao = tk.Toplevel(app.root)
        self.balao.withdraw()
        self.balao.overrideredirect(True)
        self.balao.attributes("-topmost", True)
        self.lbl_balao = tk.Label(self.balao, font=(FONTE, 9, "bold"), fg="white", bg="#111827", padx=8, pady=3)
        self.lbl_balao.pack()

        self._itens = []  # [{"chave", "nome", "letra", "cor", "acao", "imagem_url"}]
        # capa de cada app como ícone: url -> bytes baixados (None = falhou)
        self._capas = {}
        self._icones = {}  # (url, cor do fundo) -> PhotoImage pronto (guardado para o Tk não perder)
        self._sobre = None  # índice do ícone sob o mouse
        self._janelas = {}  # processo -> [hwnd] (só apps liberados abertos)
        self._foco = None
        self._janela_bloco = None  # item do canvas com o bloco (criado uma vez só)
        self._img_pasta = None  # ícone de pasta (Meus arquivos), guardado para o Tk não perdê-lo
        self._contornos = {}  # índice -> cor da borda da aba (o mouse em cima troca)
        self._fonte_aba = tkfont.Font(family=FONTE, size=8)

        # bloco da direita: sininho, relógio + tempo juntos, tema e Encerrar, em pílulas
        # (9.12: bg-zinc-900 com borda zinc-800; Encerrar em rosa suave)
        self._hora, self._tempo, self._alerta = "--:--", "00:00:00", False
        self.bloco = tk.Frame(self.canvas, bg=p["fundo"])
        fundo_bloco = lambda: self.app.paleta["fundo"]
        neutro = lambda sobre: (self.app.paleta["superficie2" if sobre else "superficie"], self.app.paleta["borda"],
                                self.app.paleta["texto2"])
        # sininho pequeno com o contador azul (clicar mostra/esconde as notificações)
        self.sininho = tk.Canvas(self.bloco, width=34, height=32, bg=p["fundo"], highlightthickness=0,
                                 bd=0, cursor="hand2")
        self.sininho.pack(side="left", padx=(0, 6))
        self.sininho.bind("<Button-1>", lambda _e: self._sininho())
        self.lbl_relogio = tk.Canvas(self.bloco, width=150, height=30, bg=p["fundo"], highlightthickness=0, bd=0)
        self.lbl_relogio.pack(side="left", padx=3)
        self._mostrar_relogio()
        self.btn_tema = Pilula(self.bloco, ICONE_TEMA[app.tema], tkfont.Font(family="Segoe MDL2 Assets", size=10),
                               neutro, fundo_bloco, comando=app.alternar_tema, altura=30, padx=9)
        self.btn_tema.pack(side="left", padx=3)
        rosa = lambda sobre: ((ROSA, ROSA, TEXTO_CLARO) if sobre else
                              (misturar(ROSA, self.app.paleta["fundo"], 0.15),
                               misturar(ROSA_CLARO, self.app.paleta["fundo"], 0.3), ROSA_TEXTO))
        self.btn_encerrar = Pilula(self.bloco, "Encerrar sessão", tkfont.Font(family=FONTE, size=8, weight="bold"),
                                   rosa, fundo_bloco, comando=app._encerrar_sessao_cliente, altura=30)
        self.btn_encerrar.pack(side="left", padx=(3, 0))

    def _mostrar_relogio(self):
        """Hora e tempo restante no mesmo bloco (font-mono): ícone, hora | tempo em verde (rosa nos 5 minutos finais)."""
        p, c = self.app.paleta, self.lbl_relogio
        fonte = tkfont.Font(family="Consolas", size=8, weight="bold")
        w = 34 + fonte.measure(self._hora) + 21 + fonte.measure(self._tempo) + 12
        c.delete("all")
        c.config(width=w, bg=p["fundo"])
        self._retangulo(c, 0, 0, w - 1, 29, 10, fill=p["borda"], outline="")
        self._retangulo(c, 1, 1, w - 2, 28, 9, fill=p["superficie"], outline="")
        c.create_text(16, 15, text="\uE823", font=("Segoe MDL2 Assets", 8), fill=p["texto2"])
        h = c.create_text(30, 15, anchor="w", text=self._hora, font=fonte, fill=p["texto"])
        xs = (c.bbox(h) or (0, 0, 70, 0))[2] + 10
        c.create_line(xs, 8, xs, 22, fill=p["borda"])
        c.create_text(xs + 10, 15, anchor="w", text=self._tempo, font=fonte,
                      fill=ROSA_TEXTO if self._alerta else EMERALD_TEXTO)

    def definir_hora(self, hora):
        if hora != self._hora:
            self._hora = hora
            self._mostrar_relogio()

    def definir_tempo(self, texto, alerta):
        if (texto, alerta) != (self._tempo, self._alerta):
            self._tempo, self._alerta = texto, alerta
            self._mostrar_relogio()

    # ── janela ──
    def mostrar(self):
        largura, altura = self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        area = area_da_barra_do_windows()
        if area and area[1] > altura // 2 and area[2] >= largura // 2 and area[3] >= 30:
            x, y, w, h = area  # exatamente onde estava a do Windows (apps maximizados não cobrem)
        else:
            x, y, w, h = 0, altura - self.ALTURA, largura, self.ALTURA
        self.altura = h
        self.top.geometry(f"{w}x{h}+{x}+{y}")
        self.top.deiconify()
        self.top.attributes("-topmost", True)
        self.top.lift()
        barra_do_windows(False)
        self._montar_itens()
        self.desenhar()

    def esconder(self):
        self.top.withdraw()
        self.balao.withdraw()
        self._janelas = {}
        barra_do_windows(True)

    def manter(self):
        """A cada segundo na sessão. Na pausa a barra some (a tela de pausa
        cobre tudo); o Windows às vezes mostra a barra dele de novo."""
        if self.app._sessao_pausada:
            self.top.withdraw()
            self.balao.withdraw()
            return
        if self.top.state() == "withdrawn":
            self.top.deiconify()
        if barra_do_windows_visivel():
            barra_do_windows(False)
        self.definir_hora(time.strftime("%H:%M"))
        self.top.lift()

    def inicio(self):
        self.app.root.deiconify()
        self.app.root.lift()
        self.app.root.focus_force()
        self.top.lift()

    # ── itens do dock: Início, os apps abertos e o sininho ──
    def _app_do_processo(self, processo):
        for i, a in enumerate(self.app.whitelist_apps):
            if (a.get("processo") or "").strip().lower() == processo:
                return i, a
        return 0, {"nome": processo.rsplit(".", 1)[0].title(), "processo": processo}

    def _montar_itens(self):
        itens = [{"chave": "inicio", "nome": "Início", "letra": "⌂", "cor": None, "acao": self.inicio},
                 {"chave": "arquivos", "nome": "Meus arquivos", "letra": "📁", "cor": "#f59e0b",
                  "acao": self._meus_arquivos}]
        for processo in sorted(self._janelas):
            i, a = self._app_do_processo(processo)
            nome = a.get("nome") or processo
            itens.append({"chave": processo, "nome": nome, "letra": nome.strip()[:1].upper(),
                          "cor": self.CORES_APPS[i % len(self.CORES_APPS)],
                          "imagem_url": (a.get("imagem_url") or "").strip() or None,
                          "acao": lambda p=processo: self._trazer(p)})
        self._itens = itens
        self._sobre = None
        self.balao.withdraw()

    def atualizar_apps(self, janelas):
        """janelas: [(hwnd, titulo, processo)] dos apps liberados abertos agora."""
        abertas = {}
        for hwnd, _titulo, processo in janelas:
            abertas.setdefault(processo, []).append(hwnd)
        foco = janela_em_foco()
        foco = next((p for p, hs in abertas.items() if foco in hs), None)
        if abertas != self._janelas or foco != self._foco:
            self._janelas, self._foco = abertas, foco
            self._montar_itens()
            self.desenhar()
            telas = getattr(self.app, "_tela_apps", None)
            if telas:
                telas.marcar_abertos(abertas)  # "Pronto" / "Aberto" nos cards

    def _icone_do_item(self, item):
        """O ícone pronto da capa do app, ou None (ainda baixando, sem capa ou
        falhou: o dock mostra a letra). O download é feito uma vez, em segundo plano."""
        url = item.get("imagem_url")
        if not url or not PIL_AVAILABLE:
            return None
        if url not in self._capas:
            self._capas[url] = ...  # baixando

            def baixar(u=url):
                try:
                    with abrir_url(u, timeout=8) as r:
                        dados = r.read()
                except Exception:
                    dados = None
                self.root.after(0, lambda: self._capa_baixada(u, dados))
            if url.startswith("data:"):
                import base64
                try:
                    self._capas[url] = base64.b64decode(url.split(",", 1)[1]) if ";base64," in url \
                        else urllib.parse.unquote(url.split(",", 1)[1]).encode("utf-8")
                except Exception:
                    self._capas[url] = None
            else:
                threading.Thread(target=baixar, daemon=True).start()
                return None
        dados = self._capas.get(url)
        if not dados or dados is ...:
            return None
        fundo = self.app.paleta["superficie"]
        chave = (url, fundo)
        if chave not in self._icones:
            img = icone_do_app(dados, self.ICONE, 9, fundo)
            self._icones[chave] = ImageTk.PhotoImage(img) if img else None
        return self._icones[chave]

    def _capa_baixada(self, url, dados):
        self._capas[url] = dados
        if dados:
            self.desenhar()

    def _trazer(self, processo):
        janelas = self._janelas.get(processo)
        if janelas:
            trazer_para_frente(janelas[0])

    def centro_do_item(self, chave):
        """x na tela do centro de um ícone do dock (para abrir a pasta em cima dele)."""
        for item, x in zip(self._itens, self._centros()):
            if item["chave"] == chave:
                return self.top.winfo_rootx() + x
        return None

    def _meus_arquivos(self):
        abrir = getattr(self.app, "abrir_meus_arquivos", None)
        if abrir:
            abrir()

    def _sininho(self):
        alternar = getattr(self.app, "alternar_notificacoes", None)
        if alternar:
            alternar()

    def contagem_notificacoes(self):
        contar = getattr(self.app, "notificacoes_nao_lidas", None)
        return contar() if contar else 0

    # ── mouse ──
    def _caixas(self):
        """(x0, x1) de cada item, da esquerda para a direita: o botão M (Início),
        Meus arquivos e uma aba por app aberto (h-8, rounded-xl), cada uma com a sua largura."""
        x, caixas = 16, []
        for item in self._itens:
            if item["chave"] == "inicio":
                largura = 32
            else:
                largura = self._fonte_aba.measure(item["nome"]) + self.ICONE + 30
                if item["chave"] == self._foco:
                    largura += 12  # a bolinha de foco
            caixas.append((x, x + largura))
            x += largura + self.ESPACO
        return caixas

    def _centros(self):
        return [(x0 + x1) / 2 for x0, x1 in self._caixas()]

    def _item_em(self, x):
        for k, (x0, x1) in enumerate(self._caixas()):
            if x0 <= x <= x1:
                return k
        return None

    def _indice(self, chave):
        return next((k for k, item in enumerate(self._itens) if item["chave"] == chave), None)

    def _ao_mover(self, ev):
        k = self._item_em(ev.x)
        if k == self._sobre:
            return  # nada mudou: não mexe em nada (é o que evita o pisca)
        self._sobre = k
        self._marcar_sobre()
        self._mostrar_balao(k)

    def _ao_sair(self, _ev):
        if self._sobre is not None:
            self._sobre = None
            self._marcar_sobre()
        self.balao.withdraw()

    def mouse_no_item(self, chave):
        """O mouse está em cima deste ícone do dock?"""
        k = self._indice(chave)
        if k is None:
            return False
        px, py = self.top.winfo_pointerxy()
        x, y = px - self.top.winfo_rootx(), py - self.top.winfo_rooty()
        return 0 <= y <= self.altura and self._item_em(x) == k

    def _marcar_sobre(self):
        cor = self.app.paleta["texto2"]
        for k in range(len(self._itens)):
            self.canvas.itemconfig(f"icone{k}", outline=cor if k == self._sobre else self._contornos.get(k, ""))

    def _mostrar_balao(self, k):
        if k is None:
            self.balao.withdraw()
            return
        self.lbl_balao.config(text=self._itens[k]["nome"])
        self.balao.update_idletasks()
        w, h = self.lbl_balao.winfo_reqwidth(), self.lbl_balao.winfo_reqheight()
        x = int(self.top.winfo_rootx() + self._centros()[k] - w / 2)
        y = self.top.winfo_rooty() - h - 4
        self.balao.geometry(f"+{x}+{y}")
        self.balao.deiconify()
        self.balao.lift()

    def _ao_clicar(self, ev):
        k = self._item_em(ev.x)
        if k is not None:
            self._itens[k]["acao"]()

    # ── desenho ──
    @staticmethod
    def _retangulo(c, x1, y1, x2, y2, r, **opcoes):
        """Retângulo de cantos arredondados no canvas."""
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        pontos = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                  x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(pontos, smooth=True, **opcoes)

    def desenhar(self):
        """Redesenha tudo (só quando algo muda: apps abertos, foco, tema)."""
        c, p = self.canvas, self.app.paleta
        c.delete("desenho")
        largura = self.top.winfo_width() or self.app.root.winfo_screenwidth()
        h, t = self.altura, self.ICONE
        meio = h / 2
        # barra inteira na base (bg zinc-950, borda de cima zinc-800)
        c.create_rectangle(0, 0, largura, h, fill=p["fundo"], outline="", tags="desenho")
        c.create_line(0, 0, largura, 0, fill=p["borda"], tags="desenho")
        c.tag_lower("desenho")
        self._contornos = {}
        for k, (item, (x0, x1)) in enumerate(zip(self._itens, self._caixas())):
            y0, y1 = meio - 16, meio + 16
            if item["chave"] == "inicio":  # o botão MatheCafé
                self._retangulo(c, x0, y0, x1, y1, 10, fill=AZUL, outline="", width=1, tags=("desenho", f"icone{k}"))
                c.create_text((x0 + x1) / 2, meio, text="M", fill=TEXTO_CLARO, font=(FONTE, 10, "bold"), tags="desenho")
                continue
            foco = item["chave"] == self._foco
            contorno = misturar(AZUL, p["fundo"], 0.6) if foco else p["borda"]
            self._contornos[k] = contorno
            self._retangulo(c, x0, y0, x1, y1, 12, fill=misturar(AZUL, p["fundo"], 0.14) if foco else p["superficie"],
                            outline=contorno, width=1, tags=("desenho", f"icone{k}"))
            x = x0 + 12 + t / 2
            topo = meio - t / 2
            if item["chave"] == "arquivos" and PIL_AVAILABLE:
                self._icone_pasta()
                c.create_image(x, topo + t / 2, image=self._img_pasta, tags="desenho")
            else:
                capa = self._icone_do_item(item)
                if capa:
                    # a capa do app cadastrada no painel (Apps permitidos)
                    c.create_image(x, topo + t / 2, image=capa, tags="desenho")
                else:
                    self._retangulo(c, x - t / 2, topo, x + t / 2, topo + t, 5, fill=item["cor"] or p["destaque"],
                                    outline="", tags="desenho")
                    c.create_text(x, topo + t / 2, text=item["letra"], fill=TEXTO_CLARO,
                                  font=(FONTE, 8, "bold"), tags="desenho")
            xt = x + t / 2 + 8
            id_txt = c.create_text(xt, meio, anchor="w", text=item["nome"], font=self._fonte_aba,
                                   fill=p["texto"] if foco else p["texto2"], tags="desenho")
            if foco:
                xf = (c.bbox(id_txt) or (0, 0, xt + 40, 0))[2] + 8
                c.create_oval(xf, meio - 3, xf + 6, meio + 3, fill=AZUL_CLARO, outline="", tags="desenho")
        # bloco à direita: sininho, relógio + tempo, tema e Encerrar (pílulas)
        self.atualizar_sininho()
        self.bloco.config(bg=p["fundo"])
        self._mostrar_relogio()
        for pil in (self.btn_tema, self.btn_encerrar):
            pil.desenhar()
        if self._janela_bloco is None:
            self._janela_bloco = c.create_window(largura - 16, meio, window=self.bloco, anchor="e")
        else:
            c.coords(self._janela_bloco, largura - 16, meio)

    def _icone_pasta(self):
        if self._img_pasta is None:
            self._img_pasta = ImageTk.PhotoImage(icone_pasta(self.ICONE + 2))
        return self._img_pasta

    def atualizar_sininho(self):
        """Só o sininho (número de não lidas), sem tocar no resto do dock."""
        s, p = self.sininho, self.app.paleta
        s.delete("all")
        s.config(bg=p["fundo"])
        n = self.contagem_notificacoes()
        # botão discreto (bg zinc-900, borda zinc-800) com o contador azul
        self._retangulo(s, 0, 1, 30, 31, 10, fill=p["borda"], outline="")
        self._retangulo(s, 1, 2, 29, 30, 9, fill=p["superficie"], outline="")
        s.create_text(15, 16, text="\uEA8F", font=("Segoe MDL2 Assets", 10), fill=p["texto" if n else "texto2"])
        if n:
            s.create_oval(21, 0, 33, 12, fill=AZUL, outline=p["fundo"])
            s.create_text(27, 6, text=str(n) if n < 10 else "9+", fill=TEXTO_CLARO, font=(FONTE, 6, "bold"))


class Notificacoes:
    """Notificações da sessão no canto inferior direito (9.4), no estilo de
    pilha: o cartão mais novo na frente e até dois "espiando" atrás; com o
    mouse em cima a pilha se abre em lista, e fecha ao sair. Uma nova aparece
    sozinha por alguns segundos e depois fica no sininho do dock (que mostra
    e esconde a pilha). Cabeçalho com "N novas" e Limpar tudo; × dispensa.

    Movimento: a pilha aparece com fade (e um leve deslize da direita) e some
    com fade deslizando para a direita; um cartão novo entra deslizando da
    direita e o dispensado sai deslizando para a direita. O fade é da janela
    inteira (-alpha): o fundo é transparente, então um cartão sozinho não tem
    com o que misturar a cor.
    """
    QUADRO_MS = 16          # ~60 quadros por segundo
    SUAVIDADE = 0.28        # fração do caminho por quadro (ease-out, ~0,2 s)
    DESLIZE_JANELA = 28     # px que a pilha anda ao aparecer/sumir
    CHAVE = "#010203"
    LARGURA, ALTURA_CARTAO, ESPACO = 384, 84, 8
    CABECALHO = 40
    ESPIAR, MAXIMO_LISTA, ESPIANDO = 10, 4, 3  # px de deslocamento atrás, cartões na lista, na pilha
    SEGUNDOS_AVISO = 7
    MAXIMO = 20
    # ícone: cor de baixo e de cima (imita o degradê da referência)
    TONS = {"operador": ("#3b82f6", "#38bdf8"), "horario": ("#f97316", "#fbbf24"),
            "tempo": ("#ef4444", "#fb923c"), "conexao": ("#14b8a6", "#38bdf8"),
            "arquivos": ("#d97706", "#fbbf24")}
    SIMBOLOS = {"operador": "✉", "horario": "🕒", "tempo": "⏳", "conexao": "⚡", "arquivos": "📁"}

    def __init__(self, app):
        self.app = app
        self.itens = []  # [{"id", "origem", "titulo", "mensagem", "tipo", "quando", "lida"}]
        self._proximo = 1
        self.visivel = False
        self.fixa = False  # aberta pelo sininho: não some sozinha
        self._timer = None
        self._aberta = 0.0  # 0 = pilha, 1 = lista (anima)
        self._alvo = 0.0
        self._animando = False
        # efeitos de entrada e saída
        self._na_tela = False
        self._alpha, self._alpha_alvo = 0.0, 0.0
        self._dx, self._dx_alvo = 0.0, 0.0  # deslocamento da janela para a direita
        self._base = (0, 0)  # posição da janela sem deslocamento
        self._desloc = {}  # id do cartão -> [deslocamento atual, alvo] (entrando/saindo)
        self._efeitos = False
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=self.CHAVE)
        try:
            self.top.attributes("-transparentcolor", self.CHAVE)
        except tk.TclError:
            pass
        altura = self.CABECALHO + self.MAXIMO_LISTA * (self.ALTURA_CARTAO + self.ESPACO)
        self.altura = altura  # fixa: a parte transparente deixa o clique passar
        self.canvas = tk.Canvas(self.top, bg=self.CHAVE, highlightthickness=0, bd=0,
                                width=self.LARGURA, height=altura)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Motion>", self._ao_mover)
        self.canvas.bind("<Leave>", lambda _e: self._abrir(False))
        self.canvas.bind("<Button-1>", self._ao_clicar)
        self._alvos = []  # [(x1, y1, x2, y2, acao)]
        self._caixa = (0, 0, 0, 0)  # área desenhada (para saber se o mouse está em cima)

    # ── API para o agente ──
    def notificar(self, origem, titulo, mensagem, tipo="operador"):
        item = {"id": self._proximo, "origem": origem, "titulo": titulo, "mensagem": mensagem,
                "tipo": tipo, "quando": time.time(), "lida": False}
        self._proximo += 1
        self.itens = ([item] + self.itens)[: self.MAXIMO]
        if self._na_tela:
            self._desloc[item["id"]] = [self.LARGURA * 0.6, 0.0]  # entra deslizando da direita
            self._efeito()
        self.visivel = True
        if not self.fixa:
            self._agendar_sumir()
        self._mostrar()
        self.app.barra.atualizar_sininho()

    def nao_lidas(self):
        return sum(1 for i in self.itens if not i["lida"])

    def alternar(self):
        """Sininho: mostra (e deixa) ou esconde a pilha."""
        self.visivel = self.fixa = not (self.visivel and self.fixa)
        if self._timer:
            self.top.after_cancel(self._timer)
            self._timer = None
        self._mostrar()

    def limpar(self):
        """Fim da sessão: nada passa para o próximo cliente (sem animação)."""
        self.itens, self.visivel, self.fixa = [], False, False
        self._aberta = self._alvo = 0.0
        self._desloc = {}
        self._na_tela = False
        self._alpha = self._alpha_alvo = 0.0
        self.top.withdraw()

    # ── comportamento ──
    def _agendar_sumir(self):
        if self._timer:
            self.top.after_cancel(self._timer)
        self._timer = self.top.after(self.SEGUNDOS_AVISO * 1000, self._sumir)

    def _sumir(self):
        self._timer = None
        if not self.fixa and self._alvo == 0:
            self.visivel = False
            self._mostrar()

    def _abrir(self, sim):
        """Mouse em cima: abre a lista (e marca como lidas); saiu: volta a pilha."""
        alvo = 1.0 if sim and self.itens else 0.0
        if alvo == self._alvo:
            return
        self._alvo = alvo
        if sim:
            if self._timer:
                self.top.after_cancel(self._timer)
                self._timer = None
            for i in self.itens:
                i["lida"] = True
            self.app.barra.atualizar_sininho()
        elif not self.fixa:
            self._agendar_sumir()
        if not self._animando:
            self._animando = True
            self.top.after(16, self._animar)

    def _animar(self):
        self._aberta += (self._alvo - self._aberta) * 0.3
        if abs(self._alvo - self._aberta) < 0.02:
            self._aberta = self._alvo
            self._animando = False
        else:
            self.top.after(16, self._animar)
        self._desenhar()

    def _ao_mover(self, ev):
        x1, y1, x2, y2 = self._caixa
        self._abrir(x1 <= ev.x <= x2 and y1 <= ev.y <= y2)

    def _dispensar(self, ident):
        """× : o cartão sai deslizando para a direita e só então é tirado."""
        item = next((i for i in self.itens if i["id"] == ident), None)
        if item is None or item.get("saindo"):
            return
        item["saindo"] = True
        atual = self._desloc.get(ident, [0.0, 0.0])[0]
        self._desloc[ident] = [atual, float(self.LARGURA + 20)]
        self._efeito()

    def _tirar(self, ident):
        self.itens = [i for i in self.itens if i["id"] != ident]
        if not self.itens:
            self._alvo = self._aberta = 0.0
        self._mostrar()
        self.app.barra.atualizar_sininho()

    def _limpar_tudo(self):
        self.itens = []
        self._alvo = self._aberta = 0.0
        self._mostrar()
        self.app.barra.atualizar_sininho()

    def _ao_clicar(self, ev):
        for x1, y1, x2, y2, acao in reversed(self._alvos):
            if x1 <= ev.x <= x2 and y1 <= ev.y <= y2:
                acao()
                return

    # ── desenho ──
    @staticmethod
    def _quando(t):
        s = int(time.time() - t)
        return "agora" if s < 60 else f"{s // 60} min"

    def _mostrar(self):
        if not self.visivel:
            if self._na_tela:  # some com fade, deslizando para a direita
                self._alpha_alvo, self._dx_alvo = 0.0, float(self.DESLIZE_JANELA)
                self._efeito()
            return
        tela_l, tela_a = self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        self._base = (tela_l - self.LARGURA - 12, tela_a - self.app.barra.altura - self.altura - 8)
        self._desenhar()
        if not self._na_tela:  # aparece com fade, vindo um pouco da direita
            self._na_tela = True
            self._alpha, self._dx = 0.0, float(self.DESLIZE_JANELA)
            self._posicionar()
            self.top.deiconify()
        self._alpha_alvo, self._dx_alvo = 1.0, 0.0
        self.top.lift()
        self._efeito()

    def _posicionar(self):
        x, y = self._base
        self.top.geometry(f"{self.LARGURA}x{self.altura}+{int(x + self._dx)}+{y}")
        try:
            self.top.attributes("-alpha", max(0.0, min(1.0, self._alpha)))
        except tk.TclError:
            pass

    def _efeito(self):
        if not self._efeitos:
            self._efeitos = True
            self.top.after(self.QUADRO_MS, self._animar_efeitos)

    @classmethod
    def _passo(cls, atual, alvo, perto):
        """Um quadro do ease-out: anda uma fração do que falta; chega se está perto."""
        novo = atual + (alvo - atual) * cls.SUAVIDADE
        return alvo if abs(alvo - novo) < perto else novo

    def _animar_efeitos(self):
        """Fade/deslize da janela e deslize dos cartões, ~60 quadros por segundo."""
        self._alpha = self._passo(self._alpha, self._alpha_alvo, 0.02)
        self._dx = self._passo(self._dx, self._dx_alvo, 0.5)
        self._posicionar()
        for ident, (atual, alvo) in list(self._desloc.items()):
            novo = self._passo(atual, alvo, 1.0)
            if novo == alvo:
                del self._desloc[ident]
                if alvo > 0:  # saiu pela direita: agora sim tira da lista
                    self._tirar(ident)
            else:
                self._desloc[ident] = [novo, alvo]
        self._desenhar()
        parado = self._alpha == self._alpha_alvo and self._dx == self._dx_alvo and not self._desloc
        if self._alpha_alvo == 0.0 and self._alpha == 0.0 and self._na_tela:
            self._na_tela = False
            self.top.withdraw()
        if parado:
            self._efeitos = False
        else:
            self.top.after(self.QUADRO_MS, self._animar_efeitos)

    def _desenhar(self):
        c, p = self.canvas, self.app.paleta
        ret = BarraSessao._retangulo
        c.delete("all")
        self._alvos = []
        L, H, a = self.LARGURA, self.ALTURA_CARTAO, self._aberta
        itens = self.itens[: self.MAXIMO_LISTA]
        n = len(itens)
        # altura ocupada: pilha (um cartão + espiadas) ou lista (todos)
        pilha = H + self.ESPIAR * max(0, min(n, self.ESPIANDO) - 1)
        lista = n * H + max(0, n - 1) * self.ESPACO
        ocupado = pilha + (lista - pilha) * a if n else H
        topo = self.altura - ocupado  # tudo encostado embaixo, crescendo para cima
        # cabeçalho: título, "N novas" e Limpar tudo, numa pílula
        hy = topo - self.CABECALHO
        ret(c, 0, hy + 4, L, hy + self.CABECALHO - 6, 14, fill=p["superficie"], outline=p["superficie3"])
        c.create_text(14, hy + 19, text="Notificações", anchor="w", fill=p["texto"], font=(FONTE, 10, "bold"))
        novas = self.nao_lidas()
        rotulo = f"{novas} {'nova' if novas == 1 else 'novas'}" if novas else f"{len(self.itens)} no total"
        etiqueta = c.create_text(126, hy + 19, text=rotulo, anchor="w", fill="white", font=(FONTE, 8, "bold"))
        ex1, ey1, ex2, ey2 = c.bbox(etiqueta)
        fundo = ret(c, ex1 - 8, ey1 - 3, ex2 + 8, ey2 + 3, 10, fill=p["destaque"], outline="")
        c.tag_raise(etiqueta, fundo)
        if self.itens:
            lim = c.create_text(L - 14, hy + 19, text="Limpar tudo", anchor="e", fill=p["texto2"],
                                font=(FONTE, 9))
            x1, y1, x2, y2 = c.bbox(lim)
            self._alvos.append((x1 - 4, y1 - 4, x2 + 4, y2 + 4, self._limpar_tudo))
        self._caixa = (0, hy, L, self.altura)
        if not n:
            ret(c, 0, topo, L, topo + H, 16, fill=p["superficie"], outline=p["superficie3"], dash=(4, 3))
            c.create_text(L / 2, topo + H / 2, text="🔕  Tudo em dia", fill=p["texto2"], font=(FONTE, 10))
            return
        # de trás para a frente: o mais novo fica por cima
        for pos in range(n - 1, -1, -1):
            item = itens[pos]
            if pos >= self.ESPIANDO and a < 0.05:
                continue  # na pilha só aparecem três
            y_pilha = topo + self.ESPIAR * min(pos, self.ESPIANDO - 1)
            y_lista = topo + pos * (H + self.ESPACO)
            y1 = y_pilha + (y_lista - y_pilha) * a
            encolhe = (1 - 0.05 * min(pos, self.ESPIANDO - 1)) * (1 - a) + a  # atrás, um pouco mais estreito
            m = L * (1 - encolhe) / 2
            dx = self._desloc.get(item["id"], (0.0, 0.0))[0]  # entrando ou saindo pela direita
            ret(c, m + dx, y1, L - m + dx, y1 + H, 16, fill=p["superficie"], outline=p["superficie3"])
            if pos > 0 and a < 0.5 and not dx:
                continue  # atrás da pilha: só a borda espiando
            self._cartao(c, item, m + dx, y1, L - m + dx)

    def _cartao(self, c, item, x1, y1, x2):
        p = self.app.paleta
        ret = BarraSessao._retangulo
        H = self.ALTURA_CARTAO
        baixo, cima = self.TONS.get(item["tipo"], (p["destaque"], p["destaque"]))
        ix, iy = x1 + 16, y1 + (H - 40) / 2
        ret(c, ix, iy, ix + 40, iy + 40, 11, fill=baixo, outline="")
        ret(c, ix, iy, ix + 40, iy + 22, 11, fill=cima, outline="")  # brilho de cima
        ret(c, ix, iy + 14, ix + 40, iy + 40, 11, fill=baixo, outline="")
        c.create_text(ix + 20, iy + 20, text=self.SIMBOLOS.get(item["tipo"], "•"), fill="white",
                      font=(FONTE, 14))
        tx = ix + 52
        c.create_text(tx, y1 + 22, text=item["origem"].upper(), anchor="w", fill=p["texto2"],
                      font=(FONTE, 8, "bold"))
        c.create_text(x2 - 34, y1 + 22, text=self._quando(item["quando"]), anchor="e", fill=p["texto2"],
                      font=(FONTE, 8))
        if not item["lida"]:
            c.create_oval(x2 - 28, y1 + 18, x2 - 20, y1 + 26, fill="#3b82f6", outline="")
        largura_texto = x2 - tx - 16
        c.create_text(tx, y1 + 42, text=self._caber(item["titulo"], largura_texto, 10), anchor="w", fill=p["texto"],
                      font=(FONTE, 10, "bold"))
        c.create_text(tx, y1 + 62, text=self._caber(item["mensagem"], largura_texto, 9), anchor="w",
                      fill=p["texto2"], font=(FONTE, 9))
        # o cartao mostra uma linha so: clicar nele abre a mensagem inteira
        self._alvos.append((x1, y1, x2, y1 + H, lambda i=item: self.app._exibir_mensagem_operador(
            i["mensagem"], titulo=i["titulo"], modal=False)))
        fechar = c.create_text(x2 - 10, y1 + 22, text="✕", fill=p["texto2"], font=(FONTE, 8))
        bx1, by1, bx2, by2 = c.bbox(fechar)
        self._alvos.append((bx1 - 5, by1 - 5, bx2 + 5, by2 + 5, lambda i=item["id"]: self._dispensar(i)))

    @staticmethod
    def _caber(texto, largura_px, tamanho):
        """Uma linha só, com reticências (como o truncate da referência)."""
        cabe = max(4, int(largura_px / (tamanho * 0.58)))
        return texto if len(texto) <= cabe else texto[: cabe - 1].rstrip() + "…"


def _fonte_pil(arquivo, tamanho):
    try:
        return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", arquivo), tamanho)
    except Exception:
        return ImageFont.load_default()


def icone_pasta(tamanho, tem_arquivos=True):
    """Ícone de pasta do dock (Meus arquivos), desenhado em 4x e reduzido."""
    S = 4
    n = 32 * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([2 * S, 5 * S, 14 * S, 12 * S], radius=2 * S, fill=(217, 119, 6))  # aba
    d.rounded_rectangle([2 * S, 8 * S, 30 * S, 28 * S], radius=3 * S, fill=(217, 119, 6))  # fundo
    if tem_arquivos:  # papéis espiando
        papel = Image.new("RGBA", (20 * S, 16 * S), (0, 0, 0, 0))
        ImageDraw.Draw(papel).rounded_rectangle([0, 0, 20 * S - 1, 16 * S - 1], radius=2 * S, fill=(226, 232, 240))
        im.alpha_composite(papel.rotate(10, resample=Image.BICUBIC, expand=True), (5 * S, 5 * S))
        ImageDraw.Draw(papel).rounded_rectangle([0, 0, 20 * S - 1, 16 * S - 1], radius=2 * S, fill=(255, 255, 255))
        im.alpha_composite(papel.rotate(-6, resample=Image.BICUBIC, expand=True), (9 * S, 7 * S))
    frente = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    df = ImageDraw.Draw(frente)
    for y in range(13 * S, 29 * S):  # degradê da frente
        t = (y - 13 * S) / (16 * S)
        df.line([(0, y), (n, y)], fill=(int(252 - 7 * t), int(211 - 53 * t), int(77 - 66 * t), 255))
    mascara = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([1 * S, 13 * S, 31 * S, 28 * S], radius=3 * S, fill=255)
    im.paste(frente, (0, 0), mascara)
    return im.resize((tamanho, tamanho), Image.LANCZOS)


def normalizar_busca(texto):
    """Minúsculas e sem acento: 'Paciência' acha 'paciencia'."""
    import unicodedata
    texto = unicodedata.normalize("NFKD", str(texto or "")).lower()
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def categorias_da_tela(apps):
    """A coluna da esquerda da tela de apps: [(chave, rótulo, quantidade)].
    Todos primeiro; as categorias na ordem do painel; "Outros" (apps sem
    categoria) no fim, só quando há categorias e algum app ficou sem."""
    ordem = {}
    sem = 0
    for a in apps:
        nome = (a.get("categoria") or "").strip()
        if not nome:
            sem += 1
            continue
        pos = a.get("categoria_ordem")
        anterior = ordem.get(nome, (pos, 0))
        ordem[nome] = (anterior[0], anterior[1] + 1)
    lista = [("todos", "Todos", len(apps))]
    for nome, (pos, n) in sorted(ordem.items(), key=lambda kv: (kv[1][0] is None, kv[1][0] or 0, normalizar_busca(kv[0]))):
        lista.append(("cat:" + nome, nome, n))
    if ordem and sem:
        lista.append(("outros", "Outros", sem))
    return lista


def filtrar_apps(apps, chave, busca):
    """Os apps da categoria escolhida (chave de categorias_da_tela) cujo nome
    ou categoria contém a busca (sem diferenciar acento nem maiúscula)."""
    termo = normalizar_busca(busca)
    saida = []
    for a in apps:
        cat = (a.get("categoria") or "").strip()
        if chave == "outros" and cat:
            continue
        if chave.startswith("cat:") and cat != chave[4:]:
            continue
        if termo and termo not in normalizar_busca(a.get("nome")) and termo not in normalizar_busca(cat):
            continue
        saida.append(a)
    return saida


def _cor_rgb(cor):
    try:
        return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, TypeError):
        return (15, 17, 23)


def _cantos(img, raio, fundo):
    """A imagem com cantos arredondados sobre a cor do fundo (sem franja)."""
    S = 3
    mascara = Image.new("L", (img.width * S, img.height * S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, mascara.width - 1, mascara.height - 1), raio * S, fill=255)
    mascara = mascara.resize(img.size, Image.LANCZOS)
    base = Image.new("RGB", img.size, _cor_rgb(fundo))
    base.paste(img.convert("RGB"), (0, 0), mascara)
    return base


def _preencher(img, largura, altura):
    """Amplia e corta o centro até cobrir largura x altura (sem deformar)."""
    escala = max(largura / img.width, altura / img.height)
    nova = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))), Image.LANCZOS)
    x0, y0 = (nova.width - largura) // 2, (nova.height - altura) // 2
    return nova.crop((x0, y0, x0 + largura, y0 + altura))


def montar_banner(cartaz, largura, altura, fundo):
    """Banner largo da Programação a partir de um cartaz em pé: o fundo é o
    próprio cartaz ampliado, desfocado e escurecido; o cartaz inteiro fica à
    direita com sombra; à esquerda, um degradê escuro para o título (que o
    Tkinter escreve por cima). Devolve (imagem RGB, largura ocupada pelo cartaz)."""
    cartaz = cartaz.convert("RGB")
    pequeno = _preencher(cartaz, max(1, largura // 4), max(1, altura // 4))
    fundo_img = pequeno.filter(ImageFilter.GaussianBlur(6)).resize((largura, altura), Image.BILINEAR)
    fundo_img = Image.blend(fundo_img, Image.new("RGB", fundo_img.size, (0, 0, 0)), 0.45)
    # degradê da esquerda (onde fica o título): zinc-950 cheio -> 90% -> transparente
    def opacidade(v):
        x = v / 255
        return 1 - x / 0.45 * 0.1 if x < 0.45 else max(0.0, 0.9 * (1 - (x - 0.45) / 0.4))
    faixa = Image.linear_gradient("L").rotate(90, expand=True).resize((largura, altura))
    faixa = faixa.point(lambda v: int(opacidade(v) * 255))
    fundo_img.paste(_cor_rgb("#09090b"), (0, 0), faixa)
    # o cartaz inteiro, à direita
    margem = max(12, altura // 14)
    alto = altura - 2 * margem
    largo = max(1, round(cartaz.width * alto / cartaz.height))
    if largo > largura * 0.45:  # cartaz deitado: limita pela largura
        largo = int(largura * 0.45)
        alto = max(1, round(cartaz.height * largo / cartaz.width))
    peca = cartaz.resize((largo, alto), Image.LANCZOS)
    x = largura - largo - margem * 2
    y = (altura - alto) // 2
    sombra = Image.new("L", (largura, altura), 0)
    ImageDraw.Draw(sombra).rounded_rectangle((x + 4, y + 8, x + largo + 4, y + alto + 8), 10, fill=150)
    sombra = sombra.filter(ImageFilter.GaussianBlur(10))
    fundo_img.paste((0, 0, 0), (0, 0), sombra)
    fundo_img.paste(_cantos(peca, 8, "#000000"), (x, y),
                    _cantos(Image.new("RGB", peca.size, (255, 255, 255)), 8, "#000000").convert("L"))
    return _cantos(fundo_img, 24, fundo), largo + margem * 3  # rounded-3xl


def _paleta_categorias():
    """Cores das categorias quando o servidor não manda (antigo): violeta, azul,
    esmeralda, âmbar, rosa... As mesmas do servidor (routers/categorias.py)."""
    return ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#f43f5e", "#06b6d4", "#ec4899", "#84cc16"]


def icone_da_categoria(nome):
    """Ícone do card pelo nome da categoria (Segoe MDL2 Assets); None = a inicial do app."""
    nome = normalizar_busca(nome)
    for palavras, icone in ((("naveg", "internet", "web"), "\uE774"), (("estudo", "leitura", "livro"), "\uE82D"),
                            (("desenv", "program", "codigo"), "\uE943"), (("utilit", "ferrament"), "\uE90F"),
                            (("midia", "audio", "musica", "video"), "\uE8D6"), (("jogo", "game"), "\uE7FC"),
                            (("escrit", "office", "texto", "document"), "\uE8A5")):
        if any(p in nome for p in palavras):
            return icone
    return None


def cor_do_app(app, destaque):
    """A cor da categoria do app (selo, fundo da logo, brilho e botão Abrir).
    App sem categoria ("Outros") usa o destaque (a cor do piso)."""
    if not (app.get("categoria") or "").strip():
        return destaque
    cor = app.get("categoria_cor")
    if cor_valida(cor):
        return cor.lower()
    cores = _paleta_categorias()
    return cores[(app.get("categoria_ordem") or 0) % len(cores)]


def montar_cartao(dados, largura, altura, capa_h, fundo, cartao, borda, cor, margem, brilho=False):
    """Card da grade de apps (9.12): capa em cima (capa_h px, escurecida como
    opacity-60 sobre o zinc-950) e o rodapé liso na cor `cartao`, com borda de
    1 px. Mouse em cima (brilho): a borda puxa para a cor da categoria. Sem capa
    (dados None), um degradê da cor da categoria. O card fica no meio de uma
    moldura de `margem` px na cor do fundo, onde cabe a sombra. Imagem RGB."""
    S = 3
    capa = None
    if dados:
        try:
            capa = _preencher(Image.open(BytesIO(dados)).convert("RGB"), largura, capa_h)
            capa = Image.blend(capa, Image.new("RGB", capa.size, _cor_rgb(ZINC_950)), 0.4)  # opacity-60
        except Exception:
            capa = None
    if capa is None:
        capa = Image.blend(Image.new("RGB", (largura, capa_h), _cor_rgb(ZINC_900)),
                           Image.new("RGB", (largura, capa_h), _cor_rgb(cor)), 0.45)
        capa.paste(_cor_rgb(ZINC_900), (0, 0), Image.linear_gradient("L").resize((largura, capa_h)))
    if brilho:
        capa = Image.blend(capa, Image.new("RGB", capa.size, _cor_rgb(cor)), 0.08)
    # o card: borda de 1 px (cor da categoria a 40% no hover) e o rodapé liso
    contorno = misturar(cor, cartao, 0.4) if brilho else borda
    card = Image.new("RGB", (largura, altura), _cor_rgb(cartao))
    card.paste(capa, (0, 0))
    linha = Image.new("L", (largura * S, altura * S), 0)
    d = ImageDraw.Draw(linha)
    d.rounded_rectangle((0, 0, largura * S - 1, altura * S - 1), 14 * S, fill=255)
    d.rounded_rectangle((S, S, largura * S - 1 - S, altura * S - 1 - S), 13 * S, fill=0)
    card.paste(_cor_rgb(contorno), (0, 0), linha.resize((largura, altura), Image.LANCZOS))
    # moldura com a sombra
    total = Image.new("RGB", (largura + 2 * margem, altura + 2 * margem), _cor_rgb(fundo))
    halo = Image.new("L", total.size, 0)
    ImageDraw.Draw(halo).rounded_rectangle((margem + 3, margem + 6, margem + largura - 3, margem + altura + 2), 14,
                                           fill=150 if brilho else 90)
    total.paste((0, 0, 0), (0, 0), halo.filter(ImageFilter.GaussianBlur(margem / 2)))
    mascara = Image.new("L", (largura * S, altura * S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, largura * S - 1, altura * S - 1), 14 * S, fill=255)
    total.paste(card, (margem, margem), mascara.resize((largura, altura), Image.LANCZOS))
    return total


def cortar_linhas(texto, fonte, largura, linhas=2):
    """O texto em até `linhas` linhas de `largura` px; o que sobra vira "…" (line-clamp)."""
    palavras, saida, atual = (texto or "").split(), [], ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if fonte.measure(teste) <= largura or not atual:
            atual = teste
            continue
        saida.append(atual)
        atual = p
        if len(saida) == linhas:
            break
    else:
        if atual:
            saida.append(atual)
        return "\n".join(saida[:linhas])
    ultima = saida[-1]
    while ultima and fonte.measure(ultima + "…") > largura:
        ultima = ultima[:-1]
    saida[-1] = ultima.rstrip() + "…"
    return "\n".join(saida)


def baixar_imagem(url, timeout=8):
    """Bytes da imagem (http/https ou data:), ou None."""
    try:
        if url.startswith("data:"):
            import base64
            cabeca, corpo = url.split(",", 1)
            return base64.b64decode(corpo) if ";base64" in cabeca else urllib.parse.unquote(corpo).encode("utf-8")
        with abrir_url(url, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


class Programacao:
    """Banner largo no topo da tela de apps com os cartazes da programação da
    biblioteca, um de cada vez (troca com fade). Os cartazes são em pé: cada um
    aparece inteiro à direita sobre ele mesmo ampliado e desfocado, com o
    título à esquerda. Vêm do servidor (Programação e avisos → Programação); sem
    cartaz, o banner some e a grade de apps sobe."""

    def __init__(self, app, frame):
        self.app = app
        self.frame = frame
        self.canvas = tk.Canvas(frame, bg=app.paleta["fundo"], highlightthickness=0, height=200, cursor="arrow")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._ao_mudar_tamanho)
        self.itens = []  # [(titulo, imagem PIL)]
        self.indice = 0
        self.segundos = 10
        self._timer = None
        self._fade = None
        self._geracao = 0
        self._prontos = {}  # (indice, largura, altura, fundo) -> (imagem PIL, largura do cartaz)
        self._foto = None
        self._tam = (0, 0)
        self._atual = None  # imagem PIL na tela (o fade parte dela)

    @staticmethod
    def altura_para(tela):
        # h-[340px] do prompt; em tela baixa (768) encolhe para a grade ainda aparecer
        return max(250, min(340, int(tela * 0.36)))

    def recarregar(self):
        if not PIL_AVAILABLE:
            return
        self._geracao += 1
        threading.Thread(target=self._baixar, args=(self._geracao,), daemon=True).start()

    def _baixar(self, geracao):
        # thread: nada de Tkinter aqui
        base = self.app.servidor.replace("wss://", "https://").replace("ws://", "http://")
        try:
            with abrir_url(f"{base}/api/programacao/agente", timeout=5) as r:
                dados = json.loads(r.read())
            imagens = []
            for item in dados.get("itens", []):
                with abrir_url(f"{base}/api/programacao/{item['id']}/imagem?v={item.get('versao', 0)}", timeout=10) as r:
                    imagens.append((item.get("titulo", ""), Image.open(BytesIO(r.read())).convert("RGB"),
                                    item.get("link") or None, item.get("descricao") or "", item.get("creditos") or ""))
        except Exception as ex:
            self.app.incoming.put({"evento": "_info", "dados": {"msg": f"Programacao: nao carregou ({ex})"}})
            return
        segundos = dados.get("segundos", 10)
        self.app.root.after(0, lambda: self._mostrar_lista(geracao, segundos, imagens))

    def _mostrar_lista(self, geracao, segundos, imagens):
        if geracao != self._geracao:
            return  # um carregamento mais novo já está a caminho
        self.segundos = max(3, int(segundos or 10))
        # a tela de login também mostra os cartazes (metade direita)
        self.app._tela_login.definir(imagens, self.segundos)
        self.itens = imagens
        self.indice = 0
        self._prontos = {}
        self._atual = None
        if not imagens or not self.app.sessao_ativa:
            self.parar()
            return
        self.frame.pack_forget()
        self.ajustar_pagina()

    def ajustar_pagina(self):
        """O banner só aparece na página Início do menu (Meus Apps é só a grade)."""
        if not (self.itens and self.app.sessao_ativa and self.app._pagina == "inicio"):
            self.frame.pack_forget()
            return
        if self.frame.winfo_manager():
            return  # já está na tela (ou entrando): não agenda outro cartaz
        altura = self.altura_para(self.app.root.winfo_screenheight())
        self.frame.configure(height=altura)
        self.frame.pack(side="top", fill="x", padx=24, pady=(18, 0), before=self.app.frame_launcher)
        self.frame.pack_propagate(False)
        self.app.root.after(30, lambda: self._exibir(fade=False))

    def _ao_mudar_tamanho(self, event):
        tam = (event.width, event.height)
        if tam != self._tam and self.itens:
            self._tam = tam
            self._atual = None
            self._desenhar(self._quadro(self._mostrando()), self._mostrando())

    def _mostrando(self):
        return (self.indice - 1) % len(self.itens) if self.itens else 0

    def _quadro(self, i):
        """O banner pronto do cartaz i no tamanho atual (montado uma vez)."""
        w, h = max(50, self.canvas.winfo_width()), max(50, self.canvas.winfo_height())
        chave = (i, w, h, self.app.paleta["fundo"])
        if chave not in self._prontos:
            self._prontos[chave] = montar_banner(self.itens[i][1], w, h, self.app.paleta["fundo"])
        return self._prontos[chave]

    def _exibir(self, fade=True):
        if self._timer:
            self.app.root.after_cancel(self._timer)
            self._timer = None
        if not self.itens:
            return
        antes = self._mostrando()
        i = self.indice % len(self.itens)
        novo = self._quadro(i)
        self.indice = i + 1
        if fade and self._atual is not None and self._atual.size == novo[0].size:
            self._animar(self._atual, novo, 1, antes, i)
        else:
            self._desenhar(novo, i)
        if len(self.itens) > 1:
            self._timer = self.app.root.after(self.segundos * 1000, self._exibir)

    def ir_para(self, i):
        self.indice = i
        self._exibir()

    DESLIZE = 28  # px que o cartaz anda na troca

    def _animar(self, de, para, passo, i_de, i_para, passos=22):
        """Troca suave entre dois cartazes (~0,65 s, ease-in-out): o novo entra
        deslizando da direita enquanto o antigo sai para a esquerda, os dois em
        fade; o texto some e o do novo aparece (sem pulo)."""
        if self._fade:
            self.app.root.after_cancel(self._fade)
            self._fade = None
        if passo >= passos:
            self._desenhar(para, i_para)
            return
        t = passo / passos
        e = t * t * (3 - 2 * t)  # smoothstep: começa e termina devagar
        cor = de.getpixel((0, 0))
        saindo = Image.new(de.mode, de.size, cor)
        saindo.paste(de, (-round(e * self.DESLIZE), 0))
        entrando = Image.new(de.mode, de.size, cor)
        entrando.paste(para[0], (round((1 - e) * self.DESLIZE), 0))
        mistura = Image.blend(saindo, entrando, e)
        # texto: o antigo some na primeira metade, o novo aparece na segunda
        if e < 0.5:
            self._desenhar((mistura, para[1]), i_de, guardar=False, opacidade=1 - 2 * e)
        else:
            self._desenhar((mistura, para[1]), i_para, guardar=False, opacidade=2 * e - 1)
        self._fade = self.app.root.after(30, lambda: self._animar(de, para, passo + 1, i_de, i_para, passos))

    def _desenhar(self, quadro, i, guardar=True, opacidade=1.0):
        c, p = self.canvas, self.app.paleta
        img, largura_cartaz = quadro
        self._foto = ImageTk.PhotoImage(img)
        if guardar:
            self._atual = img
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._foto)
        if not self.itens:
            return
        i %= len(self.itens)
        h, w = img.height, img.width
        x = max(32, h // 8)
        livre = max(160, w - largura_cartaz - x - 32)
        dados = self.itens[i]
        if opacidade < 1:
            r, g, b = img.getpixel((min(w - 1, x + 4), h // 2))[:3]
            base = "#%02x%02x%02x" % (r, g, b)
            tom = lambda cor: misturar(cor, base, max(0.0, opacidade))
        else:
            tom = lambda cor: cor
        item = {"titulo": dados[0] or "", "link": dados[2] if len(dados) > 2 else None,
                "descricao": dados[3] if len(dados) > 3 else "", "creditos": dados[4] if len(dados) > 4 else ""}
        # selo em pílula
        fonte_selo = tkfont.Font(family=FONTE, size=7, weight="bold")
        texto_selo = "\u2726  PROGRAMAÇÃO DA BIBLIOTECA"
        y = max(24, h * 0.1)
        ls = fonte_selo.measure(texto_selo) + 22
        violeta = "#8b5cf6"
        BarraSessao._retangulo(c, x, y, x + ls, y + 22, 11, fill=tom(misturar(violeta, ZINC_950, 0.45)), outline="")
        BarraSessao._retangulo(c, x + 1, y + 1, x + ls - 1, y + 21, 10, fill=tom(misturar(violeta, ZINC_950, 0.16)), outline="")
        c.create_text(x + ls / 2, y + 11, text=texto_selo, fill=tom("#c4b5fd"), font=fonte_selo)
        y += 34
        # título (text-2xl font-extrabold), descrição e créditos
        tamanho = 20 if len(item["titulo"]) < 48 else 16
        t = c.create_text(x, y, anchor="nw", text=item["titulo"], fill=tom(TEXTO_CLARO), width=livre,
                          font=(FONTE, tamanho, "bold"))
        y = (c.bbox(t) or (0, 0, 0, y + 30))[3] + 10
        if item["descricao"]:
            fonte_desc = tkfont.Font(family=FONTE, size=9)
            t = c.create_text(x, y, anchor="nw", text=cortar_linhas(item["descricao"], fonte_desc, livre, 3),
                              fill=tom("#d4d4d8"), font=fonte_desc)
            y = (c.bbox(t) or (0, 0, 0, y + 20))[3] + 6
        if item["creditos"]:
            t = c.create_text(x, y, anchor="nw", text=item["creditos"], fill=tom("#a1a1aa"), width=livre,
                              font=(FONTE, 8, "italic"))
            y = (c.bbox(t) or (0, 0, 0, y + 14))[3]
        link = item.get("link")
        y_botao = max(y + 18, h - x - 38)
        if link:  # bg-blue-600 rounded-xl shadow-lg shadow-blue-600/30
            fonte = tkfont.Font(family=FONTE, size=9, weight="bold")
            texto = "\u2197  Abrir Inscrição / Programação"
            x1, alto = x + fonte.measure(texto) + 40, 38
            BarraSessao._retangulo(c, x - 2, y_botao + 3, x1 + 2, y_botao + alto + 6, 14,
                                   fill=tom(misturar(AZUL, ZINC_950, 0.3)), outline="")
            BarraSessao._retangulo(c, x, y_botao, x1, y_botao + alto, 12, fill=tom(AZUL), outline="",
                                   tags=("link", "link_fundo"))
            c.create_text((x + x1) / 2, y_botao + alto / 2, text=texto, fill=tom(TEXTO_CLARO), font=fonte, tags="link")
            c.tag_bind("link", "<Button-1>", lambda e, u=link: self._abrir_link(u))
            c.tag_bind("link", "<Enter>", lambda e: (c.config(cursor="hand2"), c.itemconfig("link_fundo", fill=AZUL_CLARO)))
            c.tag_bind("link", "<Leave>", lambda e: (c.config(cursor="arrow"), c.itemconfig("link_fundo", fill=AZUL)))
        # navegação: ‹ bolinhas ›, embaixo à direita do texto
        n = len(self.itens)
        if n > 1:
            meio_y = y_botao + 19
            x_dir = w - largura_cartaz - 8
            larg_bolas = sum(18 if k == i else 6 for k in range(n)) + 6 * (n - 1)
            x_seta2 = x_dir - 30
            x_bolas = x_seta2 - 10 - larg_bolas
            x_seta1 = x_bolas - 10 - 30
            for xs, glifo, alvo in ((x_seta1, "\uE76B", (i - 1) % n), (x_seta2, "\uE76C", (i + 1) % n)):
                tag = f"seta{alvo}_{xs}"
                BarraSessao._retangulo(c, xs, meio_y - 15, xs + 30, meio_y + 15, 10, fill="#3f3f46", outline="", tags=tag)
                BarraSessao._retangulo(c, xs + 1, meio_y - 14, xs + 29, meio_y + 14, 9,
                                       fill=misturar("#18181b", ZINC_950, 0.7), outline="", tags=tag)
                c.create_text(xs + 15, meio_y, text=glifo, font=("Segoe MDL2 Assets", 8), fill="#d4d4d8", tags=tag)
                c.tag_bind(tag, "<Button-1>", lambda e, k=alvo: self.ir_para(k))
                c.tag_bind(tag, "<Enter>", lambda e: c.config(cursor="hand2"))
                c.tag_bind(tag, "<Leave>", lambda e: c.config(cursor="arrow"))
            xb = x_bolas
            for k in range(n):
                lb = 18 if k == i else 6
                bol = BarraSessao._retangulo(c, xb, meio_y - 3, xb + lb, meio_y + 3, 3,
                                             fill=AZUL if k == i else "#52525b", outline="")
                c.tag_bind(bol, "<Button-1>", lambda e, k=k: self.ir_para(k))
                xb += lb + 6

    def _abrir_link(self, link):
        """Abre no navegador padrão (se ele não estiver liberado na estação, o
        monitor de processos fecha)."""
        self.app._log(f"Programacao: abrindo {link}")
        try:
            webbrowser.open(link)
        except Exception as ex:
            self.app._log(f"Programacao: nao abriu o link ({ex})")

    def redesenhar(self):
        """Tema trocado: o canto arredondado e o destaque mudam de cor."""
        self.canvas.config(bg=self.app.paleta["fundo"])
        if self.itens:
            self._atual = None
            self._desenhar(self._quadro(self._mostrando()), self._mostrando())

    def parar(self):
        for t in (self._timer, self._fade):
            if t:
                self.app.root.after_cancel(t)
        self._timer = self._fade = None
        self.itens = []
        self._prontos = {}
        self._foto = None
        self._atual = None
        self.canvas.delete("all")
        self.frame.pack_forget()


class TelaApps:
    """A grade de apps da Área do Cliente (9.11): em cima a pesquisa (filtra
    pelo nome) e as pílulas das categorias (Todos, as do painel, Outros), cada
    uma na cor da sua categoria; embaixo os cards com a capa, a logo e o selo
    na cor da categoria e um botão Abrir. Mouse em cima: o card sobe um pouco
    e brilha na cor da categoria."""
    CARD_W, CARD_H = 170, 250
    CAPA_H = 128  # capa de altura fixa (h-32); embaixo, o rodapé com título, descrição e Abrir
    MARGEM = 8  # moldura do card: a sombra cabe nela
    ESPACO = 8
    SUBIR = 2  # quanto o card sobe com o mouse em cima

    def __init__(self, app, frame):
        self.app = app
        self.frame = frame
        self.apps = []
        self.chave = "todos"
        self.cartoes = {}  # índice do app -> {"canvas", "normal", "hover", "app", "cor", "sobre"}
        self._capas = {}  # url -> bytes (None = falhou; ... = baixando)
        self._colunas = 0
        self._pilulas = []  # [(chave, rótulo, quantidade, cor, canvas)]
        self.escala = 0  # Configurações → tamanho do texto (0 normal, 2 grande); volta a 0 no fim da sessão
        self.abertos = set()  # processos abertos agora (o dock avisa)
        self._montar()

    # ── estrutura (uma vez) ──
    def _montar(self):
        p = self.app.paleta
        f = self.frame
        topo = tk.Frame(f, bg=p["fundo"])
        topo.pack(fill="x", padx=(24, 24), pady=(20, 0))
        self.lbl_titulo = tk.Label(topo, text="Aplicativos da Estação", font=(FONTE, 11, "bold"), fg=p["texto"],
                                   bg=p["fundo"])
        self.lbl_titulo.pack(side="left")
        self.lbl_qtd = tk.Canvas(topo, width=90, height=22, bg=p["fundo"], highlightthickness=0)  # "6 liberados"
        self.lbl_qtd.pack(side="left", padx=10)
        self._texto_qtd = ""

        # pesquisa (rounded-xl): um Canvas com o Entry por cima
        self.caixa_busca = tk.Canvas(topo, width=270, height=36, bg=p["fundo"], highlightthickness=0)
        self.caixa_busca.pack(side="right")
        self._foco_busca = False
        self.var_busca = tk.StringVar()
        self.entry_busca = tk.Entry(self.caixa_busca, textvariable=self.var_busca, font=(FONTE, 9), bg=p["superficie"],
                                    fg=p["texto"], insertbackground=p["texto"], relief="flat", highlightthickness=0)
        self.caixa_busca.create_window(36, 18, window=self.entry_busca, anchor="w", width=204)
        self.lbl_dica = tk.Label(self.caixa_busca, text="Buscar por nome ou categoria...", font=(FONTE, 9),
                                 fg=p["fraco"], bg=p["superficie"], cursor="xterm")
        self._janela_dica = self.caixa_busca.create_window(36, 18, window=self.lbl_dica, anchor="w")
        self.lbl_dica.bind("<Button-1>", lambda e: self.entry_busca.focus_set())
        self.btn_limpar = tk.Label(self.caixa_busca, text="✕", font=(FONTE, 9), fg=p["texto2"], bg=p["superficie"],
                                   cursor="hand2")
        self._janela_limpar = self.caixa_busca.create_window(256, 18, window=self.btn_limpar, anchor="e",
                                                             state="hidden")
        self.btn_limpar.bind("<Button-1>", lambda e: self.var_busca.set(""))
        self.var_busca.trace_add("write", lambda *a: self._ao_digitar())
        self.entry_busca.bind("<Escape>", lambda e: self.var_busca.set(""))
        self.entry_busca.bind("<FocusIn>", lambda e: self._desenhar_busca(True))
        self.entry_busca.bind("<FocusOut>", lambda e: self._desenhar_busca(False))
        self._desenhar_busca(False)

        # pílulas das categorias
        # quebram em mais linhas quando não cabem (_arrumar_pilulas)
        self.barra_pilulas = tk.Frame(f, bg=p["fundo"], height=34)
        self.barra_pilulas.pack(fill="x", padx=(24, 24), pady=(12, 6))
        self.barra_pilulas.bind("<Configure>", lambda e: self._arrumar_pilulas())

        # grade com rolagem
        area = tk.Frame(f, bg=p["fundo"])
        area.pack(fill="both", expand=True, padx=(24 - self.MARGEM, 12))
        self.canvas = tk.Canvas(area, bg=p["fundo"], highlightthickness=0)
        # barra de rolagem fina, desenhada na cor do tema (a do Windows é branca)
        self.trilho = tk.Canvas(area, width=10, bg=p["fundo"], highlightthickness=0)
        self.trilho.bind("<Button-1>", self._arrastar_trilho)
        self.trilho.bind("<B1-Motion>", self._arrastar_trilho)
        self._rolagem = (0.0, 1.0)
        self.grade = tk.Frame(self.canvas, bg=p["fundo"])
        self._janela_grade = self.canvas.create_window((0, 0), window=self.grade, anchor="nw")
        self.canvas.configure(yscrollcommand=self._mover_trilho)
        self.trilho.pack(side="right", fill="y", pady=(0, 16))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.grade.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._ao_mudar_largura)
        self.canvas.bind_all("<MouseWheel>", self._rolar)
        self.lbl_vazio = tk.Label(self.grade, text="", font=(FONTE, 11), fg=p["texto2"], bg=p["fundo"],
                                  justify="left")

    def _desenhar_busca(self, foco=None):
        if foco is not None:
            self._foco_busca = foco
        p, c = self.app.paleta, self.caixa_busca
        c.delete("fundo")
        c.config(bg=p["fundo"])
        borda = misturar(AZUL, p["fundo"], 0.7) if self._foco_busca else p["borda"]
        BarraSessao._retangulo(c, 0, 0, 269, 35, 12, fill=borda, outline="", tags="fundo")
        BarraSessao._retangulo(c, 1, 1, 268, 34, 11, fill=p["superficie"], outline="", tags="fundo")
        c.create_text(18, 18, text="\uE721", font=("Segoe MDL2 Assets", 9), fill=p["fraco"], tags="fundo")
        c.tag_lower("fundo")

    def _desenhar_qtd(self, texto):
        """O chip ao lado do título: "6 liberados" (ou "2 de 6" filtrando)."""
        self._texto_qtd = texto
        p, c = self.app.paleta, self.lbl_qtd
        fonte = tkfont.Font(family="Consolas", size=8)
        w = fonte.measure(texto) + 18
        c.delete("all")
        c.config(width=w + 2, bg=p["fundo"])
        BarraSessao._retangulo(c, 0, 0, w, 21, 7, fill=p["borda"], outline="")
        BarraSessao._retangulo(c, 1, 1, w - 1, 20, 6, fill=p["superficie"], outline="")
        c.create_text(w / 2, 11, text=texto, font=fonte, fill=p["texto2"])

    def marcar_abertos(self, processos):
        """O dock avisa quais apps estão abertos: o card troca "Pronto" por "Aberto"."""
        processos = set(processos)
        if processos == self.abertos:
            return
        self.abertos = processos
        for c in self.cartoes.values():
            aberto = (c["app"].get("processo") or "").strip().lower() in processos
            rotulo = "Aberto" if aberto else "Pronto"
            c["canvas"].itemconfig("status", text=("● " if aberto else "") + rotulo,
                                   fill=EMERALD_TEXTO if aberto else self.app.paleta["fraco"])

    def _mover_trilho(self, primeiro, ultimo):
        self._rolagem = (float(primeiro), float(ultimo))
        self._desenhar_trilho()

    def _desenhar_trilho(self):
        t = self.trilho
        t.delete("all")
        primeiro, ultimo = self._rolagem
        if primeiro <= 0 and ultimo >= 1:
            return  # cabe tudo: sem barra
        h = t.winfo_height()
        y0, y1 = max(5, primeiro * h), min(h - 5, ultimo * h)
        t.create_line(5, y0, 5, max(y0 + 1, y1), width=6, capstyle="round", fill=self.app.paleta["superficie3"])

    def _arrastar_trilho(self, event):
        primeiro, ultimo = self._rolagem
        meio = (ultimo - primeiro) / 2
        self.canvas.yview_moveto(max(0.0, event.y / max(1, self.trilho.winfo_height()) - meio))

    def _rolar(self, event):
        if not self.app.sessao_ativa:
            return
        if self.grade.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── dados da sessão ──
    def mostrar(self, apps):
        """Apps da whitelist com caminho (os que dá para abrir)."""
        for c in self.cartoes.values():
            c["canvas"].destroy()
        self.cartoes = {}
        self.apps = list(apps)
        self.chave = "todos"
        self.var_busca.set("")
        larg, alt = self.CARD_W + 2 * self.MARGEM, self.CARD_H + 2 * self.MARGEM
        for i, a in enumerate(self.apps):
            cv = tk.Canvas(self.grade, width=larg, height=alt, bg=self.app.paleta["fundo"],
                           highlightthickness=0, cursor="hand2")
            self.cartoes[i] = {"canvas": cv, "app": a, "normal": None, "hover": None, "sobre": False}
            cv.bind("<Button-1>", lambda e, a=a: self.app._abrir_app(a))
            cv.bind("<Enter>", lambda e, i=i: self._sobre(i, True))
            cv.bind("<Leave>", lambda e, i=i: self._sobre(i, False))
            self._desenhar_cartao(i)
            url = (a.get("imagem_url") or "").strip()
            if url and PIL_AVAILABLE and url not in self._capas:
                self._capas[url] = ...
                threading.Thread(target=self._baixar_capa, args=(url,), daemon=True).start()
        self._montar_pilulas()
        self._filtrar()
        self.canvas.yview_moveto(0)
        self.canvas.bind_all("<MouseWheel>", self._rolar)  # o _voltar_login tira de tudo
        menu = getattr(self.app, "_menu", None)
        if menu:
            menu.definir_quantidade(len(self.apps))

    def _baixar_capa(self, url):
        dados = baixar_imagem(url)  # thread: nada de Tkinter aqui
        self.app.root.after(0, lambda: self._capa_baixada(url, dados))

    def _capa_baixada(self, url, dados):
        self._capas[url] = dados
        for i, c in self.cartoes.items():
            if (c["app"].get("imagem_url") or "").strip() == url:
                c["normal"] = c["hover"] = None
                self._desenhar_cartao(i)

    # ── cards ──
    def _desenhar_cartao(self, i):
        c = self.cartoes.get(i)
        if not c:
            return
        p = self.app.paleta
        a = c["app"]
        cor = cor_do_app(a, p["destaque"])
        dados = self._capas.get((a.get("imagem_url") or "").strip())
        if dados is ...:
            dados = None
        cv = c["canvas"]
        cv.delete("all")
        c["desloc"] = 0  # a animação de entrada recomeça daqui
        cv.config(bg=p["fundo"])
        M, W, H, CH = self.MARGEM, self.CARD_W, self.CARD_H, self.CAPA_H
        if PIL_AVAILABLE:
            if c["normal"] is None:
                args = (dados, W, H, CH, p["fundo"], p["superficie"], p["borda"], cor, M)
                c["normal"] = ImageTk.PhotoImage(montar_cartao(*args))
                c["hover"] = ImageTk.PhotoImage(montar_cartao(*args, brilho=True))
            cv.create_image(0, 0, anchor="nw", image=c["hover"] if c["sobre"] else c["normal"], tags="capa")
        else:
            BarraSessao._retangulo(cv, M, M, M + W, M + H, 14, fill=p["superficie"], outline=p["borda"], tags="capa")
        nome = a.get("nome") or ""
        letra = nome[:1].upper() or "?"
        if not dados:  # sem capa: a inicial grande no meio da capa
            cv.create_text(M + W / 2, M + CH / 2 - 4, text=letra, fill=misturar(cor, TEXTO_CLARO, 0.35),
                           font=(FONTE, 36, "bold"))
        # selo da categoria no canto de cima, à esquerda (fundo translúcido e borda na cor)
        categoria = (a.get("categoria") or "").strip() or "Outros"
        fonte_selo = tkfont.Font(family=FONTE, size=7, weight="bold")
        texto_selo, limite = categoria.upper(), W - 24
        while fonte_selo.measure(texto_selo) + 16 > limite and len(texto_selo) > 2:
            texto_selo = texto_selo[:-2].rstrip() + "…"  # não quebra em duas linhas
        larg = fonte_selo.measure(texto_selo) + 16
        BarraSessao._retangulo(cv, M + 10, M + 10, M + 10 + larg, M + 30, 8, fill=misturar(cor, ZINC_950, 0.5),
                               outline="")
        BarraSessao._retangulo(cv, M + 11, M + 11, M + 9 + larg, M + 29, 7, fill=misturar(cor, ZINC_950, 0.2),
                               outline="")
        cv.create_text(M + 10 + larg / 2, M + 20, text=texto_selo, fill=misturar(cor, TEXTO_CLARO, 0.45),
                       font=fonte_selo)
        # ícone (w-9 h-9 rounded-xl) sobre a borda de baixo da capa
        y_ic = M + CH - 18
        BarraSessao._retangulo(cv, M + 12, y_ic, M + 48, y_ic + 36, 11, fill=misturar(cor, ZINC_950, 0.55),
                               outline="")
        BarraSessao._retangulo(cv, M + 13, y_ic + 1, M + 47, y_ic + 35, 10, fill=misturar(cor, ZINC_900, 0.3),
                               outline="")
        glifo = icone_da_categoria(categoria)
        cv.create_text(M + 30, y_ic + 18, text=glifo or letra, fill=misturar(cor, TEXTO_CLARO, 0.55),
                       font=("Segoe MDL2 Assets", 12) if glifo else (FONTE, 13, "bold"))
        # rodapé: título, descrição curta (2 linhas) e o Abrir à direita
        e = self.escala  # Configurações → tamanho do texto
        fonte_desc = tkfont.Font(family=FONTE, size=8 + e)
        descricao = (a.get("descricao") or "").strip() or (categoria if categoria != "Outros" else "Aplicativo")
        cv.create_text(M + 14, M + CH + 26, anchor="nw", text=nome, fill=p["texto"], width=W - 28,
                       font=(FONTE, 10 + e, "bold"))
        cv.create_text(M + 14, M + CH + 46 + e * 2, anchor="nw", text=cortar_linhas(descricao, fonte_desc, W - 28),
                       fill=p["texto2"], font=fonte_desc)
        aberto = (a.get("processo") or "").strip().lower() in self.abertos
        rotulo = "Aberto" if aberto else "Pronto"
        cv.create_text(M + 14, M + H - 26, anchor="w", text=("● " if aberto else "") + rotulo,
                       fill=EMERALD_TEXTO if aberto else p["fraco"], font=(FONTE, 8), tags="status")
        fonte_btn = tkfont.Font(family=FONTE, size=9, weight="bold")
        bx1, by1 = M + W - 12, M + H - 12
        bx0, by0 = bx1 - fonte_btn.measure("Abrir") - 28, by1 - 28
        BarraSessao._retangulo(cv, bx0 + 1, by0 + 3, bx1 + 1, by1 + 3, 10, fill=misturar(AZUL, p["superficie"], 0.25),
                               outline="")  # shadow-blue-600/20
        BarraSessao._retangulo(cv, bx0, by0, bx1, by1, 10, fill=AZUL, outline="", tags=("abrir",))
        cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="Abrir", fill=TEXTO_CLARO, font=fonte_btn,
                       tags=("abrir_txt",))
        for tag in ("abrir", "abrir_txt"):
            cv.tag_bind(tag, "<Enter>", lambda e, cv=cv: cv.itemconfig("abrir", fill=AZUL_CLARO))
            cv.tag_bind(tag, "<Leave>", lambda e, cv=cv: cv.itemconfig("abrir", fill=AZUL))
        if c["sobre"]:
            cv.move("all", 0, -self.SUBIR)

    def _sobre(self, i, sim):
        c = self.cartoes.get(i)
        if not c or c["sobre"] == sim:
            return
        c["sobre"] = sim
        cv = c["canvas"]
        if c["normal"] is not None:  # só troca a imagem e sobe: sem redesenhar (não pisca)
            cv.itemconfig("capa", image=c["hover"] if sim else c["normal"])
        cv.move("all", 0, -self.SUBIR if sim else self.SUBIR)

    # ── pílulas e filtro ──
    def _cor_da_chave(self, chave):
        if chave.startswith("cat:"):
            for a in self.apps:
                if (a.get("categoria") or "").strip() == chave[4:]:
                    return cor_do_app(a, self.app.paleta["destaque"])
        return self.app.paleta["destaque"]

    def _montar_pilulas(self):
        for w in self.barra_pilulas.winfo_children():
            w.destroy()
        self._pilulas = []
        p = self.app.paleta
        fonte = tkfont.Font(family=FONTE, size=9, weight="bold")
        for chave, rotulo, n in categorias_da_tela(self.apps):
            largura = fonte.measure(rotulo) + 30
            cv = tk.Canvas(self.barra_pilulas, width=largura, height=34, bg=p["fundo"], highlightthickness=0,
                           cursor="hand2")
            cv.bind("<Button-1>", lambda e, k=chave: self.escolher(k))
            cv.bind("<Enter>", lambda e, k=chave: self._pintar_pilulas(sobre=k))
            cv.bind("<Leave>", lambda e: self._pintar_pilulas())
            self._pilulas.append((chave, rotulo, self._cor_da_chave(chave), cv, fonte))
        self._pintar_pilulas()
        self._arrumar_pilulas()

    def _pintar_pilulas(self, sobre=None):
        p = self.app.paleta
        for chave, texto, cor, cv, fonte in self._pilulas:
            cv.delete("all")
            cv.config(bg=p["fundo"])
            w, h = int(cv.cget("width")), int(cv.cget("height"))
            if chave == self.chave:
                BarraSessao._retangulo(cv, 0, 0, w - 1, h - 1, 12, fill=AZUL, outline="")
                cor_texto = TEXTO_CLARO
            else:
                BarraSessao._retangulo(cv, 0, 0, w - 1, h - 1, 12, fill=p["borda"], outline="")
                BarraSessao._retangulo(cv, 1, 1, w - 2, h - 2, 11,
                                       fill=p["superficie2"] if chave == sobre else p["superficie"], outline="")
                cor_texto = p["texto"] if chave == sobre else p["texto2"]
            cv.create_text(w / 2, h / 2, text=texto, fill=cor_texto, font=fonte)

    def _arrumar_pilulas(self):
        """Uma ao lado da outra; a que não cabe desce para a linha de baixo."""
        largura = max(200, self.barra_pilulas.winfo_width())
        x = y = 0
        for _, _, _, cv, _ in self._pilulas:
            w = int(cv.cget("width"))
            if x and x + w > largura:
                x, y = 0, y + 42
            cv.place(x=x, y=y)
            x += w + 8
        altura = y + 34 if self._pilulas else 34
        if int(self.barra_pilulas.cget("height")) != altura:
            self.barra_pilulas.config(height=altura)

    def escolher(self, chave):
        self.chave = chave
        self._pintar_pilulas()
        self._filtrar()
        self.canvas.yview_moveto(0)
        self.animar_entrada()

    # ── entrada suave dos cards (troca de aba e de página) ──
    # cada card sobe 12 px e aparece em ~0,2 s (ease-out), um depois do outro;
    # o "véu" com pontilhado do Tk (stipple) faz o papel do fade
    DESLOC_ENTRADA = (12, 7, 4, 2, 1, 0)
    VEU_ENTRADA = ("gray75", "gray50", "gray25", "gray12", "gray12", None)
    CASCATA_MS, PASSO_MS, MAX_ANIMADOS = 35, 35, 16

    def animar_entrada(self):
        self._gen_entrada = getattr(self, "_gen_entrada", 0) + 1
        gen = self._gen_entrada
        fundo = self.app.paleta["fundo"]
        for c in self.cartoes.values():  # desfaz uma animação que ficou no meio
            cv = c["canvas"]
            if c.get("desloc"):
                cv.move("all", 0, -c["desloc"])
                c["desloc"] = 0
            cv.delete("veu")
        for n, i in enumerate(getattr(self, "_visiveis", [])[:self.MAX_ANIMADOS]):
            c = self.cartoes[i]
            cv = c["canvas"]
            w, h = int(cv.cget("width")), int(cv.cget("height"))
            cv.create_rectangle(-4, -30, w + 4, h + 30, fill=fundo, outline="", stipple=self.VEU_ENTRADA[0], tags="veu")
            cv.move("all", 0, self.DESLOC_ENTRADA[0])
            c["desloc"] = self.DESLOC_ENTRADA[0]
            self.app.root.after(n * self.CASCATA_MS, lambda i=i: self._passo_entrada(i, gen, 1))

    def _passo_entrada(self, i, gen, k):
        if gen != getattr(self, "_gen_entrada", 0):
            return
        c = self.cartoes.get(i)
        if not c or not c["canvas"].winfo_exists():
            return
        cv = c["canvas"]
        alvo = self.DESLOC_ENTRADA[k]
        cv.move("all", 0, alvo - c.get("desloc", 0))
        c["desloc"] = alvo
        if self.VEU_ENTRADA[k]:
            cv.itemconfig("veu", stipple=self.VEU_ENTRADA[k])
        else:
            cv.delete("veu")
        if k < len(self.DESLOC_ENTRADA) - 1:
            self.app.root.after(self.PASSO_MS, lambda: self._passo_entrada(i, gen, k + 1))

    def _ao_digitar(self):
        texto = self.var_busca.get()
        if texto:
            self.caixa_busca.itemconfig(self._janela_dica, state="hidden")
            self.caixa_busca.itemconfig(self._janela_limpar, state="normal")
            if self.chave != "todos":  # a pesquisa procura em todos os apps
                self.chave = "todos"
                self._pintar_pilulas()
        else:
            self.caixa_busca.itemconfig(self._janela_dica, state="normal")
            self.caixa_busca.itemconfig(self._janela_limpar, state="hidden")
        self._filtrar()
        self.canvas.yview_moveto(0)

    def _rotulo(self, chave):
        for k, rotulo, _ in categorias_da_tela(self.apps):
            if k == chave:
                return rotulo
        return "Todos"

    def _filtrar(self):
        busca = self.var_busca.get().strip()
        visiveis = filtrar_apps(self.apps, self.chave, busca)
        ids = {id(a) for a in visiveis}
        total = len(self.apps)
        self._desenhar_qtd(f"{total} liberados" if len(visiveis) == total else f"{len(visiveis)} de {total}")
        for c in self.cartoes.values():
            c["canvas"].grid_forget()
        self.lbl_vazio.grid_forget()
        self._visiveis = [i for i, c in self.cartoes.items() if id(c["app"]) in ids]
        if not self.apps:
            self.lbl_vazio.config(text="Nenhum app liberado nesta estação.\nPeça ajuda a um funcionário.")
            self.lbl_vazio.grid(row=0, column=0, sticky="w", padx=self.MARGEM, pady=20)
        elif not self._visiveis:
            self.lbl_vazio.config(text=f'Nenhum app encontrado com "{busca}".' if busca else "Nenhum app aqui.")
            self.lbl_vazio.grid(row=0, column=0, sticky="w", padx=self.MARGEM, pady=20)
        self._posicionar()

    def _ao_mudar_largura(self, event):
        passo = self.CARD_W + 2 * self.MARGEM + self.ESPACO
        colunas = max(1, (event.width + self.ESPACO) // passo)
        if colunas != self._colunas:
            self._colunas = colunas
            self._posicionar()

    def _posicionar(self):
        colunas = self._colunas or 4
        for n, i in enumerate(getattr(self, "_visiveis", [])):
            linha, col = divmod(n, colunas)
            self.cartoes[i]["canvas"].grid(row=linha, column=col, padx=(0, self.ESPACO), pady=(0, self.ESPACO))

    def redesenhar(self):
        """Tema ou cor do piso trocados: refaz os cards e as pílulas."""
        for i, c in self.cartoes.items():
            c["normal"] = c["hover"] = None
            self._desenhar_cartao(i)
        self._montar_pilulas()
        self._desenhar_trilho()
        self._desenhar_busca()
        self._desenhar_qtd(self._texto_qtd or "0 liberados")

    def limpar(self):
        self.escala = 0  # a preferência é só da sessão
        self.abertos = set()
        self.mostrar([])


class TelaLogin:
    """Metade direita do login do PC: os cartazes da Programação cobrindo a
    metade, com degradê para o fundo embaixo e o título do cartaz digitando
    entre aspas. Os cartazes passam sozinhos (fade). Sem cartaz, um fundo na
    cor do piso com uma frase de boas-vindas."""
    BOAS_VINDAS = "Bem-vindo(a) à biblioteca! Faça login para começar."

    def __init__(self, app, frame):
        self.app = app
        self.canvas = tk.Canvas(frame, bg=app.paleta["fundo"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._ao_mudar_tamanho)
        self.cartazes = []  # [(titulo, imagem PIL)]
        self.segundos = 10
        self.indice = 0
        self._tam = (0, 0)
        self._timer = self._digitando = self._fade = None
        self._foto = None
        self._atual = None
        self._frase, self._n, self._cursor = "", 0, True

    def definir(self, cartazes, segundos):
        """Chamado pela Programacao sempre que os cartazes chegam do servidor."""
        self.cartazes = list(cartazes)
        self.segundos = max(3, int(segundos or 10))
        self.indice = 0
        self._mostrar()

    def _ao_mudar_tamanho(self, event):
        if (event.width, event.height) != self._tam:
            self._tam = (event.width, event.height)
            self._atual = None
            self._mostrar(reiniciar_texto=False)

    def _imagem(self, w, h):
        p = self.app.paleta
        fundo = _cor_rgb(p["fundo"])
        if self.cartazes:
            # o cartaz inteiro, em cima, sobre ele mesmo ampliado e desfocado
            cartaz = self.cartazes[self.indice % len(self.cartazes)][1].convert("RGB")
            img = _preencher(cartaz, max(1, w // 4), max(1, h // 4)).filter(ImageFilter.GaussianBlur(6))
            img = Image.blend(img.resize((w, h), Image.BILINEAR), Image.new("RGB", (w, h), (0, 0, 0)), 0.5)
            caixa_l, caixa_a = max(1, w - 120), max(1, h - 200)
            escala = min(caixa_l / cartaz.width, caixa_a / cartaz.height)
            largo, alto = max(1, round(cartaz.width * escala)), max(1, round(cartaz.height * escala))
            x, y = (w - largo) // 2, 36
            sombra = Image.new("L", (w, h), 0)
            ImageDraw.Draw(sombra).rounded_rectangle((x + 4, y + 10, x + largo + 4, y + alto + 10), 12, fill=160)
            img.paste((0, 0, 0), (0, 0), sombra.filter(ImageFilter.GaussianBlur(12)))
            peca = cartaz.resize((largo, alto), Image.LANCZOS)
            mascara = _cantos(Image.new("RGB", (largo, alto), (255, 255, 255)), 10, "#000000").convert("L")
            img.paste(peca, (x, y), mascara)
        else:  # sem cartaz: degradê da cor do piso para o fundo
            img = Image.new("RGB", (w, h), _cor_rgb(p["destaque"]))
            vertical = Image.linear_gradient("L").resize((w, h))
            horizontal = Image.linear_gradient("L").rotate(90).resize((w, h))  # 0 à esquerda
            diagonal = Image.blend(vertical, horizontal, 0.5)  # cor do piso no canto de cima, à esquerda
            img.paste(fundo, (0, 0), diagonal)
        embaixo = Image.linear_gradient("L").resize((w, h))  # 0 em cima, 255 embaixo
        # degradê para o fundo só na faixa da frase, embaixo
        img.paste(fundo, (0, 0), embaixo.point(lambda v: int(min(1.0, max(0.0, (v / 255 - 0.72) / 0.2)) * 255)))
        return img

    def _mostrar(self, reiniciar_texto=True):
        for t in (self._timer, self._fade):
            if t:
                self.app.root.after_cancel(t)
        self._timer = self._fade = None
        c, p = self.canvas, self.app.paleta
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50 or not PIL_AVAILABLE:
            return  # ainda sem tamanho: o <Configure> chama de novo
        c.config(bg=p["fundo"])
        if self.cartazes:
            frase = self.cartazes[self.indice % len(self.cartazes)][0] or "Programação da biblioteca"
            assinatura = "Programação da biblioteca"
        else:
            frase, assinatura = self.BOAS_VINDAS, "MatheCafé"
        novo = self._imagem(w, h)
        if not c.find_withtag("img"):
            c.create_image(0, 0, anchor="nw", tags="img")
            c.create_text(0, 0, anchor="s", tags="frase", justify="center")
            c.create_text(0, 0, anchor="s", tags="assinatura")
        c.coords("frase", w / 2, h - 78)
        c.itemconfig("frase", width=max(200, w - 120), fill=p["texto"], font=(FONTE, 18, "bold"))
        c.coords("assinatura", w / 2, h - 44)
        c.itemconfig("assinatura", text="— " + assinatura, fill=p["texto2"], font=(FONTE, 10))
        if reiniciar_texto and self._atual is not None and self._atual.size == novo.size:
            self._animar(self._atual, novo, 1)
        else:
            self._pintar(novo)
        if reiniciar_texto or frase != self._frase:
            self._frase, self._n = frase, 0
        if not self._digitando:
            self._digitar()
        if len(self.cartazes) > 1:
            self._timer = self.app.root.after(self.segundos * 1000, self._proximo)

    def _pintar(self, img, guardar=True):
        self._foto = ImageTk.PhotoImage(img)
        self.canvas.itemconfig("img", image=self._foto)
        if guardar:
            self._atual = img

    def _animar(self, de, para, passo, passos=10):
        """Fade entre dois cartazes (~0,3 s)."""
        if passo >= passos:
            self._fade = None
            self._pintar(para)
            return
        self._pintar(Image.blend(de, para, passo / passos), guardar=False)
        self._fade = self.app.root.after(30, lambda: self._animar(de, para, passo + 1, passos))

    def _digitar(self):
        """A frase aparece letra a letra; depois o cursor fica piscando."""
        if self._n < len(self._frase):
            self._n += 1
            self._cursor, espera = True, 45
        else:
            self._cursor, espera = not self._cursor, 530
        self.canvas.itemconfig("frase", text="“" + self._frase[:self._n] + ("|" if self._cursor else " ") + "”")
        self._digitando = self.app.root.after(espera, self._digitar)

    def _proximo(self):
        self._timer = None
        if self.app.sessao_ativa:  # escondido durante a sessão: só agenda o próximo
            self._timer = self.app.root.after(self.segundos * 1000, self._proximo)
            return
        self.indice += 1
        self._mostrar()

    def redesenhar(self):
        """Tema ou cor do piso trocados."""
        self._atual = None
        self._mostrar(reiniciar_texto=False)


def avatar_degrade(lado, raio, fundo):
    """Quadrado arredondado em degradê azul -> índigo (bg-gradient-to-tr from-blue-600 to-indigo-600)."""
    a = Image.new("RGB", (lado, lado), _cor_rgb(AZUL))
    b = Image.new("RGB", (lado, lado), _cor_rgb("#4f46e5"))
    mascara = Image.linear_gradient("L").rotate(45, expand=True).resize((lado, lado))
    img = Image.composite(b, a, mascara)
    return _cantos(img, raio, fundo)


def _linha_menu(cv, largura, altura, rotulo, icone, aberto, escolhido, sobre, paleta, contagem=None):
    """Um botão do menu (rounded-xl, ícone 16 px): escolhido em azul translúcido."""
    p = paleta
    cv.delete("all")
    cv.config(width=largura, bg=p["fundo"])
    if escolhido:
        BarraSessao._retangulo(cv, 0, 0, largura - 1, altura - 1, 12, fill=misturar(AZUL, p["fundo"], 0.45), outline="")
        BarraSessao._retangulo(cv, 1, 1, largura - 2, altura - 2, 11, fill=misturar(AZUL, p["fundo"], 0.14), outline="")
    elif sobre:
        BarraSessao._retangulo(cv, 0, 0, largura - 1, altura - 1, 12, fill=p["superficie"], outline="")
    cor_icone = AZUL_CLARO if escolhido else p["texto2"]
    cor_texto = p["texto"] if (escolhido or sobre) else p["texto2"]
    x_icone = 22 if aberto else largura / 2
    cv.create_text(x_icone, altura / 2, text=icone, font=("Segoe MDL2 Assets", 11), fill=cor_icone)
    if aberto:
        cv.create_text(44, altura / 2, anchor="w", text=rotulo, font=(FONTE, 9, "bold" if escolhido else "normal"),
                       fill=cor_texto)
        if contagem is not None:
            texto = str(contagem)
            larg = tkfont.Font(family="Consolas", size=7).measure(texto) + 12
            BarraSessao._retangulo(cv, largura - 12 - larg, altura / 2 - 9, largura - 12, altura / 2 + 9, 6,
                                   fill=p["borda"], outline="")
            BarraSessao._retangulo(cv, largura - 11 - larg, altura / 2 - 8, largura - 13, altura / 2 + 8, 5,
                                   fill=p["superficie"], outline="")
            cv.create_text(largura - 12 - larg / 2, altura / 2, text=texto, font=("Consolas", 7), fill=p["texto2"])


class MenuLateral:
    """Menu da esquerda da Área do Cliente (9.13): só a marca no topo, os links
    (Início e Meus Apps) e Configurações no rodapé. Recolhe de 240 para 64 px.
    O cliente aparece no card da sessão, à direita (sem repetir aqui)."""
    LARGURA_ABERTO, LARGURA_FECHADO = 240, 64
    ITENS = [("inicio", "Início", ""), ("apps", "Meus Apps", "")]
    RODAPE = ("config", "Configurações", "")
    ALTURA_LINHA = 38

    def __init__(self, app, frame):
        self.app = app
        self.frame = frame
        self.aberto = True
        self.quantidade = 0
        self._linhas = {}  # chave -> (canvas, rótulo, ícone)
        self._montar()

    def _montar(self):
        p = self.app.paleta
        f = self.frame
        f.config(width=self.LARGURA_ABERTO, bg=p["fundo"], highlightthickness=1, highlightbackground=p["borda"])
        f.pack_propagate(False)
        # marca: quadrado azul com o M, nome e o botão de recolher
        self.topo = tk.Canvas(f, height=60, bg=p["fundo"], highlightthickness=0)
        self.topo.pack(fill="x")
        self.topo.bind("<Configure>", lambda e: self._desenhar_topo())
        self.topo.tag_bind("recolher", "<Button-1>", lambda e: self.alternar())
        self.lbl_menu = tk.Label(f, text="NAVEGAÇÃO", font=(FONTE, 7, "bold"), fg=p["fraco"], bg=p["fundo"])
        self.lbl_menu.pack(anchor="w", padx=20, pady=(18, 8))
        for chave, rotulo, icone in self.ITENS:
            self._linha(chave, rotulo, icone).pack(fill="x", padx=10, pady=2)
        chave, rotulo, icone = self.RODAPE
        rodape = tk.Frame(f, bg=p["fundo"])
        rodape.pack(side="bottom", fill="x", pady=(0, 12))
        self._linha(chave, rotulo, icone, rodape).pack(fill="x", padx=10)
        self.pintar()

    def _linha(self, chave, rotulo, icone, pai=None):
        cv = tk.Canvas(pai or self.frame, height=self.ALTURA_LINHA, highlightthickness=0, cursor="hand2")
        cv.bind("<Button-1>", lambda e, k=chave: self.app._mostrar_pagina(k))
        cv.bind("<Enter>", lambda e, k=chave: self.pintar(sobre=k))
        cv.bind("<Leave>", lambda e: self.pintar())
        cv.bind("<Configure>", lambda e: self.pintar())
        self._linhas[chave] = (cv, rotulo, icone)
        return cv

    def _desenhar_topo(self):
        p = self.app.paleta
        c = self.topo
        c.delete("all")
        c.config(bg=p["fundo"])
        w = c.winfo_width() or self.LARGURA_ABERTO
        c.create_line(0, 59, w, 59, fill=p["borda"])
        x = 16 if self.aberto else (w - 30) / 2
        BarraSessao._retangulo(c, x, 15, x + 30, 45, 9, fill=AZUL, outline="", tags="recolher" if not self.aberto else "")
        c.create_text(x + 15, 30, text="M", fill=TEXTO_CLARO, font=(FONTE, 11, "bold"),
                      tags="recolher" if not self.aberto else "")
        if self.aberto:
            c.create_text(x + 42, 23, anchor="w", text="MatheCafé", fill=p["texto"], font=(FONTE, 9, "bold"))
            c.create_text(x + 42, 38, anchor="w", text="Sistema de Estações", fill=p["texto2"], font=(FONTE, 7))
            c.create_text(w - 22, 30, text="", font=("Segoe MDL2 Assets", 9), fill=p["texto2"], tags="recolher")
            c.tag_bind("recolher", "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind("recolher", "<Leave>", lambda e: c.config(cursor=""))

    def definir_quantidade(self, n):
        self.quantidade = n
        self.pintar()

    def pintar(self, sobre=None):
        p = self.app.paleta
        pagina = getattr(self.app, "_pagina", "inicio")
        for chave, (cv, rotulo, icone) in self._linhas.items():
            largura = max(40, cv.winfo_width())
            _linha_menu(cv, largura, self.ALTURA_LINHA, rotulo, icone, self.aberto, chave == pagina, chave == sobre, p,
                        contagem=self.quantidade if chave == "apps" else None)

    def alternar(self):
        """Recolhe (só os ícones) ou abre de novo."""
        self.aberto = not self.aberto
        self.frame.config(width=self.LARGURA_ABERTO if self.aberto else self.LARGURA_FECHADO)
        if self.aberto:
            self.lbl_menu.config(text="NAVEGAÇÃO")
        else:
            self.lbl_menu.config(text="")
        self.app.root.after(10, lambda: (self._desenhar_topo(), self.pintar()))

    def redesenhar(self):
        self.frame.config(bg=self.app.paleta["fundo"], highlightbackground=self.app.paleta["borda"])
        self._desenhar_topo()
        self.pintar()


class PainelDireito:
    """Coluna da direita (9.13): o card da sessão com o cliente no topo (avatar,
    nome, estação, login e Online), o tempo restante e a barra; embaixo, os Avisos
    da biblioteca, cada um num card com o chip do tipo e o horário."""
    LARGURA = 300
    CARD_W = 268
    # o chip e o ícone de cada tipo de aviso (o admin escolhe no painel)
    TIPOS = {
        "alerta": ("#f59e0b", ""),  # âmbar, triângulo
        "evento": ("#8b5cf6", ""),  # violeta, calendário
        "info": ("#3b82f6", ""),  # azul, i
    }
    CARD_H = 196

    def __init__(self, app, frame):
        self.app = app
        self.frame = frame
        self.avisos = []
        self._geracao = 0
        self._restante = 0.0
        self.nome, self.login, self.online = "", "", False
        self._avatar = None
        self._montar()

    def _montar(self):
        p = self.app.paleta
        self.frame.config(width=self.LARGURA, bg=p["fundo"])
        self.frame.pack_propagate(False)
        self.card = tk.Canvas(self.frame, width=self.CARD_W, height=self.CARD_H, bg=p["fundo"], highlightthickness=0)
        self.card.pack(anchor="n", pady=(20, 18))
        cab = tk.Frame(self.frame, bg=p["fundo"])
        cab.pack(fill="x", padx=(16, 16))
        tk.Label(cab, text="AVISOS DA BIBLIOTECA", font=(FONTE, 7, "bold"), fg=p["fraco"], bg=p["fundo"]).pack(side="left")
        self.lista = tk.Frame(self.frame, bg=p["fundo"])
        self.lista.pack(fill="both", expand=True, pady=(8, 16))
        self._desenhar_card()
        self._mostrar_avisos(self._geracao, [])

    # ── card da sessão ──
    def definir_cliente(self, nome, login):
        self.nome, self.login = nome or "", login or ""
        self._avatar = None
        self._desenhar_card()

    def definir_status(self, online):
        self.online = online
        self._desenhar_card()

    def _desenhar_card(self):
        p = self.app.paleta
        c, W, H = self.card, self.CARD_W, self.CARD_H
        c.delete("all")
        c.config(bg=p["fundo"])
        BarraSessao._retangulo(c, 0, 0, W - 1, H - 1, 16, fill=p["borda"], outline="")
        BarraSessao._retangulo(c, 1, 1, W - 2, H - 2, 15, fill=p["superficie"], outline="")
        # cliente: avatar em degradê, nome, estação, login e Online
        if PIL_AVAILABLE:
            if self._avatar is None:
                self._avatar = ImageTk.PhotoImage(avatar_degrade(40, 12, p["superficie"]))
            c.create_image(18, 18, anchor="nw", image=self._avatar)
        else:
            BarraSessao._retangulo(c, 18, 18, 58, 58, 12, fill=AZUL, outline="")
        c.create_text(38, 38, text=(self.nome[:1] or "?").upper(), fill=TEXTO_CLARO, font=(FONTE, 12, "bold"))
        c.create_oval(50, 50, 62, 62, fill=EMERALD if self.online else COR_OFFLINE, outline=p["superficie"], width=2)
        # nome inteiro se couber ao lado da estação e do Online; senão, o primeiro nome
        fonte_nome = tkfont.Font(family=FONTE, size=10, weight="bold")
        livre = W - 70 - 16 - 62 - tkfont.Font(family="Consolas", size=7).measure(self.app.estacao) - 18
        nome = self.nome if fonte_nome.measure(self.nome) <= livre or not self.nome.split() else self.nome.split()[0]
        id_nome = c.create_text(70, 30, anchor="w", text=nome, fill=p["texto"], font=fonte_nome)
        x = (c.bbox(id_nome) or (0, 0, 120, 0))[2] + 8
        fonte_mono = tkfont.Font(family="Consolas", size=7)
        estacao = self.app.estacao
        larg = fonte_mono.measure(estacao) + 10
        BarraSessao._retangulo(c, x, 22, x + larg, 38, 5, fill=misturar(AZUL, p["superficie"], 0.4), outline="")
        BarraSessao._retangulo(c, x + 1, 23, x + larg - 1, 37, 4, fill=misturar(AZUL, p["superficie"], 0.14),
                               outline="")
        c.create_text(x + larg / 2, 30, text=estacao, fill=AZUL_CLARO, font=fonte_mono)
        c.create_text(70, 47, anchor="w", text=f"Login: {self.login}" if self.login else "", fill=p["texto2"],
                      font=("Consolas", 7))
        cor = EMERALD if self.online else COR_OFFLINE
        rotulo = "Online" if self.online else "Offline"
        fonte_chip = tkfont.Font(family=FONTE, size=7, weight="bold")
        larg = fonte_chip.measure(rotulo) + 16
        BarraSessao._retangulo(c, W - 16 - larg, 28, W - 16, 48, 10, fill=misturar(cor, p["superficie"], 0.45),
                               outline="")
        BarraSessao._retangulo(c, W - 15 - larg, 29, W - 17, 47, 9, fill=misturar(cor, p["superficie"], 0.14),
                               outline="")
        c.create_text(W - 16 - larg / 2, 38, text=rotulo, fill=misturar(cor, TEXTO_CLARO, 0.75), font=fonte_chip)
        c.create_line(18, 76, W - 18, 76, fill=p["borda"])
        # tempo restante, início e limite, barra
        c.create_text(18, 96, anchor="w", text="TEMPO RESTANTE DE USO", fill=p["fraco"], font=(FONTE, 7, "bold"))
        c.create_text(18, 126, anchor="w", text="00:00:00", fill=p["texto"], font=("Consolas", 22, "bold"), tags="tempo")
        c.create_text(18, 152, anchor="w", text="", fill=p["fraco"], font=(FONTE, 7), tags="inicio")
        c.create_line(18, 174, W - 18, 174, width=6, capstyle="round", fill=p["superficie3"])
        c.create_line(18, 174, 19, 174, width=6, capstyle="round", fill=AZUL, tags="barra")
        self._atualizar_textos()

    def atualizar_tempo(self, restante, total):
        self._restante = (restante / total) if total else 0.0
        self._texto_tempo = (self.app._fmt(restante), restante < 300, total)
        self._atualizar_textos()

    def _atualizar_textos(self):
        c, p = self.card, self.app.paleta
        texto, alerta, total = getattr(self, "_texto_tempo", ("00:00:00", False, 0))
        c.itemconfig("tempo", text=texto, fill=ROSA_TEXTO if alerta else p["texto"])
        inicio = getattr(self.app, "inicio_sessao", None)
        if total and inicio:
            c.itemconfig("inicio", text=f"Sessão iniciada às {time.strftime('%H:%M', time.localtime(inicio))}  |  "
                                        f"Limite: {self.app._fmt(total)}")
        fim = 18 + (self.CARD_W - 36) * max(0.0, min(1.0, self._restante))
        c.coords("barra", 18, 174, max(19, fim), 174)
        c.itemconfig("barra", fill=ROSA if alerta else AZUL)

    # ── avisos ──
    def recarregar_avisos(self):
        self._geracao += 1
        threading.Thread(target=self._baixar, args=(self._geracao,), daemon=True).start()

    def _baixar(self, geracao):
        # thread: nada de Tkinter aqui
        base = self.app.servidor.replace("wss://", "https://").replace("ws://", "http://")
        try:
            with abrir_url(f"{base}/api/avisos/agente", timeout=5) as r:
                avisos = json.loads(r.read())
        except Exception as ex:
            self.app.incoming.put({"evento": "_info", "dados": {"msg": f"Avisos: nao carregou ({ex})"}})
            return
        self.app.root.after(0, lambda: self._mostrar_avisos(geracao, avisos))

    def _mostrar_avisos(self, geracao, avisos):
        if geracao != self._geracao:
            return  # um carregamento mais novo já está a caminho
        self.avisos = list(avisos or [])
        self._desenhar_avisos()

    def _desenhar_avisos(self):
        p = self.app.paleta
        for w in self.lista.winfo_children():
            w.destroy()
        if not self.avisos:
            tk.Label(self.lista, text="Nenhum aviso no momento.", font=(FONTE, 9), fg=p["fraco"],
                     bg=p["fundo"]).pack(anchor="w", padx=16)
            return
        W = self.CARD_W
        for aviso in self.avisos:
            cor, icone = self.TIPOS.get(aviso.get("tipo") or "info", self.TIPOS["info"])
            c = tk.Canvas(self.lista, width=W, height=60, bg=p["fundo"], highlightthickness=0)
            c.pack(anchor="n", pady=(0, 10))
            c.create_text(18, 20, text=icone, font=("Segoe MDL2 Assets", 9), fill=cor)
            c.create_text(32, 20, anchor="w", text=aviso.get("titulo") or "", fill=misturar(cor, p["texto"], 0.8),
                          font=(FONTE, 9, "bold"), width=W - 92)
            if aviso.get("horario"):
                c.create_text(W - 14, 20, anchor="e", text=aviso.get("horario"), fill=p["fraco"], font=("Consolas", 7))
            y = 36
            if aviso.get("texto"):
                t = c.create_text(16, y, anchor="nw", text=aviso["texto"], fill=p["texto2"], font=(FONTE, 8),
                                  width=W - 32)
                y = (c.bbox(t) or (0, 0, 0, y + 14))[3]
            h = y + 14
            c.config(height=h)
            fundo = BarraSessao._retangulo(c, 0, 0, W - 1, h - 1, 12, fill=p["borda"], outline="")
            dentro = BarraSessao._retangulo(c, 1, 1, W - 2, h - 2, 11, fill=p["superficie"], outline="")
            c.tag_lower(dentro)
            c.tag_lower(fundo)

    def redesenhar(self):
        self._avatar = None
        self._desenhar_card()
        self._desenhar_avisos()


class PaginaPreferencias:
    """Configurações do menu (9.13): tema e tamanho do texto dos cards, só para
    esta sessão do cliente (o tamanho volta ao normal no fim da sessão)."""

    def __init__(self, app, frame):
        self.app = app
        self.frame = frame
        p = app.paleta
        tk.Label(frame, text="Configurações", font=(FONTE, 14, "bold"), fg=p["texto"], bg=p["fundo"]).pack(
            anchor="w", padx=24, pady=(24, 2))
        tk.Label(frame, text="Valem só para você, nesta sessão.", font=(FONTE, 9), fg=p["texto2"],
                 bg=p["fundo"]).pack(anchor="w", padx=24, pady=(0, 18))
        self.opcoes = []  # [(canvas, rótulo, ativo(), ação)]
        self._grupo("TEMA", [("Escuro", lambda: self.app.tema == "escuro", lambda: self._tema("escuro")),
                             ("Claro", lambda: self.app.tema == "claro", lambda: self._tema("claro"))])
        self._grupo("TAMANHO DO TEXTO DOS APPS", [
            ("Normal", lambda: self.app._tela_apps.escala == 0, lambda: self._escala(0)),
            ("Grande", lambda: self.app._tela_apps.escala == 2, lambda: self._escala(2))])

    def _grupo(self, titulo, botoes):
        p = self.app.paleta
        tk.Label(self.frame, text=titulo, font=(FONTE, 7, "bold"), fg=p["fraco"], bg=p["fundo"]).pack(
            anchor="w", padx=24, pady=(6, 6))
        linha = tk.Frame(self.frame, bg=p["fundo"])
        linha.pack(anchor="w", padx=24, pady=(0, 14))
        for rotulo, ativo, acao in botoes:
            cv = tk.Canvas(linha, width=110, height=36, highlightthickness=0, cursor="hand2")
            cv.pack(side="left", padx=(0, 8))
            cv.bind("<Button-1>", lambda e, a=acao: (a(), self.redesenhar()))
            self.opcoes.append((cv, rotulo, ativo))
        self.redesenhar()

    def _tema(self, tema):
        if self.app.tema != tema:
            self.app.alternar_tema()

    def _escala(self, escala):
        self.app._tela_apps.escala = escala
        self.app._tela_apps.redesenhar()

    def redesenhar(self):
        p = self.app.paleta
        for cv, rotulo, ativo in self.opcoes:
            cv.delete("all")
            cv.config(bg=p["fundo"])
            sim = ativo()
            BarraSessao._retangulo(cv, 0, 0, 109, 35, 12, fill=AZUL if sim else p["borda"], outline="")
            BarraSessao._retangulo(cv, 1, 1, 108, 34, 11, fill=AZUL if sim else p["superficie"], outline="")
            cv.create_text(55, 18, text=rotulo, fill=TEXTO_CLARO if sim else p["texto2"], font=(FONTE, 9, "bold"))


class AgenteApp:
    def __init__(self, root, servidor, estacao):
        self.root = root
        self.servidor = servidor.rstrip("/")
        self.estacao = estacao
        # 1.14: o servidor reconhece o PC por este id (o nome pode ser trocado no painel)
        self.identificador = identificador_da_estacao()
        self.aprovada = True

        self.incoming = queue.Queue()
        self.loop = None
        self.ws = None
        self.conectado = False
        # Fim de sessao que aconteceu sem conexao: vai ao servidor ao reconectar
        # (lista de (mensagem, time.monotonic() do fim); so mexida na thread do Tk
        # e lida pela do WebSocket ao conectar)
        self._pendentes = []
        # log de quando estava sem servidor: vai com a hora original ao reconectar
        self._logs_offline = deque(maxlen=100)

        # Estado da sessão
        self.sessao_ativa = False
        self.sessao_id = None
        self.cliente_nome = None
        self.tempo_total = 0
        self.inicio_sessao = None
        self.whitelist_apps = []
        self.whitelist_procs = set()
        self.reiniciar_ao_encerrar = False
        self._credenciais_manutencao = None
        self.versao_nova = None  # versao do servidor mais nova que esta (6.13)
        self._img_refs = []
        self.modo_manutencao_ativo = False

        # PIDs que já existiam antes da sessão (não serão encerrados pela whitelist)
        self._pids_pre_sessao = set()

        # Prompt de manutenção pendente (aguardando resposta do servidor)
        self._prompt_manutencao = None

        # Streaming ao vivo
        self._streaming = False

        # Pausa de sessão
        self._sessao_pausada = False
        self._aviso_5min_dado = False

        # Tema escolhido pelo cliente, guardado no agente.cfg da estação
        self.tema = carregar_cfg().get("TEMA", "escuro")
        if self.tema not in PALETAS:
            self.tema = "escuro"
        self.cor_piso = None  # cor do piso da estacao (servidor manda ao conectar)
        self.paleta = PALETAS[self.tema]
        self._definir_cores()

        self.root.title(f"MatheCafe v{VERSAO} - {estacao}")
        self.root.configure(bg=self.paleta["fundo"])
        self.root.resizable(True, True)
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)

        # Impede fechar a janela durante a sessão
        self.root.protocol("WM_DELETE_WINDOW", self._tentar_fechar)

        global FONTE
        if "Inter" in tkfont.families(root):
            FONTE = "Inter"  # 9.13: a do prompt; sem ela fica a Segoe UI
        self._build_ui()
        self.barra = BarraSessao(self)
        self.notificacoes = Notificacoes(self)
        self._vigia = None  # PowerShell que prende o Explorador em Downloads (9.5)
        self._pids_proprios = set()  # processos do agente que o vigia de processos nao encerra
        self._start_ws_thread()

        # Atalhos
        self._teclado = BloqueioTeclado(self._tecla_bloqueada)
        self.root.bind("<Escape>", self._tentar_esc)
        self.root.bind("<Unmap>", self._ao_minimizar)
        self.root.bind("<Configure>", self._ao_redimensionar)
        self.root.bind("<Control-Shift-M>", self._abrir_prompt_admin)
        self.root.bind("<Control-Shift-KeyPress-M>", self._abrir_prompt_admin)

        self.root.after(100, self._processar_fila)
        self.root.after(1000, self._atualizar_countdown)
        self.root.after(500, self._verificar_processos)

    # ── Controle de janela ────────────────────────────────────────────────────
    def _tentar_fechar(self):
        """Fechar (X, Alt+F4) só funciona no modo manutenção."""
        if self.modo_manutencao_ativo:
            barra_do_windows(True)
            self.root.destroy()

    def _tentar_esc(self, event=None):
        """ESC só sai da tela cheia no modo manutenção."""
        if self.modo_manutencao_ativo:
            self.root.attributes("-fullscreen", False)

    def _ao_minimizar(self, event=None):
        """Minimizar (botão, clique na barra de tarefas) só no modo manutenção."""
        if self.modo_manutencao_ativo or self.root.state() != "iconic":
            return
        self.root.after(50, self._restaurar_janela)

    def _restaurar_janela(self):
        self.root.deiconify()
        if self.sessao_ativa:
            self.root.attributes("-fullscreen", True)
        self.root.lift()

    def _definir_cores(self):
        p = self.paleta
        self.c_bg, self.c_bg2, self.c_bg3, self.c_bg4 = p["fundo"], p["superficie"], p["superficie2"], p["superficie3"]
        self.c_text, self.c_text2, self.c_accent = p["texto"], p["texto2"], p["destaque"]

    def _paleta_de(self, tema):
        """A paleta do tema com o destaque na cor do piso da estacao (Infantil, Adulto...)."""
        paleta = dict(PALETAS[tema])
        if self.cor_piso:
            paleta["destaque"], paleta["destaque_forte"] = self.cor_piso, escurecer(self.cor_piso)
        return paleta

    def _aplicar_cor_piso(self, piso):
        """O servidor manda o piso da estacao; a cor dele vira o destaque da tela."""
        cor = (piso or {}).get("cor")
        if not cor_valida(cor) or cor.lower() == (self.cor_piso or "").lower():
            return
        self.cor_piso = cor.lower()
        antiga, nova = self.paleta, self._paleta_de(self.tema)
        trocar_cores(self.root, {antiga[k].lower(): nova[k] for k in ("destaque", "destaque_forte")})
        self.paleta = nova
        self._log(f"Piso da estacao: {(piso or {}).get('nome')} ({cor})")
        self.barra.desenhar()
        self._tela_apps.redesenhar()
        self._programacao.redesenhar()
        self._tela_login.redesenhar()
        self._menu.redesenhar()
        self._painel_direito.redesenhar()
        self._preferencias.redesenhar()

    def alternar_tema(self):
        """Botão do cliente (tela de login e barra da sessão): claro <-> escuro."""
        novo = "claro" if self.tema == "escuro" else "escuro"
        antiga, nova = self.paleta, self._paleta_de(novo)
        trocar_cores(self.root, {antiga[k].lower(): nova[k] for k in antiga})
        self.tema, self.paleta = novo, nova
        self._definir_cores()
        self.btn_tema.config(text=ROTULO_TEMA[novo])
        self.barra.btn_tema.config(text=ICONE_TEMA[novo])
        self.barra.desenhar()
        self._tela_apps.redesenhar()
        self._programacao.redesenhar()
        self._tela_login.redesenhar()
        self._menu.redesenhar()
        self._painel_direito.redesenhar()
        self._preferencias.redesenhar()
        salvar_tema(novo)

    def _ao_redimensionar(self, event):
        """Na sessão a janela é tela cheia (sem barra de título para arrastar):
        se sair disso, volta sozinha."""
        if event.widget is not self.root or self.modo_manutencao_ativo or not self.sessao_ativa:
            return
        if not self.root.attributes("-fullscreen"):
            self.root.after(50, self._restaurar_janela)

    def _liberar_janela(self, ativo):
        """Botões de minimizar/maximizar e borda: só no modo manutenção."""
        try:
            self.root.update_idletasks()
            botoes_janela(int(self.root.wm_frame(), 16), ativo)
        except Exception:
            pass

    def _tecla_bloqueada(self, vk, alt, ctrl, shift):
        """Chamado pelo hook de teclado (outra thread): True engole a tecla."""
        if self.modo_manutencao_ativo:
            return False
        if vk == VK_ESCAPE and ctrl and shift:
            return True  # Gerenciador de Tarefas
        if vk in (VK_LWIN, VK_RWIN):
            return True  # Iniciar, Win+R, Win+E, Win+D...
        if vk == VK_ESCAPE and ctrl:
            return True  # Ctrl+Esc abre o Iniciar
        if self.sessao_ativa:
            return False  # Alt+Tab e Alt+F4 entre os apps liberados
        # Tela de login: nada tira o cliente do agente
        return alt and vk in (VK_TAB, VK_ESCAPE, VK_F4)

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        p = self.paleta
        bg, bg2, bg3 = self.c_bg, self.c_bg2, self.c_bg3
        text, text2, accent = self.c_text, self.c_text2, self.c_accent

        title_font = tkfont.Font(family=FONTE, size=16, weight="bold")
        normal_font = tkfont.Font(family=FONTE, size=11)
        big_font = tkfont.Font(family="Consolas", size=36, weight="bold")
        small_font = tkfont.Font(family="Consolas", size=9)
        self.f_normal = normal_font
        self.f_small = small_font
        self.f_app = tkfont.Font(family=FONTE, size=10, weight="bold")
        self.f_icon = tkfont.Font(family=FONTE, size=22, weight="bold")

        # ── Frame de login ──
        # duas metades: formulário à esquerda, cartazes da programação à direita
        self.frame_login = tk.Frame(self.root, bg=bg)
        esquerda = tk.Frame(self.frame_login, bg=bg)
        esquerda.place(relx=0, rely=0, relwidth=0.5, relheight=1)
        direita = tk.Frame(self.frame_login, bg=bg)
        direita.place(relx=0.5, rely=0, relwidth=0.5, relheight=1)
        self._tela_login = TelaLogin(self, direita)

        _form = tk.Frame(esquerda, bg=bg)
        _form.pack(expand=True)
        # espacador fixa a largura; pack_propagate(False) sem height colapsava o form em 1px
        tk.Frame(_form, bg=bg, width=380, height=0).pack()

        # sem barra em cima: o nome do PC bem grande, com o computador verde
        # (online) ou vermelho (offline)
        self._icone_pc = tk.Canvas(_form, width=120, height=100, bg=bg, highlightthickness=0)
        self._icone_pc.pack()
        self._desenhar_icone_pc(COR_CONECTANDO)
        self.lbl_estacao = tk.Label(_form, text=self.estacao, font=tkfont.Font(family=FONTE, size=40, weight="bold"),
                                    fg=text, bg=bg, wraplength=520)
        self.lbl_estacao.pack(pady=(2, 0))
        self.lbl_status = tk.Label(_form, text="conectando...", font=tkfont.Font(family=FONTE, size=11, weight="bold"),
                                   fg=COR_CONECTANDO, bg=bg)
        self.lbl_status.pack(pady=(0, 30))

        tk.Label(_form, text="Entre na sua conta", font=tkfont.Font(family=FONTE, size=18, weight="bold"),
                 fg=text, bg=bg).pack()
        tk.Label(_form, text="Use o login e a senha do seu cadastro na biblioteca",
                 font=tkfont.Font(family=FONTE, size=10), fg=text2, bg=bg).pack(pady=(4, 22))

        f_rotulo = tkfont.Font(family=FONTE, size=10, weight="bold")
        campo = dict(font=normal_font, bg=bg3, fg=text, insertbackground=text, relief="flat",
                     highlightthickness=1, highlightbackground=p["superficie3"], highlightcolor=accent)
        tk.Label(_form, text="Login", font=f_rotulo, fg=text, bg=bg).pack(anchor="w")
        self.entry_login = tk.Entry(_form, **campo)
        self.entry_login.pack(fill="x", pady=(6, 16), ipady=8)

        tk.Label(_form, text="Senha", font=f_rotulo, fg=text, bg=bg).pack(anchor="w")
        caixa_senha = tk.Frame(_form, bg=bg3, highlightthickness=1, highlightbackground=p["superficie3"],
                               highlightcolor=accent)
        caixa_senha.pack(fill="x", pady=(6, 22))
        self.entry_senha = tk.Entry(caixa_senha, show="•", **{**campo, "highlightthickness": 0})
        self.entry_senha.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry_senha.bind("<Return>", lambda e: self._fazer_login())
        # o olho mostra/esconde a senha
        self.lbl_olho = tk.Label(caixa_senha, text="👁", font=("Segoe UI Symbol", 12), fg=text2, bg=bg3,
                                 cursor="hand2", padx=10)
        self.lbl_olho.pack(side="right", fill="y")
        self.lbl_olho.bind("<Button-1>", self._alternar_senha)

        self.btn_login = tk.Button(_form, text="Entrar", font=tkfont.Font(family=FONTE, size=11, weight="bold"),
                                   bg=accent, fg="white", relief="flat", activebackground=p["destaque_forte"],
                                   activeforeground="white", cursor="hand2",
                                   command=self._fazer_login, state="disabled")
        self.btn_login.pack(fill="x", ipady=9)

        self.lbl_login_erro = tk.Label(_form, text="", font=small_font, fg="#ef4444", bg=bg)
        self.lbl_login_erro.pack(pady=8)

        tk.Frame(_form, bg=p["superficie3"], height=1).pack(fill="x", pady=(6, 14))
        tk.Label(_form, text="Não tem cadastro? Fale com um funcionário da biblioteca.",
                 font=tkfont.Font(family=FONTE, size=10), fg=text2, bg=bg).pack()

        # canto de baixo: tema e versão (ficavam na barra de cima)
        rodape = tk.Frame(esquerda, bg=bg)
        rodape.place(x=20, rely=1, y=-16, anchor="sw")
        self.btn_tema = tk.Button(rodape, text=ROTULO_TEMA[self.tema], font=small_font, bg=bg3, fg=text2,
                                  activebackground=p["superficie3"], relief="flat", padx=10, cursor="hand2",
                                  command=self.alternar_tema)
        self.btn_tema.pack(side="left")
        tk.Label(rodape, text=f"MatheCafé v{VERSAO}", font=tkfont.Font(family=FONTE, size=9),
                 fg=p["fraco"], bg=bg).pack(side="left", padx=10)

        # ── Frame de sessão (launcher) ──
        self.frame_sessao = tk.Frame(self.root, bg=bg)
        # espaço da barra do MatheCafé, que fica por cima, embaixo da tela
        tk.Frame(self.frame_sessao, bg=bg, height=BarraSessao.ALTURA).pack(side="bottom", fill="x")

        # Área do Cliente (9.11): menu à esquerda, banner e apps no centro,
        # sessão e avisos à direita; embaixo, o dock (BarraSessao)
        self._pagina = "inicio"
        self.frame_corpo = tk.Frame(self.frame_sessao, bg=bg)
        self.frame_corpo.pack(expand=True, fill="both")
        self._menu = MenuLateral(self, tk.Frame(self.frame_corpo))
        self._menu.frame.pack(side="left", fill="y")
        self._painel_direito = PainelDireito(self, tk.Frame(self.frame_corpo))
        self._painel_direito.frame.pack(side="right", fill="y")
        self.frame_centro = tk.Frame(self.frame_corpo, bg=bg)
        self.frame_centro.pack(side="left", expand=True, fill="both")
        self.frame_launcher = tk.Frame(self.frame_centro, bg=bg)
        self.frame_launcher.pack(side="bottom", expand=True, fill="both")
        # pesquisa, pílulas das categorias e a grade de cards
        self._tela_apps = TelaApps(self, self.frame_launcher)
        # banner da programação no topo (só em Início): aparece quando há cartaz
        self.frame_programacao = tk.Frame(self.frame_centro, bg=bg)
        self._programacao = Programacao(self, self.frame_programacao)
        # Configurações (menu): tema e tamanho do texto, no lugar da grade
        self.frame_config = tk.Frame(self.frame_centro, bg=bg)
        self._preferencias = PaginaPreferencias(self, self.frame_config)

        self.frame_login.pack(fill="both", expand=True)

        # ── Frame de encerramento ──
        self.frame_encerramento = tk.Frame(self.root, bg=bg)
        tk.Label(self.frame_encerramento, text="SESSAO ENCERRADA",
                 font=tkfont.Font(family=FONTE, size=24, weight="bold"),
                 fg="#ef4444", bg=bg).pack(expand=False, pady=(80, 12))
        tk.Label(self.frame_encerramento, text="Aguarde a liberacao do sistema...",
                 font=normal_font, fg=text2, bg=bg).pack()
        self._lbl_enc_relogio = tk.Label(self.frame_encerramento, text="6",
                                          font=big_font, fg="#f59e0b", bg=bg)
        self._lbl_enc_relogio.pack(pady=20)

        # ── Barra de manutenção (oculta inicialmente) ──
        self.frame_manutencao = tk.Frame(self.root, bg="#f59e0b")
        tk.Label(self.frame_manutencao, text="Modo Manutencao ativo",
                 bg="#f59e0b", fg="black", font=normal_font).pack(side="left", padx=14, pady=8)
        tk.Button(self.frame_manutencao, text="Encerrar manutencao",
                  bg="#92400e", fg="white", relief="flat", font=small_font,
                  command=self._sair_modo_manutencao).pack(side="right", padx=14, pady=8)
        tk.Button(self.frame_manutencao, text="Configurar conexao",
                  bg="#92400e", fg="white", relief="flat", font=small_font,
                  command=self._abrir_config_conexao).pack(side="right", pady=8)
        # Atualizacao do agente: so por aqui (6.13)
        self.btn_atualizar = tk.Button(self.frame_manutencao, text="Verificar atualizacao",
                                       bg="#92400e", fg="white", relief="flat", font=small_font,
                                       command=self._clicar_atualizar)
        self.btn_atualizar.pack(side="right", padx=(0, 6), pady=8)

    def _log(self, msg, _remoto=True):
        """O log de comunicação vai ao servidor (painel > estação > Log); não aparece no PC.
        Sem conexão, guarda as linhas e manda ao reconectar. _remoto=False: só o
        eco do que foi enviado, que não interessa."""
        if not _remoto:
            return
        linha = {"msg": msg, "ts": datetime.now().strftime("%H:%M:%S")}
        if not (self.loop and self.ws):
            self._logs_offline.append(linha)
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({"evento": "log_agente", "dados": linha})), self.loop)
        except Exception:
            self._logs_offline.append(linha)

    def _enviar_logs_offline(self):
        """Ao reconectar: as linhas de quando estava sem servidor, na ordem."""
        while self._logs_offline and self.loop and self.ws:
            linha = self._logs_offline.popleft()
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({"evento": "log_agente", "dados": linha})), self.loop)

    def _desenhar_icone_pc(self, cor):
        """O computador acima do nome do PC, na cor da conexão."""
        c = self._icone_pc
        c.delete("all")
        BarraSessao._retangulo(c, 10, 4, 110, 74, 10, fill=cor, outline="")
        c.create_rectangle(19, 13, 101, 65, fill=escurecer(cor, 0.55), outline="")
        c.create_line(28, 22, 46, 22, fill=cor, width=3, capstyle="round")  # brilho da tela
        c.create_polygon(52, 74, 68, 74, 72, 88, 48, 88, fill=cor, outline="")
        BarraSessao._retangulo(c, 34, 86, 86, 96, 4, fill=cor, outline="")

    # ── WebSocket (thread separada) ──────────────────────────────────────────
    def _start_ws_thread(self):
        t = threading.Thread(target=self._thread_main, daemon=True)
        t.start()

    def _thread_main(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self):
        url_anterior = None
        while True:
            # refeita a cada tentativa: o painel pode ter renomeado a estacao
            url = url_da_estacao(self.servidor, self.estacao, self.identificador, piso_da_instalacao())
            # Servidor na rede interna: conexão direta. O websockets usa o proxy do
            # Windows por padrão, e redes com proxy desviam até IPs internos.
            proxy = None if servidor_na_rede_local(url) else True
            if url != url_anterior:
                url_anterior = url
                self.incoming.put({"evento": "_info", "dados": {
                    "msg": f"Conectando a {url}" + (" (direto, sem proxy)" if proxy is None else "")}})
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, proxy=proxy) as ws:
                    # Primeiro o que terminou sem conexao, depois o estado: o
                    # servidor retoma a sessao em andamento (ele ou a rede caiu e o
                    # cliente seguiu usando) ou encerra a que ficou aberta.
                    pendentes, self._pendentes = self._pendentes, []
                    for msg in mensagens_pendentes(pendentes, time.monotonic()):
                        await ws.send(json.dumps(msg))
                    # Só fica "online" quando o servidor responder: uma estação
                    # não cadastrada é fechada antes da resposta
                    await ws.send(json.dumps({
                        "evento": "estado", "versao": VERSAO,
                        "sessao_id": self.sessao_id if self.sessao_ativa else None}))
                    async for raw in ws:
                        if not self.conectado:
                            self.ws = ws
                            self.conectado = True
                            self.incoming.put({"evento": "_conectado"})
                        self.incoming.put(json.loads(raw))
            except websockets.exceptions.ConnectionClosed as e:
                if e.rcvd and e.rcvd.code == 4004:
                    self.incoming.put({"evento": "_erro", "dados": {"nao_cadastrada": True, "msg": (
                        f"O servidor recusou a estacao '{self.estacao}' (recusada em Novas estacoes). "
                        "Para cadastrar de novo, reinstale o agente.")}})
                else:
                    self.incoming.put({"evento": "_erro", "dados": {"msg": str(e)}})
            except Exception as e:
                self.incoming.put({"evento": "_erro", "dados": {"msg": str(e)}})

            self.ws = None
            self.conectado = False
            self.incoming.put({"evento": "_desconectado"})
            await asyncio.sleep(3)

    def _enviar(self, msg: dict):
        if not (self.loop and self.ws) and msg.get("evento") == "sessao_encerrada":
            # Sem servidor: guarda o fim da sessao e manda ao reconectar
            self._pendentes.append((msg, time.monotonic()))
            self._log("Sem conexao: o fim da sessao vai ao servidor quando reconectar", _remoto=False)
            return
        if self.loop and self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(msg)), self.loop)
            self._log(f"-> enviado: {msg.get('evento')}", _remoto=False)
        else:
            self._log("AVISO: nao conectado, mensagem nao enviada", _remoto=False)

    # ── Processamento de eventos ─────────────────────────────────────────────
    def _processar_fila(self):
        try:
            while True:
                msg = self.incoming.get_nowait()
                self._handle_evento(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def _handle_evento(self, msg):
        evento = msg.get("evento")
        dados = msg.get("dados", {})

        if evento == "_conectado":
            self.lbl_status.config(text="online", fg=COR_ONLINE)
            self._desenhar_icone_pc(COR_ONLINE)
            self._painel_direito.definir_status(True)
            self.btn_login.config(state="normal")
            self._enviar_logs_offline()
            self._log("Conectado ao servidor")
            self._programacao.recarregar()  # cartazes do login (e do banner da sessão)
            self._painel_direito.recarregar_avisos()
            if self.sessao_ativa and getattr(self, "_avisou_queda", False):
                self.notificacoes.notificar("Sistema", "Conexão restabelecida", "Tudo certo de novo.", "conexao")
            self._avisou_queda = False
            if self.modo_manutencao_ativo:
                # Caiu e voltou durante a manutencao: o servidor marca livre
                # a cada conexao nova, entao lembra que ainda esta nela
                self._enviar({"evento": "status_estacao", "status": "manutencao"})

        elif evento == "_desconectado":
            self.lbl_status.config(text="offline", fg=COR_OFFLINE)
            self._desenhar_icone_pc(COR_OFFLINE)
            self._painel_direito.definir_status(False)
            self.btn_login.config(state="disabled")
            self._log("Desconectado - tentando reconectar em 3s...")
            if self.sessao_ativa:
                # O servidor (ou a rede) caiu: o cliente segue usando ate o tempo
                # acabar; ao reconectar, o servidor retoma a mesma sessao
                self._log("Conexao perdida durante a sessao - o cliente continua; reconectando")
                if not getattr(self, "_avisou_queda", False):
                    self._avisou_queda = True
                    self.notificacoes.notificar("Sistema", "Sem conexão com o servidor",
                                                "Você continua usando normalmente; o tempo segue contando.", "conexao")

        elif evento == "_info":
            self._log(dados.get("msg", ""))

        elif evento == "_erro":
            self._log(f"Erro de conexao: {dados.get('msg')}")
            if dados.get("nao_cadastrada"):
                self.lbl_login_erro.config(text=dados["msg"], wraplength=340)

        elif evento == "login_resultado":
            self._log(f"<- login_resultado: {dados}")
            if dados.get("ok"):
                if dados.get("manutencao"):
                    nome = dados.get("admin_nome", "Admin")
                    self._log(f"Login de admin/operador ({nome}): entrando em manutencao")
                    self.root.after(0, self._modo_manutencao)
                else:
                    self._iniciar_sessao(dados)
            else:
                motivo = dados.get("motivo", "Erro desconhecido")
                pendente = motivo.startswith("Este computador aguarda")
                self.lbl_login_erro.config(text=motivo, fg="#f59e0b" if pendente else "#ef4444", wraplength=340)

        elif evento == "pong":
            pass

        elif evento == "encerrar_sessao":
            if self.sessao_ativa:
                saldo = dados.get("saldo_restante", 0)
                self._log(f"Sessao encerrada pelo operador. Saldo: {self._fmt(saldo)}")
                self._voltar_login()
                self._reiniciar_se_necessario()

        elif evento == "validar_manutencao_resultado":
            self._log(f"<- validar_manutencao_resultado: {dados}")
            credenciais, self._credenciais_manutencao = self._credenciais_manutencao, None
            if credenciais:
                if dados.get("ok"):
                    lembrar_operador(*credenciais)
                else:
                    esquecer_operador(credenciais[0])
            if self._prompt_manutencao and self._prompt_manutencao.winfo_exists():
                if dados.get("ok"):
                    self._prompt_manutencao.destroy()
                    self._prompt_manutencao = None
                    self._modo_manutencao()
                else:
                    motivo = dados.get("motivo", "Credenciais invalidas")
                    # Mostra erro dentro do prompt
                    for w in self._prompt_manutencao.winfo_children():
                        if isinstance(w, tk.Label) and getattr(w, "_is_erro", False):
                            w.config(text=motivo)
                            return
                    lbl = tk.Label(self._prompt_manutencao, text=motivo,
                                   fg="#ef4444", bg="#1A1B26", font=("Arial", 9))
                    lbl._is_erro = True
                    lbl.pack(pady=(0, 4))

        elif evento == "reiniciar_pc":
            self._log("<- reiniciar_pc do operador")
            self.reiniciar_ao_encerrar = True
            if self.sessao_ativa:
                self._log("Encerrando sessao para reiniciar...")
                self._voltar_login()
            self._countdown_reinicio(10)

        elif evento == "desligar_pc":
            # O servidor ja encerrou a sessao e devolveu o tempo ao cliente
            self._log("<- desligar_pc do operador")
            if self.sessao_ativa:
                self._log("Encerrando sessao para desligar...")
                self._voltar_login()
            self._countdown_reinicio(10, desligar=True)

        elif evento == "mensagem_tela":
            texto = dados.get("texto", "")
            self._log(f"<- mensagem_tela: {texto}")
            if self.sessao_ativa:
                # na sessão vira notificação (canto de baixo, sininho do dock)
                if dados.get("origem") == "horario":
                    self.notificacoes.notificar("Biblioteca", "A biblioteca vai fechar", texto, "horario")
                else:
                    self.notificacoes.notificar("Atendimento", "Mensagem do operador", texto, "operador")
            else:
                self.root.after(0, lambda t=texto: self._exibir_mensagem_operador(t))

        elif evento == "ativar_manutencao":
            self._log("<- ativar_manutencao do operador")
            if not self.modo_manutencao_ativo:
                self.root.after(0, self._modo_manutencao)

        elif evento == "desativar_manutencao":
            self._log("<- desativar_manutencao do operador")
            if self.modo_manutencao_ativo:
                self.root.after(0, self._sair_modo_manutencao)

        elif evento == "piso_estacao":
            self._aplicar_cor_piso(dados)

        elif evento == "atualizar_agente":
            # 1.16: o painel mandou atualizar (o servidor so manda sem cliente usando)
            self._log(f"<- atualizar_agente: {dados}")
            self._atualizar_pelo_painel()

        elif evento == "estacao_info":
            # 1.14: o nome cadastrado (o painel pode ter trocado) e se o PC ja
            # foi aprovado em "Novas estacoes"
            self._log(f"<- estacao_info: {dados}")
            self._aplicar_info_estacao(dados)

        elif evento == "iniciar_sessao_direta":
            self._log(f"<- iniciar_sessao_direta: {dados}")
            if not self.sessao_ativa:
                self.root.after(0, lambda d=dados: self._iniciar_sessao(d))

        elif evento == "capturar_tela":
            self._log("<- capturar_tela")
            self.root.after(0, self._capturar_e_enviar_tela)

        elif evento == "pausar_sessao":
            self._log("<- pausar_sessao")
            self.root.after(0, self._pausar_sessao)

        elif evento == "retomar_sessao":
            self._log("<- retomar_sessao")
            novo_total = dados.get("tempo_total_segundos")
            self.root.after(0, lambda t=novo_total: self._retomar_sessao(t))

        elif evento == "renovar_sessao":
            self._log("<- renovar_sessao")
            novo_total = dados.get("tempo_total_segundos")
            self.root.after(0, lambda t=novo_total: self._renovar_sessao(t))

        elif evento == "iniciar_streaming":
            self._log("<- iniciar_streaming")
            if not self._streaming:
                self._streaming = True
                threading.Thread(target=self._loop_streaming, daemon=True).start()

        elif evento == "programacao_atualizada":
            self._log("<- programacao_atualizada")
            self._programacao.recarregar()  # login e banner da sessão

        elif evento == "avisos_atualizados":
            self._log("<- avisos_atualizados")
            self._painel_direito.recarregar_avisos()

        elif evento == "parar_streaming":
            self._log("<- parar_streaming")
            self._streaming = False

        else:
            self._log(f"<- evento: {evento} | {dados}")

    # ── Captura de tela ──────────────────────────────────────────────────────
    def _aplicar_info_estacao(self, dados):
        nome = (dados.get("nome") or "").strip()
        if nome and nome != self.estacao:
            self._log(f"Estacao renomeada no painel: {self.estacao} -> {nome}")
            self.estacao = nome
            gravar_cfg(ESTACAO=nome)
            self.lbl_estacao.config(text=nome)
        aprovada = bool(dados.get("aprovada", True))
        if not aprovada:
            self.lbl_login_erro.config(text=AGUARDANDO_APROVACAO, fg="#f59e0b", wraplength=340)
        elif not self.aprovada:
            self.lbl_login_erro.config(text="", fg="#ef4444")
            self._log("Estacao aprovada no painel")
        self.aprovada = aprovada

    def _tirar_screenshot(self):
        """Captura a tela silenciosamente via PIL (sem abrir janela ou processo)."""
        import io, base64
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow nao instalado -- instale com: pip install Pillow")
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.thumbnail((1280, 720))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65)
        return base64.b64encode(buf.getvalue()).decode()

    def _capturar_e_enviar_tela(self):
        try:
            b64 = self._tirar_screenshot()
            self._enviar({"evento": "captura_tela_resultado", "dados": {"imagem": b64}})
            self._log(f"-> captura enviada ({len(b64)} chars)")
        except Exception as ex:
            self._log(f"Erro na captura de tela: {ex}")

    def alternar_notificacoes(self):
        self.notificacoes.alternar()

    def abrir_meus_arquivos(self):
        """Abre o Explorador de verdade na pasta Downloads; o vigia nao deixa sair dela."""
        if not self.sessao_ativa:
            return
        pasta = pasta_downloads()
        try:
            os.makedirs(pasta, exist_ok=True)
            self._ligar_vigia()
            subprocess.Popen(["explorer.exe", pasta])
        except Exception as e:
            self._log(f"Meus arquivos: erro ao abrir a pasta ({e})")

    def _ligar_vigia(self):
        if self._vigia and self._vigia.poll() is None:
            return
        try:
            self._vigia = iniciar_vigia(pasta_downloads())
            self._pids_proprios = {self._vigia.pid}
        except Exception as e:
            self._vigia = None
            self._log(f"Meus arquivos: vigia do Explorador nao iniciou ({e})")

    def _desligar_vigia(self):
        if self._vigia:
            try:
                self._vigia.kill()
            except Exception:
                pass
        self._vigia = None
        self._pids_proprios = set()

    def _limpar_downloads(self):
        """Esvazia a pasta Downloads: o próximo cliente não vê o que este baixou."""
        try:
            apagados = limpar_pasta(pasta_downloads())
            if apagados:
                self._log(f"Downloads limpos: {apagados} item(ns)")
        except Exception as e:
            self._log(f"Erro ao limpar Downloads: {e}")

    def notificacoes_nao_lidas(self):
        return self.notificacoes.nao_lidas()

    def _avisar_saldo_baixo(self, restante_segundos: int):
        mins = max(1, restante_segundos // 60)
        self.notificacoes.notificar("Sessão", "Seu tempo está acabando",
                                    f"Restam {mins} minutos. Salve o que estiver fazendo.", "tempo")

    def _pausar_sessao(self):
        self._sessao_pausada = True
        self._log("Sessao pausada pelo operador")
        # Mostra overlay de pausa na janela (por cima do launcher)
        try:
            self._overlay_pausa = tk.Toplevel(self.root)
            self._overlay_pausa.overrideredirect(True)
            self._overlay_pausa.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            self._overlay_pausa.configure(bg=self.c_bg)
            self._overlay_pausa.attributes("-topmost", True)
            tk.Label(self._overlay_pausa, text="SESSAO PAUSADA",
                     font=(FONTE, 22, "bold"), bg=self.c_bg, fg="#f59e0b").pack(expand=True)
            tk.Label(self._overlay_pausa, text="Aguarde o operador retomar",
                     font=(FONTE, 12), bg=self.c_bg, fg=self.c_text2).pack()
        except Exception as ex:
            self._log(f"Erro ao exibir overlay: {ex}")

    def _retomar_sessao(self, novo_total: int):
        self._sessao_pausada = False
        if novo_total:
            self.tempo_total = novo_total
        self._log("Sessao retomada")
        try:
            if hasattr(self, "_overlay_pausa") and self._overlay_pausa:
                self._overlay_pausa.destroy()
                self._overlay_pausa = None
        except Exception:
            pass

    def _renovar_sessao(self, novo_total: int):
        if novo_total:
            self.tempo_total = novo_total
            self._log(f"Sessao renovada: {self._fmt(novo_total)} no total")

    def _loop_streaming(self):
        # Roda em thread separada: nada de self._log/self._enviar aqui, que
        # escrevem no log da janela (o Tkinter so aceita a thread principal)
        self.incoming.put({"evento": "_info", "dados": {"msg": "Tela ao vivo: iniciada"}})
        while self._streaming:
            try:
                b64 = self._tirar_screenshot()
                if self.loop and self.ws:
                    envio = asyncio.run_coroutine_threadsafe(
                        self.ws.send(json.dumps({"evento": "tela_frame", "dados": {"imagem": b64}})), self.loop)
                    envio.result(timeout=10)  # rede lenta: espera em vez de acumular quadros
            except Exception as ex:
                self.incoming.put({"evento": "_info", "dados": {"msg": f"Tela ao vivo: erro ({ex})"}})
                time.sleep(3)
            time.sleep(1.2)
        self.incoming.put({"evento": "_info", "dados": {"msg": "Tela ao vivo: encerrada"}})

    # ── Fluxo de sessão ───────────────────────────────────────────────────────
    def _encerrar_sessao_cliente(self):
        """Cliente encerra a propria sessao pelo botao."""
        if not self.sessao_ativa:
            return
        import tkinter.messagebox as _mb
        if _mb.askyesno("Encerrar sessao", "Deseja encerrar sua sessao agora?", parent=self.root):
            self._log("Cliente encerrou a sessao pelo botao")
            self._enviar({"evento": "sessao_encerrada", "sessao_id": self.sessao_id, "motivo": "cliente"})
            self._voltar_login()
            self._reiniciar_se_necessario()

    def _fazer_login(self):
        login = self.entry_login.get().strip()
        senha = self.entry_senha.get()
        self.lbl_login_erro.config(text="")
        if not login or not senha:
            self.lbl_login_erro.config(text="Preencha login e senha")
            return
        self._enviar({"evento": "login_cliente", "login": login, "senha": senha})

    def _alternar_senha(self, event=None):
        """O olho do campo de senha: mostra ou esconde o que foi digitado."""
        mostrando = self.entry_senha.cget("show") == ""
        self.entry_senha.config(show="•" if mostrando else "")
        self.lbl_olho.config(fg=self.paleta["texto2"] if mostrando else self.paleta["destaque"])

    def _iniciar_sessao(self, dados):
        if dados.get("piso"):
            self._aplicar_cor_piso(dados["piso"])
        self._limpar_downloads()  # o PC pode ter reiniciado no meio da sessão anterior
        self._ligar_vigia()  # o Explorador so pode mostrar a pasta Downloads
        # Captura os PIDs que ja existem ANTES da sessao comecar
        self._pids_pre_sessao = {p.pid for p in psutil.process_iter(["pid"])}

        self.sessao_ativa = True
        self.sessao_id = dados["sessao_id"]
        self.cliente_nome = dados["cliente_nome"]
        self.tempo_total = dados["tempo_segundos"]
        self.inicio_sessao = time.time()

        whitelist_apps = dados.get("whitelist", [])
        if whitelist_apps and isinstance(whitelist_apps[0], str):
            whitelist_apps = [{"nome": p, "processo": p, "caminho": None} for p in whitelist_apps]

        self.whitelist_apps = whitelist_apps
        self.whitelist_procs = {a["processo"].strip().lower() for a in whitelist_apps if a.get("processo")}
        self.reiniciar_ao_encerrar = dados.get("reiniciar_ao_encerrar", False)

        self._painel_direito.definir_cliente(self.cliente_nome, dados.get("cliente_login"))
        self._mostrar_pagina("inicio")
        self._painel_direito.atualizar_tempo(self.tempo_total, self.tempo_total)
        self.entry_login.delete(0, "end")
        self.entry_senha.delete(0, "end")
        self.entry_senha.config(show="•")
        self.lbl_olho.config(fg=self.paleta["texto2"])
        self.lbl_login_erro.config(text="")

        self._montar_launcher()

        self.frame_login.pack_forget()
        self.frame_sessao.pack(fill="both", expand=True)

        # Tela cheia sem "sempre por cima": os apps abrem na frente, e não há
        # barra de título para arrastar ou diminuir. A barra do MatheCafé
        # (Início, apps, tempo) fica no lugar da do Windows.
        self.root.attributes("-topmost", False)
        self.root.attributes("-fullscreen", True)
        self.barra.mostrar()
        self._programacao.recarregar()
        self._painel_direito.recarregar_avisos()
        self.root.lift()
        self.root.focus_force()

        if self.whitelist_procs:
            self._log(f"Sessao iniciada - {self._fmt(self.tempo_total)} | "
                      f"whitelist: {len(self.whitelist_procs)} app(s)")
        else:
            self._log(f"Sessao iniciada - {self._fmt(self.tempo_total)} | sem restricao")

    def _montar_launcher(self):
        """A tela de apps da sessão (TelaApps): só os apps com caminho abrem."""
        self._tela_apps.mostrar([a for a in self.whitelist_apps if a.get("caminho")])

    def _mostrar_pagina(self, pagina):
        """Menu da esquerda: Início (banner + apps) ou Meus Apps (só a grade)."""
        self._pagina = pagina
        self._menu.pintar()
        if pagina == "config":
            self.frame_programacao.pack_forget()
            self.frame_launcher.pack_forget()
            self._preferencias.redesenhar()
            self.frame_config.pack(fill="both", expand=True)
            return
        self.frame_config.pack_forget()
        if not self.frame_launcher.winfo_manager():
            self.frame_launcher.pack(side="bottom", expand=True, fill="both")
        self._programacao.ajustar_pagina()
        self.root.after(40, self._tela_apps.animar_entrada)

    def _abrir_app(self, app):
        caminho = app.get("caminho")
        if not caminho:
            return
        try:
            subprocess.Popen([caminho])
            self._log(f"Abrindo: {app['nome']}")
            # Envia launcher para tras sem minimizar
            self.root.after(300, self.root.lower)
        except Exception as e:
            self._log(f"Erro ao abrir {app['nome']}: {e}")

    def _atualizar_countdown(self):
        if self.sessao_ativa and not self._sessao_pausada:
            decorrido = time.time() - self.inicio_sessao
            restante = max(0, self.tempo_total - decorrido)
            self._painel_direito.atualizar_tempo(restante, self.tempo_total)
            self.barra.definir_tempo(self._fmt(restante), restante < 300)

            if restante < 300:
                # Aviso de 5 minutos — disparado uma unica vez pelo countdown
                if not self._aviso_5min_dado and restante > 0:
                    self._aviso_5min_dado = True
                    self.root.after(0, lambda r=int(restante): self._avisar_saldo_baixo(r))

            if restante <= 0:
                self._encerrar_automatico()

        self.root.after(1000, self._atualizar_countdown)

    def _encerrar_manual(self):
        if not self.sessao_ativa:
            return
        consumido = int(time.time() - self.inicio_sessao)
        self._enviar({
            "evento": "sessao_encerrada",
            "sessao_id": self.sessao_id,
            "motivo": "cliente",
            "tempo_consumido_segundos": consumido
        })
        restante = max(0, self.tempo_total - consumido)
        self._log(f"Sessao encerrada pelo cliente. Saldo: {self._fmt(restante)}")
        self._voltar_login()
        self._reiniciar_se_necessario()

    def _encerrar_automatico(self):
        self._enviar({
            "evento": "sessao_encerrada",
            "sessao_id": self.sessao_id,
            "motivo": "tempo_esgotado",
            "tempo_consumido_segundos": self.tempo_total
        })
        self._log("Tempo esgotado!")
        self._voltar_login()
        self._reiniciar_se_necessario()

    def _reiniciar_se_necessario(self):
        if not self.reiniciar_ao_encerrar:
            return
        self._log("Iniciando contagem para reiniciar...")
        self._countdown_reinicio(10)

    def _countdown_reinicio(self, segundos, desligar=False):
        """Exibe contagem regressiva no launcher e reinicia (ou desliga) ao zerar."""
        verbo = "Desligando" if desligar else "Reiniciando"
        if segundos > 0:
            self.lbl_login_erro.config(
                text=f"Sessao encerrada. {verbo} em {segundos}s...",
                fg="#f59e0b"
            )
            self.root.after(1000, self._countdown_reinicio, segundos - 1, desligar)
        else:
            self.lbl_login_erro.config(text=f"{verbo} agora...", fg="#ef4444")
            self._log(f"{verbo} o PC...")
            try:
                resultado = subprocess.run(
                    r"C:\Windows\System32\shutdown.exe " + ("/s" if desligar else "/r") + " /f /t 0",
                    shell=True, capture_output=True, text=True
                )
                if resultado.returncode != 0:
                    self._log(f"shutdown falhou (cod {resultado.returncode}): {resultado.stderr.strip()}")
            except Exception as e:
                self._log(f"Erro ao reiniciar: {e}")

    def _encerrar_apps_do_cliente(self):
        """Encerra os processos que o cliente abriu durante a sessao."""
        if not self.whitelist_procs:
            return
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                nome = (proc.info["name"] or "").lower()
                if nome in self.whitelist_procs:
                    proc.kill()
                    self._log(f"Fechando app do cliente: {nome}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _voltar_login(self):
        """Encerra apps, exibe tela de encerramento por 6s e volta ao login."""
        self._encerrar_apps_do_cliente()
        self._desligar_vigia()  # sem vigia, o Explorador volta a ser fechado
        self.barra.esconder()
        self.notificacoes.limpar()
        # depois de fechar os apps (arquivo aberto não sai)
        self.root.after(1500, self._limpar_downloads)
        self._programacao.parar()
        self._tela_apps.limpar()

        # Reseta estado imediatamente para parar o countdown e o monitor de processos
        self.sessao_ativa = False
        self.sessao_id = None
        self.whitelist_apps = []
        self.whitelist_procs = set()
        self._img_refs = []
        self._pids_pre_sessao = set()
        self._sessao_pausada = False
        self._aviso_5min_dado = False

        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass

        # Fecha overlay de pausa se houver
        try:
            if hasattr(self, "_overlay_pausa") and self._overlay_pausa:
                self._overlay_pausa.destroy()
                self._overlay_pausa = None
        except Exception:
            pass

        self.root.deiconify()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.frame_sessao.pack_forget()
        self.frame_login.pack_forget()
        self.frame_encerramento.pack(fill="both", expand=True)
        self._countdown_encerramento(6)

    def _countdown_encerramento(self, restante):
        """Contagem regressiva na tela de encerramento antes de exibir o login."""
        if restante > 0:
            self._lbl_enc_relogio.config(text=str(restante))
            self.root.after(1000, self._countdown_encerramento, restante - 1)
        else:
            self._ir_para_login()

    def _ir_para_login(self):
        """Exibe a tela de login apos o encerramento."""
        self.frame_encerramento.pack_forget()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.frame_login.pack(fill="both", expand=True)

    # ── Manutenção admin ─────────────────────────────────────────────────────
    def _abrir_prompt_admin(self, event=None):
        """Abre o prompt de manutencao. Credenciais validadas pelo servidor."""
        if self.modo_manutencao_ativo:
            self._sair_modo_manutencao()
            return

        # Fecha prompt anterior se houver
        if self._prompt_manutencao and self._prompt_manutencao.winfo_exists():
            self._prompt_manutencao.destroy()

        prompt = tk.Toplevel(self.root)
        self._prompt_manutencao = prompt
        prompt.title("Acesso Administrativo")
        prompt.geometry("320x200")
        prompt.configure(bg="#1A1B26")
        prompt.attributes("-topmost", True)
        prompt.grab_set()

        pos_x = int(self.root.winfo_screenwidth() / 2 - 160)
        pos_y = int(self.root.winfo_screenheight() / 2 - 100)
        prompt.geometry(f"+{pos_x}+{pos_y}")

        tk.Label(prompt, text="Login do operador:", bg="#1A1B26", fg="white",
                 font=(FONTE, 10)).pack(pady=(16, 2))
        login_entry = tk.Entry(prompt, font=(FONTE, 11),
                               bg="#2A2B3D", fg="white", insertbackground="white")
        login_entry.pack(padx=24, fill="x")
        login_entry.focus()

        tk.Label(prompt, text="Senha:", bg="#1A1B26", fg="white",
                 font=(FONTE, 10)).pack(pady=(8, 2))
        senha_entry = tk.Entry(prompt, show="*", font=(FONTE, 11),
                               bg="#2A2B3D", fg="white", insertbackground="white")
        senha_entry.pack(padx=24, fill="x")

        def validar(event=None):
            login = login_entry.get().strip()
            senha = senha_entry.get()
            if not login or not senha:
                return
            btn.config(state="disabled", text="Verificando...")
            if self.conectado:
                # Valida pelo servidor; se ele aceitar, fica lembrado aqui
                self._credenciais_manutencao = (login, senha)
                self._enviar({"evento": "validar_manutencao", "login": login, "senha": senha})
            elif operador_conferido_sem_rede(login, senha):
                # Sem conexao (ex.: servidor errado no agente.cfg): vale quem ja
                # entrou nesta estacao com o servidor no ar
                self._log(f"Manutencao sem conexao: operador {login}")
                prompt.destroy()
                self._prompt_manutencao = None
                self._modo_manutencao()
            else:
                # Sem conexao e operador desconhecido: nao permite manutencao
                for w in prompt.winfo_children():
                    if isinstance(w, tk.Label) and getattr(w, "_is_erro", False):
                        w.config(text="Sem conexao com o servidor")
                        btn.config(state="normal", text="Entrar")
                        return
                lbl = tk.Label(prompt, text="Sem conexao com o servidor",
                               fg="#ef4444", bg="#1A1B26", font=(FONTE, 9))
                lbl._is_erro = True
                lbl.pack(pady=(2, 0))
                btn.config(state="normal", text="Entrar")

        btn = tk.Button(prompt, text="Entrar", command=validar,
                        bg="#4f46e5", fg="white", relief="flat",
                        font=(FONTE, 10))
        btn.pack(pady=12, padx=24, fill="x", ipady=6)

        senha_entry.bind("<Return>", validar)
        login_entry.bind("<Return>", lambda e: senha_entry.focus())
        prompt.bind("<Escape>", lambda e: prompt.destroy())

        def _on_close():
            self._prompt_manutencao = None
            prompt.destroy()
        prompt.protocol("WM_DELETE_WINDOW", _on_close)

    def _abrir_config_conexao(self):
        """Troca o servidor e o nome da estacao sem reinstalar (so na manutencao).
        Salva no agente.cfg e reinicia o agente, que conecta com o novo."""
        if not self.modo_manutencao_ativo:
            return
        janela = tk.Toplevel(self.root)
        janela.title("Configurar conexao")
        janela.configure(bg="#1A1B26")
        janela.resizable(False, False)
        janela.attributes("-topmost", True)
        w, h = 420, 380
        janela.geometry(f"{w}x{h}+{(janela.winfo_screenwidth() - w) // 2}+{(janela.winfo_screenheight() - h) // 2}")
        janela.grab_set()

        def campo(rotulo, valor):
            tk.Label(janela, text=rotulo, bg="#1A1B26", fg="white",
                     font=(FONTE, 10)).pack(anchor="w", padx=24, pady=(14, 2))
            e = tk.Entry(janela, font=(FONTE, 11), bg="#2A2B3D", fg="white", insertbackground="white")
            e.insert(0, valor)
            e.pack(padx=24, fill="x")
            return e

        e_servidor = campo("Endereco do servidor (ex: 10.26.31.99:8000):", self.servidor)
        e_estacao = campo("Nome desta estacao:", self.estacao)
        # Piso (6.18): a lista vem do servidor; mudar de piso faz este PC entrar
        # no outro piso como computador novo (igual a reinstalar escolhendo outro)
        tk.Label(janela, text="Piso:", bg="#1A1B26", fg="white",
                 font=(FONTE, 10)).pack(anchor="w", padx=24, pady=(14, 2))
        pisos = {"lista": [], "estacao": ""}  # [(id, nome)] e "piso_id;nome" deste PC
        v_piso = tk.StringVar(value="(carregando...)")
        m_piso = tk.OptionMenu(janela, v_piso, "(carregando...)")
        m_piso.config(font=(FONTE, 10), bg="#2A2B3D", fg="white", activebackground="#3A3B4D",
                      activeforeground="white", relief="flat", highlightthickness=0, anchor="w")
        m_piso["menu"].config(font=(FONTE, 10), bg="#2A2B3D", fg="white")
        m_piso.pack(padx=24, fill="x")

        def mostrar_pisos(lista, estacao):
            if not janela.winfo_exists():
                return
            pisos["lista"], pisos["estacao"] = lista, estacao
            menu = m_piso["menu"]
            menu.delete(0, "end")
            for _, nome in lista:
                menu.add_command(label=nome, command=lambda n=nome: v_piso.set(n))
            if not lista:
                v_piso.set("(sem conexao com o servidor)")
                return
            atual = (linhas_id_nome(estacao) or [(piso_da_instalacao(), "")])[0][0]
            v_piso.set(next((n for i, n in lista if i == atual), lista[0][1]))

        def baixar_pisos():
            # thread: so rede aqui
            base = self.servidor.replace("wss://", "https://").replace("ws://", "http://")
            lista, estacao = [], ""
            try:
                with abrir_url(f"{base}/api/agente/pisos", timeout=5) as r:
                    lista = linhas_id_nome(r.read().decode("utf-8", "replace"))
                if self.identificador:
                    alvo = f"{base}/api/agente/estacao?id={urllib.parse.quote(self.identificador)}"
                    with abrir_url(alvo, timeout=5) as r:
                        estacao = r.read().decode("utf-8", "replace")
            except Exception as ex:
                self._log(f"Configurar conexao: pisos nao carregaram ({ex})")
            self.root.after(0, lambda: mostrar_pisos(lista, estacao))
        threading.Thread(target=baixar_pisos, daemon=True).start()
        e_servidor.focus()
        lbl = tk.Label(janela, text="", bg="#1A1B26", fg="#94a3b8", font=(FONTE, 9),
                       wraplength=w - 48, justify="left")
        lbl.pack(anchor="w", padx=24, pady=(10, 0))
        botoes = tk.Frame(janela, bg="#1A1B26")
        botoes.pack(side="bottom", fill="x", padx=24, pady=16)

        def lidos():
            return normalizar_servidor(e_servidor.get()), e_estacao.get().strip()

        def testar():
            servidor, estacao = lidos()
            if not servidor or not estacao:
                return lbl.config(text="Preencha o servidor e o nome da estacao", fg="#ef4444")
            lbl.config(text="Testando...", fg="#94a3b8")

            def trabalhar():
                ok, msg = testar_conexao(servidor, estacao)
                self.root.after(0, lambda: janela.winfo_exists() and
                                lbl.config(text=msg, fg="#22c55e" if ok else "#ef4444"))
            threading.Thread(target=trabalhar, daemon=True).start()

        def salvar():
            servidor, estacao = lidos()
            if not servidor or not estacao:
                return lbl.config(text="Preencha o servidor e o nome da estacao", fg="#ef4444")
            import tkinter.messagebox as _mb
            piso = next((i for i, n in pisos["lista"] if n == v_piso.get()), None)
            if piso_mudou(pisos["estacao"], piso):
                antes = linhas_id_nome(pisos["estacao"])[0]
                nome_antes = next((n for i, n in pisos["lista"] if i == antes[0]), "anterior")
                if not _mb.askyesno("Mudar de piso", (
                        f"Este computador é a {antes[1]} do piso {nome_antes}.\n\n"
                        f"No piso {v_piso.get()} ele entra como computador novo: assume a estação "
                        f"{estacao} do mapa desse piso, ou vai para aprovação (Mapa → Novas estações). "
                        f"A {antes[1]} do piso {nome_antes} fica no mapa sem computador (exclua no painel).\n\n"
                        "Mudar de piso?"), parent=janela):
                    return
                gravar_cfg(PISO=piso, ID="")  # sem ID: o agente cria outro ao reiniciar
                self._log(f"Piso trocado para {v_piso.get()}: este PC entra como computador novo")
            else:
                if piso:
                    gravar_cfg(PISO=piso)
                if estacao != self.estacao and self.identificador and self.aprovada:
                    # 1.18: o servidor reconhece o PC pelo id; nome novo vira um
                    # pedido em Novas estacoes (ate aceitar, segue com o atual)
                    _mb.showinfo("Troca de nome", (
                        f"O nome {estacao} vai para aprovação no painel (Mapa → Novas estações).\n\n"
                        f"Até um administrador aceitar, este computador continua como {self.estacao}. "
                        "Também dá para trocar direto pelo lápis da estação no Mapa."), parent=janela)
            salvar_cfg(servidor, estacao)
            self._log(f"Conexao trocada para {servidor} / {estacao} - reiniciando o agente")
            # Recomeca do zero com o agente.cfg novo (como na atualizacao)
            os.execv(sys.executable, [sys.executable] + sys.argv)

        for texto, cor, cmd in (("Salvar e reiniciar", "#4f46e5", salvar), ("Testar", "#2A2B3D", testar),
                                ("Cancelar", "#2A2B3D", janela.destroy)):
            tk.Button(botoes, text=texto, command=cmd, bg=cor, fg="white", relief="flat",
                      font=(FONTE, 10), padx=12, pady=4).pack(side="right", padx=(6, 0))

    def _exibir_mensagem_operador(self, texto, titulo="Mensagem do operador", modal=True):
        """Mostra a mensagem do operador inteira. A janela cresce com o texto (era
        380x160 fixo e cortava as longas); passando de ~60% da tela, rola.
        modal=False: aberta pela notificacao, durante a sessao (nao prende os apps)."""
        popup = tk.Toplevel(self.root)
        popup.title(titulo)
        popup.configure(bg="#1A1B26")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        tk.Label(popup, text=titulo, font=(FONTE, 11, "bold"),
                 fg="#f59e0b", bg="#1A1B26").pack(pady=(16, 6))
        botao = tk.Button(popup, text="OK", font=(FONTE, 10, "bold"),
                          bg="#3b82f6", fg="white", relief="flat", padx=20, pady=6,
                          command=popup.destroy)
        botao.pack(side="bottom", pady=(8, 16))

        largura = 460
        util = largura - 60  # margens e a barra de rolagem
        altura_max = int(popup.winfo_screenheight() * 0.6)
        fonte = tkfont.Font(family=FONTE, size=11)
        # altura conforme as linhas que o texto ocupa nessa largura
        altura_texto = linhas_do_texto(texto, fonte.measure, util) * fonte.metrics("linespace") + 8
        quadro = tk.Frame(popup, bg="#1A1B26")
        quadro.pack(fill="both", expand=True, padx=(20, 8))
        caixa = tk.Text(quadro, font=fonte, fg="#e2e8f0", bg="#1A1B26", relief="flat", wrap="word",
                        width=1, height=1, borderwidth=0, highlightthickness=0, cursor="arrow")
        if altura_texto > altura_max:
            barra = tk.Scrollbar(quadro, command=caixa.yview)
            caixa.config(yscrollcommand=barra.set)
            barra.pack(side="right", fill="y")
            altura_texto = altura_max
        caixa.insert("1.0", texto)
        caixa.tag_configure("centro", justify="center")
        caixa.tag_add("centro", "1.0", "end")
        caixa.config(state="disabled")
        caixa.pack(side="left", fill="both", expand=True)
        h = altura_texto + 110
        x = (popup.winfo_screenwidth() - largura) // 2
        y = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{largura}x{h}+{x}+{y}")
        if modal:
            popup.grab_set()
        botao.focus_set()
        self._log(f"Mensagem exibida: {texto}")

    # ── Atualizacao do agente (so na manutencao, 6.13) ──────────────────────
    def _servidor_http(self):
        return self.servidor.replace("wss://", "https://").replace("ws://", "http://")

    def _versao_conferida(self, versao):
        """Resposta do servidor sobre a versao (None: sem conexao)."""
        self.versao_nova = versao if ha_versao_nova(versao, VERSAO) else None
        if self.versao_nova:
            self._log(f"Versao nova do agente no servidor: {self.versao_nova} (atualize pela manutencao)")
        self._mostrar_botao_atualizar(sem_conexao=versao is None)

    def _mostrar_botao_atualizar(self, sem_conexao=False, texto=None):
        if not hasattr(self, "btn_atualizar"):
            return
        if texto:
            self.btn_atualizar.config(text=texto, state="disabled")
        elif self.versao_nova:
            self.btn_atualizar.config(text=f"Atualizar para a versao {self.versao_nova}", state="normal",
                                      bg="#15803d")
        else:
            self.btn_atualizar.config(text="Sem conexao: tentar de novo" if sem_conexao
                                      else f"Agente em dia (v{VERSAO})", state="normal", bg="#92400e")

    def _clicar_atualizar(self):
        if not self.modo_manutencao_ativo:
            return
        if not self.versao_nova:
            # confere de novo agora
            self._mostrar_botao_atualizar(texto="Verificando...")
            checar_atualizacao(self, self._servidor_http())
            return
        import tkinter.messagebox as _mb
        if not _mb.askyesno("Atualizar o agente",
                            f"Atualizar o agente da versao {VERSAO} para a {self.versao_nova}?\n\n"
                            "Ele baixa a versao nova e reinicia (volta na tela de login).",
                            parent=self.root):
            return
        self._mostrar_botao_atualizar(texto="Baixando...")

        def trabalhar():
            baixado = baixar_atualizacao(self._servidor_http())
            self.root.after(0, lambda: self._aplicar_atualizacao(baixado))
        threading.Thread(target=trabalhar, daemon=True).start()

    def _atualizar_pelo_painel(self):
        """Baixa a versao do servidor e reinicia, sem passar pela manutencao.
        Nunca com um cliente usando (o servidor ja confere; aqui de novo)."""
        if self.sessao_ativa:
            self._log("Atualizacao pelo painel ignorada: ha um cliente usando")
            return
        self._mostrar_botao_atualizar(texto="Baixando...")

        def trabalhar():
            baixado = baixar_atualizacao(self._servidor_http())
            self.root.after(0, lambda: self._aplicar_atualizacao(baixado, pelo_painel=True))
        threading.Thread(target=trabalhar, daemon=True).start()

    def _aplicar_atualizacao(self, baixado, pelo_painel=False):
        """Troca o arquivo do agente e reinicia. Na manutencao ou pelo painel
        (sem cliente usando)."""
        if self.sessao_ativa or not (self.modo_manutencao_ativo or pelo_painel):
            return
        if not baixado and pelo_painel:
            self._log("Atualizacao pelo painel: nada novo para baixar (ou o servidor nao respondeu)")
            self._mostrar_botao_atualizar()
            return
        if not baixado:
            self._log("Atualizacao: nao foi possivel baixar a versao nova")
            self.versao_nova = None
            self._mostrar_botao_atualizar(sem_conexao=True)
            return
        versao, caminho_novo = baixado
        self._log(f"Atualizando o agente para a versao {versao} e reiniciando...")
        os.replace(caminho_novo, os.path.abspath(__file__))
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _modo_manutencao(self):
        self.barra.esconder()
        if self.sessao_ativa:
            consumido = int(time.time() - self.inicio_sessao)
            self._enviar({
                "evento": "sessao_encerrada",
                "sessao_id": self.sessao_id,
                "motivo": "manutencao",
                "tempo_consumido_segundos": consumido
            })
            self._voltar_login()
        else:
            self.root.attributes("-fullscreen", False)
            self.root.attributes("-topmost", False)

        self.modo_manutencao_ativo = True
        self._liberar_janela(True)
        self._enviar({"evento": "status_estacao", "status": "manutencao"})
        self.frame_manutencao.pack(fill="x", side="top", before=self.root.pack_slaves()[0])
        self._log("Modo manutencao ativado")
        # confere se ha versao nova, para o botao ja mostrar
        self._mostrar_botao_atualizar(texto="Verificando atualizacao...")
        checar_atualizacao(self, self._servidor_http())

    def _sair_modo_manutencao(self):
        self.modo_manutencao_ativo = False
        self._liberar_janela(False)
        self.frame_manutencao.pack_forget()
        self._enviar({"evento": "status_estacao", "status": "livre"})
        self.frame_sessao.pack_forget()
        self.frame_login.pack(fill="both", expand=True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-fullscreen", True)
        self.root.lift()
        self.root.focus_force()
        self._log("Modo manutencao encerrado - retornando ao login")

    @staticmethod
    def _fmt(segundos):
        segundos = int(max(0, segundos))
        h, r = divmod(segundos, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ── Whitelist de processos ────────────────────────────────────────────────
    def _verificar_processos(self):
        pid_atual = os.getpid()
        if not self.sessao_ativa and not self.modo_manutencao_ativo:
            # Tela de login: nada do cliente fica aberto, nem o que ele abriu
            # na inicializacao do Windows antes de o agente aparecer
            for proc in psutil.process_iter(["name"]):
                try:
                    nome = (proc.info["name"] or "").lower()
                    if nome in PROCESSOS_BLOQUEADOS_NO_LOGIN or nome in PROCESSOS_SEMPRE_BLOQUEADOS:
                        proc.kill()
                        self._log(f"Bloqueado (tela de login): {nome}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self._fechar_janelas_fora_da_whitelist(pid_atual, set())
        if self.sessao_ativa:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    nome = (proc.info["name"] or "").lower()
                    pid = proc.info["pid"]

                    if pid == pid_atual or not nome or pid in self._pids_proprios:
                        continue

                    if nome in PROCESSOS_SEMPRE_BLOQUEADOS:
                        proc.kill()
                        self._log(f"Bloqueado (proibido): {nome}")
                        continue

                    # Processos em segundo plano de antes da sessao: nao toca
                    # (as janelas deles sao conferidas abaixo)
                    if pid in self._pids_pre_sessao:
                        continue

                    if not self.whitelist_procs:
                        continue
                    if nome in PROCESSOS_SEGUROS:
                        continue
                    if nome in self.whitelist_procs:
                        continue

                    proc.kill()
                    self._log(f"Bloqueado (fora da whitelist): {nome}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if self.whitelist_procs:
                self._fechar_janelas_fora_da_whitelist(pid_atual, self.whitelist_procs)
            self.barra.atualizar_apps(self._janelas_dos_apps(pid_atual))
            self.barra.manter()

        self.root.after(1000, self._verificar_processos)

    def _janelas_dos_apps(self, pid_atual):
        """[(hwnd, titulo, processo)] das janelas dos apps liberados, para o dock."""
        janelas = []
        for pid, lista in janelas_visiveis().items():
            if pid == pid_atual:
                continue
            try:
                nome = psutil.Process(pid).name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if nome not in self.whitelist_procs:
                continue
            for hwnd, _classe in lista:
                titulo = titulo_da_janela(hwnd)
                if titulo:
                    janelas.append((hwnd, titulo, nome))
        return janelas

    def _fechar_janelas_fora_da_whitelist(self, pid_atual, permitidos):
        """Um programa que já rodava antes do login (Edge em segundo plano, por
        exemplo) abre janelas novas sem criar processo novo; o Explorador de
        Arquivos é o próprio explorer.exe. Por isso também se confere quem é o
        dono de cada janela visível."""
        for pid, janelas in janelas_visiveis().items():
            if pid == pid_atual:
                continue
            try:
                nome = psutil.Process(pid).name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if nome in permitidos:
                continue
            if nome in JANELAS_DE_PROCESSOS_SEGUROS:
                classe_app, descricao = JANELAS_DE_PROCESSOS_SEGUROS[nome]
                if nome == "explorer.exe" and self.sessao_ativa and self._vigia and self._vigia.poll() is None:
                    continue  # Meus arquivos: o vigia mantem o Explorador em Downloads
                for hwnd, classe in janelas:
                    if classe == classe_app:
                        fechar_janela(hwnd)
                        self._log(f"Bloqueado (fora da whitelist): {descricao}")
                continue
            if nome in PROCESSOS_SEGUROS:
                continue
            try:
                psutil.Process(pid).kill()
                self._log(f"Bloqueado (fora da whitelist): {nome}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


# ── Auto-update ──────────────────────────────────────────────────────────────

def _versao_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def ha_versao_nova(versao_servidor, versao_local) -> bool:
    return bool(versao_servidor) and _versao_tuple(versao_servidor) > _versao_tuple(versao_local)


def versao_no_servidor(servidor_http: str):
    """A versao que o servidor distribui (None sem conexao). Roda numa thread."""
    import json as _json
    try:
        with abrir_url(f"{servidor_http}/api/agente/versao", timeout=5) as r:
            return _json.loads(r.read()).get("versao")
    except Exception as e:
        print(f"Aviso: falha ao verificar update: {e}")
        return None


def baixar_atualizacao(servidor_http: str):
    """Se houver versao nova no servidor, baixa ao lado deste arquivo.
    Roda numa thread (sem Tkinter). Devolve (versao, caminho_baixado) ou None."""
    try:
        versao_servidor = versao_no_servidor(servidor_http)
        if not ha_versao_nova(versao_servidor, VERSAO):
            return None
        caminho_novo = os.path.abspath(__file__) + ".novo"
        with abrir_url(f"{servidor_http}/api/agente/download", timeout=30) as r:
            conteudo = r.read()
        with open(caminho_novo, "wb") as f:
            f.write(conteudo)
        return versao_servidor, caminho_novo
    except Exception as e:
        print(f"Aviso: falha ao verificar update: {e}")
        return None


def checar_atualizacao(app, servidor_http: str):
    """So confere, em segundo plano, se ha versao nova (6.13). O agente nunca se
    atualiza sozinho: com versao nova, o botao da faixa da manutencao passa a
    oferecer "Atualizar para a versao X" e o operador escolhe a hora."""
    def trabalhar():
        versao = versao_no_servidor(servidor_http)
        app.root.after(0, lambda: app._versao_conferida(versao))

    threading.Thread(target=trabalhar, daemon=True).start()


CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agente.cfg")

def carregar_cfg():
    """Le servidor e estacao de agente.cfg (formato KEY=VALUE)."""
    cfg = {}
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if "=" in linha and not linha.startswith("#"):
                        k, _, v = linha.partition("=")
                        cfg[k.strip()] = v.strip()
        except Exception:
            pass
    return cfg

def mensagens_pendentes(pendentes, agora):
    """Fins de sessao guardados sem conexao, com ha quantos segundos aconteceram
    (o servidor desconta so ate la). `agora` e `pendentes` em time.monotonic()."""
    saida = []
    for msg, quando in pendentes:
        msg = dict(msg)
        msg["segundos_atras"] = max(0, int(agora - quando))
        saida.append(msg)
    return saida


def gravar_cfg(**valores):
    """Atualiza chaves do agente.cfg sem apagar as outras (vazio remove)."""
    cfg = carregar_cfg()
    cfg.update({k: v for k, v in valores.items() if v is not None})
    try:
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            f.write("# MatheCafe - configuracao da estacao (gerado automaticamente)\n")
            for k, v in cfg.items():
                if v:
                    f.write(f"{k}={v}\n")
    except Exception as e:
        print(f"Aviso: nao foi possivel salvar agente.cfg: {e}")


def salvar_cfg(servidor, estacao, tema=None):
    """Persiste servidor, estacao (e tema) em agente.cfg para a proxima inicializacao."""
    gravar_cfg(SERVIDOR=servidor, ESTACAO=estacao, TEMA=tema)


AGUARDANDO_APROVACAO = "Este computador aguarda aprovação no painel do MatheCafé (Mapa → Novas estações)."


def identificador_da_estacao():
    """O id desta instalacao (ID= no agente.cfg), criado na primeira vez. E por ele
    que o servidor reconhece o PC: um PC novo aparece no painel para aprovar."""
    atual = carregar_cfg().get("ID", "").strip()
    if atual:
        return atual
    novo = uuid.uuid4().hex
    gravar_cfg(ID=novo)
    return novo


def piso_da_instalacao():
    """O piso escolhido no instalador (PISO= no agente.cfg, o id do piso). Com
    ele o servidor poe o PC na estacao desse nome naquele piso: AD-01 pode
    existir no Adulto e no Infantil (6.18)."""
    piso = carregar_cfg().get("PISO", "").strip()
    return piso if piso.isdigit() else None


def linhas_id_nome(texto):
    """Respostas em texto do servidor ("1;Adulto" por linha) -> [("1", "Adulto"), ...]."""
    linhas = []
    for linha in (texto or "").splitlines():
        if ";" in linha:
            a, _, b = linha.strip().partition(";")
            if a.strip():
                linhas.append((a.strip(), b.strip()))
    return linhas


def piso_mudou(resposta_estacao, piso_escolhido):
    """Trocar para piso_escolhido muda de piso? resposta_estacao e o que o servidor
    diz deste PC (/api/agente/estacao: "piso_id;nome", vazio se nao conhece).
    Mudou: o PC precisa de um ID novo, senao o servidor o acha pela estacao do
    piso antigo (como no instalar.bat, 6.18)."""
    atual = linhas_id_nome(resposta_estacao)
    return bool(atual and piso_escolhido and atual[0][0] != str(piso_escolhido))


def url_da_estacao(servidor, estacao, identificador=None, piso=None):
    # quote: nomes com espaço ou acento ("PC 01") viram um endereço válido
    url = f"{servidor}/ws/estacao/{urllib.parse.quote(estacao)}"
    params = [("id", identificador), ("piso", piso)]
    consulta = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params if v)
    return url + ("?" + consulta if consulta else "")


def linhas_do_texto(texto, medir, largura_px):
    """Quantas linhas o texto ocupa quebrando por palavra em largura_px
    (medir: px de um trecho, ex. tkfont.Font.measure). Palavra maior que a
    linha conta o que ela ocupa quebrada."""
    total = 0
    for paragrafo in (texto or "").split("\n"):
        linha = ""
        n = 1
        for palavra in paragrafo.split():
            tentativa = f"{linha} {palavra}" if linha else palavra
            if medir(tentativa) <= largura_px:
                linha = tentativa
                continue
            if linha:
                n += 1
            # palavra enorme (link): ocupa varias linhas sozinha
            while medir(palavra) > largura_px and len(palavra) > 1:
                corte = max(1, int(len(palavra) * largura_px / medir(palavra)))
                palavra = palavra[corte:]
                n += 1
            linha = palavra
        total += n
    return max(1, total)


def salvar_tema(tema):
    gravar_cfg(TEMA=tema)


def normalizar_servidor(texto):
    """Aceita IP puro, http:// ou https:// e devolve ws:// ou wss://."""
    servidor = (texto or "").strip().rstrip("/")
    if not servidor:
        return ""
    servidor = servidor.replace("https://", "wss://").replace("http://", "ws://")
    if not servidor.startswith("ws"):
        servidor = "ws://" + servidor
    return servidor


def testar_conexao(servidor, estacao):
    """Conecta como a estacao e diz se o servidor a aceitou. Roda numa thread."""
    url = url_da_estacao(servidor, estacao, identificador_da_estacao(), piso_da_instalacao())
    proxy = None if servidor_na_rede_local(url) else True

    async def tentar():
        async with websockets.connect(url, open_timeout=6, proxy=proxy) as ws:
            # Abrir mandando ping e coisa de agente antigo: o servidor encerraria a
            # sessao aberta desta estacao
            await ws.send(json.dumps({"evento": "teste_conexao"}))
            await asyncio.wait_for(ws.recv(), timeout=6)

    try:
        asyncio.run(tentar())
        return True, f"Conectou: o servidor reconhece a estacao {estacao}."
    except websockets.exceptions.ConnectionClosed as e:
        if e.rcvd and e.rcvd.code == 4004:
            return False, f"O servidor respondeu, mas recusou a estacao '{estacao}' (recusada em Novas estacoes)."
        return False, f"O servidor fechou a conexao: {e}"
    except Exception as e:
        return False, f"Nao conectou em {servidor}: {e or type(e).__name__}"


# Operadores que ja entraram na manutencao desta estacao com o servidor no ar:
# guardados so como hash, para entrar na manutencao quando nao ha conexao
OPERADORES_LEMBRADOS = 5


def _hash_operador(login, senha, sal):
    dado = f"{login.strip().lower()}\n{senha}".encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", dado, bytes.fromhex(sal), 200_000).hex()


def _operadores_guardados():
    itens = []
    for item in carregar_cfg().get("OPERADORES", "").split(","):
        partes = item.rsplit(":", 2)
        if len(partes) == 3:
            itens.append(partes)
    return itens


def esquecer_operador(login):
    login = login.strip().lower()
    gravar_cfg(OPERADORES=",".join(":".join(p) for p in _operadores_guardados() if p[0] != login))


def lembrar_operador(login, senha):
    login = login.strip().lower()
    sal = os.urandom(16).hex()
    outros = [":".join(p) for p in _operadores_guardados() if p[0] != login]
    novos = (outros + [f"{login}:{sal}:{_hash_operador(login, senha, sal)}"])[-OPERADORES_LEMBRADOS:]
    gravar_cfg(OPERADORES=",".join(novos))


def operador_conferido_sem_rede(login, senha):
    login = login.strip().lower()
    for nome, sal, guardado in _operadores_guardados():
        if nome == login:
            try:
                return hmac.compare_digest(guardado, _hash_operador(login, senha, sal))
            except ValueError:
                return False
    return False


def main():
    parser = argparse.ArgumentParser(description="MatheCafe - Agente da Estacao")
    parser.add_argument("--servidor", default=None,
                         help="URL do servidor: ws://localhost:8000 ou wss://mathecafe.onrender.com")
    parser.add_argument("--estacao", default=None,
                         help="Nome da estacao cadastrada no painel, ex: PC-01")
    args = parser.parse_args()

    # Prioridade: argumento CLI > agente.cfg > perguntar
    cfg = carregar_cfg()
    servidor = args.servidor or cfg.get("SERVIDOR", "")
    estacao = args.estacao or cfg.get("ESTACAO", "")

    # Ainda falta algum dado — pede via caixa de dialogo simples
    if not servidor or not estacao:
        root_cfg = tk.Tk()
        root_cfg.withdraw()

        if not servidor:
            servidor = tk.simpledialog.askstring(
                "MatheCafe - Configuracao",
                "Endereco do servidor (ex: ws://192.168.0.10:8000):",
                parent=root_cfg
            ) or ""
        if not estacao:
            estacao = tk.simpledialog.askstring(
                "MatheCafe - Configuracao",
                "Nome desta estacao (igual ao cadastrado no Mapa, ex: PC-01):",
                parent=root_cfg
            ) or ""

        root_cfg.destroy()
        if not servidor or not estacao:
            print("Servidor ou estacao nao informados. Encerrando.")
            return

    servidor = normalizar_servidor(servidor)

    # Salva para a proxima vez
    salvar_cfg(servidor, estacao)

    # Se o agente fechar ou cair, a barra do Windows (escondida na sessão) volta
    atexit.register(barra_do_windows, True)
    root = tk.Tk()
    # Erros dentro da interface: só no arquivo, sem janela (o agente segue rodando)
    root.report_callback_exception = lambda t, v, tb: registrar_erro(t, v, tb, mostrar=False)
    app = AgenteApp(root, servidor, estacao)
    # So confere a versao, depois da janela no ar; atualizar e pela manutencao (6.13)
    checar_atualizacao(app, servidor.replace("wss://", "https://").replace("ws://", "http://"))
    root.mainloop()


if __name__ == "__main__":
    main()
