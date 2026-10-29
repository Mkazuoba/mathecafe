"""
MatheCafé - Agente da Estação

Conecta a estação ao servidor via WebSocket e oferece:
- Tela de login do cliente
- Countdown da sessão
- Encerramento manual ou automático (tempo esgotado)
- Launcher de apps com grade visual
- Modo manutenção autenticado pelo servidor (Ctrl+Shift+M)
- Log de comunicação para debug

Uso:
    python agente.py --servidor ws://localhost:8000 --estacao PC-01
    python agente.py --servidor wss://mathecafe.onrender.com --estacao PC-01

IMPORTANTE:
- A estação precisa estar cadastrada no painel com o MESMO NOME de --estacao.
- Rode como Administrador para que o bloqueio de processos funcione.
"""
# Versao do agente — incrementar a cada publicacao de update.
# Unica declaracao: o servidor le a primeira linha VERSAO deste arquivo.
VERSAO = "1.6.3"

import asyncio
import json
import threading
import queue
import argparse
import time
import os
import subprocess
import ctypes
from datetime import datetime
from io import BytesIO
import urllib.parse
import urllib.request
import sys
import traceback
import tkinter as tk
from tkinter import font as tkfont, scrolledtext, simpledialog

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
    from PIL import Image, ImageTk
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


def botao_minimizar(hwnd, ativo):
    """Mostra ou tira o botão de minimizar da barra de título."""
    if _u32 is None:
        return
    GWL_STYLE, WS_MINIMIZEBOX = -16, 0x00020000
    estilo = _u32.GetWindowLongW(hwnd, GWL_STYLE)
    estilo = estilo | WS_MINIMIZEBOX if ativo else estilo & ~WS_MINIMIZEBOX
    _u32.SetWindowLongW(hwnd, GWL_STYLE, estilo)
    # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED: redesenha a moldura
    _u32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)


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


class AgenteApp:
    def __init__(self, root, servidor, estacao):
        self.root = root
        self.servidor = servidor.rstrip("/")
        self.estacao = estacao

        self.incoming = queue.Queue()
        self.loop = None
        self.ws = None
        self.conectado = False

        # Estado da sessão
        self.sessao_ativa = False
        self.sessao_id = None
        self.cliente_nome = None
        self.tempo_total = 0
        self.inicio_sessao = None
        self.whitelist_apps = []
        self.whitelist_procs = set()
        self.reiniciar_ao_encerrar = False
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

        self.root.title(f"MatheCafe v{VERSAO} - {estacao}")
        self.root.configure(bg="#0f1117")
        self.root.resizable(True, True)
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)

        # Impede fechar a janela durante a sessão
        self.root.protocol("WM_DELETE_WINDOW", self._tentar_fechar)

        self._build_ui()
        self._start_ws_thread()

        # Atalhos
        self._teclado = BloqueioTeclado(self._tecla_bloqueada)
        self.root.bind("<Escape>", self._tentar_esc)
        self.root.bind("<Unmap>", self._ao_minimizar)
        self.root.bind("<Control-Shift-M>", self._abrir_prompt_admin)
        self.root.bind("<Control-Shift-KeyPress-M>", self._abrir_prompt_admin)

        self.root.after(100, self._processar_fila)
        self.root.after(1000, self._atualizar_countdown)
        self.root.after(3000, self._verificar_processos)

    # ── Controle de janela ────────────────────────────────────────────────────
    def _tentar_fechar(self):
        """Fechar (X, Alt+F4) só funciona no modo manutenção."""
        if self.modo_manutencao_ativo:
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
            self.root.state("zoomed")
        self.root.lift()

    def _permitir_minimizar(self, ativo):
        try:
            self.root.update_idletasks()
            botao_minimizar(int(self.root.wm_frame(), 16), ativo)
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
        self.c_bg = bg = "#0f1117"
        self.c_bg2 = bg2 = "#171b26"
        self.c_bg3 = bg3 = "#1e2333"
        self.c_text = text = "#e2e8f0"
        self.c_text2 = text2 = "#94a3b8"
        self.c_accent = accent = "#6366f1"

        title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        normal_font = tkfont.Font(family="Segoe UI", size=11)
        big_font = tkfont.Font(family="Consolas", size=36, weight="bold")
        small_font = tkfont.Font(family="Consolas", size=9)
        self.f_normal = normal_font
        self.f_small = small_font
        self.f_app = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_icon = tkfont.Font(family="Segoe UI", size=22, weight="bold")

        # ── Cabeçalho ──
        self.header_frame = header = tk.Frame(self.root, bg=bg2)
        header.pack(fill="x")
        tk.Label(header, text="MatheCafe", font=title_font, fg=accent, bg=bg2).pack(side="left", padx=(14,4), pady=10)
        ver_font = tkfont.Font(family="Segoe UI", size=9)
        tk.Label(header, text=f"v{VERSAO}", font=ver_font, fg="#6b7280", bg=bg2).pack(side="left", pady=10)
        self.lbl_estacao = tk.Label(header, text=self.estacao, font=normal_font, fg=text2, bg=bg2)
        self.lbl_estacao.pack(side="left", padx=4)
        self.lbl_status = tk.Label(header, text="conectando...", font=small_font, fg="#f97316", bg=bg2)
        self.lbl_status.pack(side="right", padx=14)

        # ── Frame de login ──
        self.frame_login = tk.Frame(self.root, bg=bg)

        # container centralizado de largura fixa
        _form = tk.Frame(self.frame_login, bg=bg)
        _form.pack(expand=True)
        # espacador fixa a largura; pack_propagate(False) sem height colapsava o form em 1px
        tk.Frame(_form, bg=bg, width=360, height=0).pack()

        tk.Label(_form, text="Faca login para iniciar sua sessao",
                 font=normal_font, fg=text, bg=bg).pack(pady=(40, 24))

        tk.Label(_form, text="LOGIN", font=small_font, fg=text2, bg=bg).pack(anchor="w")
        self.entry_login = tk.Entry(_form, font=normal_font, bg=bg3, fg=text,
                                     insertbackground=text, relief="flat")
        self.entry_login.pack(fill="x", pady=(2, 12), ipady=6)

        tk.Label(_form, text="SENHA", font=small_font, fg=text2, bg=bg).pack(anchor="w")
        self.entry_senha = tk.Entry(_form, font=normal_font, bg=bg3, fg=text,
                                     insertbackground=text, relief="flat", show="*")
        self.entry_senha.pack(fill="x", pady=(2, 16), ipady=6)
        self.entry_senha.bind("<Return>", lambda e: self._fazer_login())

        self.btn_login = tk.Button(_form, text="Entrar", font=normal_font,
                                    bg=accent, fg="white", relief="flat", activebackground="#4f46e5",
                                    command=self._fazer_login, state="disabled")
        self.btn_login.pack(fill="x", ipady=8)

        self.lbl_login_erro = tk.Label(_form, text="", font=small_font, fg="#ef4444", bg=bg)
        self.lbl_login_erro.pack(pady=8)

        # ── Frame de sessão (launcher) ──
        self.frame_sessao = tk.Frame(self.root, bg=bg)

        topo_sessao = tk.Frame(self.frame_sessao, bg=bg2)
        topo_sessao.pack(fill="x")
        self.lbl_cliente = tk.Label(topo_sessao, text="", font=normal_font, fg=text, bg=bg2)
        self.lbl_cliente.pack(side="left", padx=16, pady=10)
        self.lbl_countdown = tk.Label(topo_sessao, text="00:00:00",
                                       font=tkfont.Font(family="Consolas", size=16, weight="bold"),
                                       fg="#22c55e", bg=bg2)
        self.lbl_countdown.pack(side="right", padx=16, pady=10)
        tk.Button(topo_sessao, text="Encerrar sessao", font=small_font,
                  bg="#ef4444", fg="white", relief="flat", activebackground="#dc2626",
                  command=self._encerrar_sessao_cliente).pack(side="right", padx=8, pady=8, ipady=2)

        tk.Label(self.frame_sessao, text="Selecione um aplicativo para abrir",
                 font=small_font, fg=text2, bg=bg).pack(pady=(16, 8))

        self.frame_launcher = tk.Frame(self.frame_sessao, bg=bg)
        self.frame_launcher.pack(expand=True, fill="both", padx=20)

        self.frame_login.pack(fill="both", expand=True)

        # ── Frame de encerramento ──
        self.frame_encerramento = tk.Frame(self.root, bg=bg)
        tk.Label(self.frame_encerramento, text="SESSAO ENCERRADA",
                 font=tkfont.Font(family="Segoe UI", size=24, weight="bold"),
                 fg="#ef4444", bg=bg).pack(expand=False, pady=(80, 12))
        tk.Label(self.frame_encerramento, text="Aguarde a liberacao do sistema...",
                 font=normal_font, fg=text2, bg=bg).pack()
        self._lbl_enc_relogio = tk.Label(self.frame_encerramento, text="6",
                                          font=big_font, fg="#f59e0b", bg=bg)
        self._lbl_enc_relogio.pack(pady=20)

        # ── Log ──
        self.frame_log = tk.Frame(self.root, bg=bg)
        tk.Label(self.frame_log, text="LOG DE COMUNICACAO", font=small_font, fg=text2, bg=bg).pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(self.frame_log, height=8, bg=bg3, fg=text2,
                                              font=small_font, relief="flat", wrap="word")
        self.log.pack(fill="both", padx=10, pady=(2, 10), expand=False)
        self.log.configure(state="disabled")
        self.frame_log.pack(fill="both", expand=False)

        # ── Barra de manutenção (oculta inicialmente) ──
        self.frame_manutencao = tk.Frame(self.root, bg="#f59e0b")
        tk.Label(self.frame_manutencao, text="Modo Manutencao ativo",
                 bg="#f59e0b", fg="black", font=normal_font).pack(side="left", padx=14, pady=8)
        tk.Button(self.frame_manutencao, text="Encerrar manutencao",
                  bg="#92400e", fg="white", relief="flat", font=small_font,
                  command=self._sair_modo_manutencao).pack(side="right", padx=14, pady=8)

    def _log(self, msg, _remoto=True):
        self.log.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        # Repassa o log para o servidor (visivel no painel do operador)
        # _remoto=False evita loop quando _enviar() por si chama _log()
        if _remoto and self.loop and self.ws:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.ws.send(json.dumps({"evento": "log_agente", "dados": {"msg": msg}})),
                    self.loop
                )
            except Exception:
                pass

    # ── WebSocket (thread separada) ──────────────────────────────────────────
    def _start_ws_thread(self):
        t = threading.Thread(target=self._thread_main, daemon=True)
        t.start()

    def _thread_main(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self):
        # quote: nomes com espaço ou acento ("PC 01") viram um endereço válido
        url = f"{self.servidor}/ws/estacao/{urllib.parse.quote(self.estacao)}"
        # Servidor na rede interna: conexão direta. O websockets usa o proxy do
        # Windows por padrão, e redes com proxy desviam até IPs internos.
        proxy = None if servidor_na_rede_local(url) else True
        self.incoming.put({"evento": "_info", "dados": {
            "msg": f"Conectando a {url}" + (" (direto, sem proxy)" if proxy is None else "")}})
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, proxy=proxy) as ws:
                    # Só fica "online" quando o servidor responder: uma estação
                    # não cadastrada é fechada antes do pong
                    await ws.send(json.dumps({"evento": "ping"}))
                    async for raw in ws:
                        if not self.conectado:
                            self.ws = ws
                            self.conectado = True
                            self.incoming.put({"evento": "_conectado"})
                        self.incoming.put(json.loads(raw))
            except websockets.exceptions.ConnectionClosed as e:
                if e.rcvd and e.rcvd.code == 4004:
                    self.incoming.put({"evento": "_erro", "dados": {"nao_cadastrada": True, "msg": (
                        f"Estacao '{self.estacao}' nao esta cadastrada no servidor. "
                        "Cadastre no painel (Mapa -> Modo configuracao) com esse nome exato.")}})
                else:
                    self.incoming.put({"evento": "_erro", "dados": {"msg": str(e)}})
            except Exception as e:
                self.incoming.put({"evento": "_erro", "dados": {"msg": str(e)}})

            self.ws = None
            self.conectado = False
            self.incoming.put({"evento": "_desconectado"})
            await asyncio.sleep(3)

    def _enviar(self, msg: dict):
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
            self.lbl_status.config(text="online", fg="#22c55e")
            self.btn_login.config(state="normal")
            self._log("Conectado ao servidor")

        elif evento == "_desconectado":
            self.lbl_status.config(text="offline", fg="#ef4444")
            self.btn_login.config(state="disabled")
            self._log("Desconectado - tentando reconectar em 3s...")
            if self.sessao_ativa:
                self._log("Conexao perdida durante sessao - retornando ao login")
                self._voltar_login()

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
                self.lbl_login_erro.config(text=dados.get("motivo", "Erro desconhecido"))

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

        elif evento == "mensagem_tela":
            texto = dados.get("texto", "")
            self._log(f"<- mensagem_tela: {texto}")
            self.root.after(0, lambda t=texto: self._exibir_mensagem_operador(t))

        elif evento == "ativar_manutencao":
            self._log("<- ativar_manutencao do operador")
            if not self.modo_manutencao_ativo:
                self.root.after(0, self._modo_manutencao)

        elif evento == "desativar_manutencao":
            self._log("<- desativar_manutencao do operador")
            if self.modo_manutencao_ativo:
                self.root.after(0, self._sair_modo_manutencao)

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

        elif evento == "parar_streaming":
            self._log("<- parar_streaming")
            self._streaming = False

        else:
            self._log(f"<- evento: {evento} | {dados}")

    # ── Captura de tela ──────────────────────────────────────────────────────
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

    def _avisar_saldo_baixo(self, restante_segundos: int):
        mins = restante_segundos // 60
        try:
            import tkinter.messagebox as mb
            mb.showwarning("Saldo acabando",
                           f"Atencao: restam {mins} minutos de saldo.\nProcure o operador para renovar.")
        except Exception:
            pass

    def _pausar_sessao(self):
        self._sessao_pausada = True
        self._log("Sessao pausada pelo operador")
        # Mostra overlay de pausa na janela (por cima do launcher)
        try:
            self._overlay_pausa = tk.Toplevel(self.root)
            self._overlay_pausa.overrideredirect(True)
            self._overlay_pausa.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            self._overlay_pausa.configure(bg="#0f1117")
            self._overlay_pausa.attributes("-topmost", True)
            tk.Label(self._overlay_pausa, text="SESSAO PAUSADA",
                     font=("Segoe UI", 22, "bold"), bg="#0f1117", fg="#f59e0b").pack(expand=True)
            tk.Label(self._overlay_pausa, text="Aguarde o operador retomar",
                     font=("Segoe UI", 12), bg="#0f1117", fg="#9ca3af").pack()
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
        # Roda em thread separada — NAO usar self._log() aqui (Tkinter nao e thread-safe)
        print("[streaming] iniciado")
        while self._streaming:
            try:
                b64 = self._tirar_screenshot()
                self._enviar({"evento": "tela_frame", "dados": {"imagem": b64}})
                print(f"[streaming] frame: {len(b64)} chars")
            except Exception as ex:
                print(f"[streaming] erro: {ex}")
            time.sleep(1.2)
        print("[streaming] encerrado")

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

    def _iniciar_sessao(self, dados):
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

        self.lbl_cliente.config(text=f"Bem-vindo(a), {self.cliente_nome}!")
        self.entry_login.delete(0, "end")
        self.entry_senha.delete(0, "end")
        self.lbl_login_erro.config(text="")

        self._montar_launcher()

        self.frame_log.pack_forget()
        self.frame_login.pack_forget()
        self.frame_sessao.pack(fill="both", expand=True)

        self.root.attributes("-fullscreen", False)
        self.root.attributes("-topmost", False)
        self.root.state("zoomed")
        self._permitir_minimizar(False)
        self.root.lift()
        self.root.focus_force()

        if self.whitelist_procs:
            self._log(f"Sessao iniciada - {self._fmt(self.tempo_total)} | "
                      f"whitelist: {len(self.whitelist_procs)} app(s)")
        else:
            self._log(f"Sessao iniciada - {self._fmt(self.tempo_total)} | sem restricao")

    def _montar_launcher(self):
        for widget in self.frame_launcher.winfo_children():
            widget.destroy()
        self._img_refs = []

        apps = [a for a in self.whitelist_apps if a.get("caminho")]

        if not apps:
            tk.Label(self.frame_launcher,
                     text="Nenhum app configurado com caminho de execucao.\n"
                          "Peca ao administrador para configurar a whitelist.",
                     font=self.f_small, fg=self.c_text2, bg=self.c_bg,
                     justify="center").pack(expand=True)
            return

        canvas = tk.Canvas(self.frame_launcher, bg=self.c_bg, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.frame_launcher, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=self.c_bg)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        COLUNAS = 4
        CARD_W, CARD_H = 160, 200
        IMG_W, IMG_H = 160, 140

        f_nome = tkfont.Font(family="Segoe UI", size=11)
        f_inicial = tkfont.Font(family="Segoe UI", size=36, weight="bold")

        for idx, app in enumerate(apps):
            row, col = divmod(idx, COLUNAS)

            card = tk.Frame(scroll_frame, bg="#1e2333", width=CARD_W, height=CARD_H, cursor="hand2")
            card.grid(row=row, column=col, padx=10, pady=10)
            card.grid_propagate(False)

            inicial = (app.get("nome", "?")[:1] or "?").upper()
            img_lbl = tk.Label(card, text=inicial, font=f_inicial, fg="white", bg="#1e2333")
            img_lbl.place(x=0, y=0, width=CARD_W, height=IMG_H)

            nome_raw = app.get("nome", "")
            nome_txt = (nome_raw[:18] + "...") if len(nome_raw) > 18 else nome_raw
            nome_lbl = tk.Label(card, text=nome_txt, font=f_nome,
                                 fg=self.c_text, bg="#1e2333", justify="center")
            nome_lbl.place(x=4, y=IMG_H + 4, width=CARD_W - 8, height=CARD_H - IMG_H - 8)

            for w in (card, img_lbl, nome_lbl):
                w.bind("<Button-1>", lambda e, a=app: self._abrir_app(a))

            ws = [card, img_lbl, nome_lbl]
            def _enter(e, widgets=ws):
                for w in widgets:
                    try: w.config(bg="#252b3b")
                    except Exception: pass
            def _leave(e, widgets=ws):
                for w in widgets:
                    try: w.config(bg="#1e2333")
                    except Exception: pass

            for w in (card, img_lbl, nome_lbl):
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)

            url = app.get("imagem_url")
            if url:
                def _load_img(u=url, lbl=img_lbl, refs=self._img_refs):
                    img = carregar_imagem_url(u, IMG_W, IMG_H)
                    if img:
                        refs.append(img)
                        lbl.after(0, lambda i=img, l=lbl: l.config(image=i, text="") if l.winfo_exists() else None)
                threading.Thread(target=_load_img, daemon=True).start()

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
            self.lbl_countdown.config(text=self._fmt(restante))

            if restante < 300:
                self.lbl_countdown.config(fg="#ef4444")
                # Aviso de 5 minutos — disparado uma unica vez pelo countdown
                if not self._aviso_5min_dado and restante > 0:
                    self._aviso_5min_dado = True
                    self.root.after(0, lambda r=int(restante): self._avisar_saldo_baixo(r))
            else:
                self.lbl_countdown.config(fg="#22c55e")

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

    def _countdown_reinicio(self, segundos):
        """Exibe contagem regressiva no launcher e reinicia ao zerar."""
        if segundos > 0:
            self.lbl_login_erro.config(
                text=f"Sessao encerrada. Reiniciando em {segundos}s...",
                fg="#f59e0b"
            )
            self.root.after(1000, self._countdown_reinicio, segundos - 1)
        else:
            self.lbl_login_erro.config(text="Reiniciando agora...", fg="#ef4444")
            self._log("Reiniciando o PC...")
            try:
                resultado = subprocess.run(
                    r"C:\Windows\System32\shutdown.exe /r /f /t 0",
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
        self.frame_log.pack_forget()
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
        self.frame_log.pack(fill="both", expand=False)

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
                 font=("Segoe UI", 10)).pack(pady=(16, 2))
        login_entry = tk.Entry(prompt, font=("Segoe UI", 11),
                               bg="#2A2B3D", fg="white", insertbackground="white")
        login_entry.pack(padx=24, fill="x")
        login_entry.focus()

        tk.Label(prompt, text="Senha:", bg="#1A1B26", fg="white",
                 font=("Segoe UI", 10)).pack(pady=(8, 2))
        senha_entry = tk.Entry(prompt, show="*", font=("Segoe UI", 11),
                               bg="#2A2B3D", fg="white", insertbackground="white")
        senha_entry.pack(padx=24, fill="x")

        def validar(event=None):
            login = login_entry.get().strip()
            senha = senha_entry.get()
            if not login or not senha:
                return
            btn.config(state="disabled", text="Verificando...")
            if self.conectado:
                # Valida pelo servidor
                self._enviar({"evento": "validar_manutencao", "login": login, "senha": senha})
            else:
                # Sem conexao: nao permite manutencao
                for w in prompt.winfo_children():
                    if isinstance(w, tk.Label) and getattr(w, "_is_erro", False):
                        w.config(text="Sem conexao com o servidor")
                        btn.config(state="normal", text="Entrar")
                        return
                lbl = tk.Label(prompt, text="Sem conexao com o servidor",
                               fg="#ef4444", bg="#1A1B26", font=("Segoe UI", 9))
                lbl._is_erro = True
                lbl.pack(pady=(2, 0))
                btn.config(state="normal", text="Entrar")

        btn = tk.Button(prompt, text="Entrar", command=validar,
                        bg="#4f46e5", fg="white", relief="flat",
                        font=("Segoe UI", 10))
        btn.pack(pady=12, padx=24, fill="x", ipady=6)

        senha_entry.bind("<Return>", validar)
        login_entry.bind("<Return>", lambda e: senha_entry.focus())
        prompt.bind("<Escape>", lambda e: prompt.destroy())

        def _on_close():
            self._prompt_manutencao = None
            prompt.destroy()
        prompt.protocol("WM_DELETE_WINDOW", _on_close)

    def _exibir_mensagem_operador(self, texto):
        """Mostra mensagem enviada pelo operador em uma janela modal."""
        popup = tk.Toplevel(self.root)
        popup.title("Mensagem do operador")
        popup.configure(bg="#1A1B26")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        # Centraliza
        popup.update_idletasks()
        w, h = 380, 160
        x = (popup.winfo_screenwidth() - w) // 2
        y = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{x}+{y}")
        popup.grab_set()

        tk.Label(popup, text="Mensagem do operador", font=("Arial", 11, "bold"),
                 fg="#f59e0b", bg="#1A1B26").pack(pady=(16, 4))
        tk.Label(popup, text=texto, font=("Arial", 10), fg="#e2e8f0",
                 bg="#1A1B26", wraplength=340, justify="center").pack(padx=16, pady=4)
        tk.Button(popup, text="OK", font=("Arial", 10, "bold"),
                  bg="#3b82f6", fg="white", relief="flat", padx=20, pady=6,
                  command=popup.destroy).pack(pady=(8, 0))
        self._log(f"Mensagem exibida: {texto}")

    def _modo_manutencao(self):
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
        self._permitir_minimizar(True)
        self._enviar({"evento": "status_estacao", "status": "manutencao"})
        self.frame_manutencao.pack(fill="x", before=self.header_frame)
        self._log("Modo manutencao ativado")

    def _sair_modo_manutencao(self):
        self.modo_manutencao_ativo = False
        self._permitir_minimizar(False)
        self.frame_manutencao.pack_forget()
        self._enviar({"evento": "status_estacao", "status": "livre"})
        self.frame_sessao.pack_forget()
        self.frame_login.pack(fill="both", expand=True)
        self.frame_log.pack(fill="both", expand=False)
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
        if not self.sessao_ativa and not self.modo_manutencao_ativo:
            for proc in psutil.process_iter(["name"]):
                try:
                    nome = (proc.info["name"] or "").lower()
                    if nome in PROCESSOS_BLOQUEADOS_NO_LOGIN:
                        proc.kill()
                        self._log(f"Bloqueado (tela de login): {nome}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        if self.sessao_ativa:
            pid_atual = os.getpid()
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    nome = (proc.info["name"] or "").lower()
                    pid = proc.info["pid"]

                    if pid == pid_atual or not nome:
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
                self._fechar_janelas_fora_da_whitelist(pid_atual)

        self.root.after(1000, self._verificar_processos)

    def _fechar_janelas_fora_da_whitelist(self, pid_atual):
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
            if nome in self.whitelist_procs:
                continue
            if nome in JANELAS_DE_PROCESSOS_SEGUROS:
                classe_app, descricao = JANELAS_DE_PROCESSOS_SEGUROS[nome]
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


def verificar_update(servidor_http: str) -> bool:
    """
    Consulta o servidor. Se houver versao mais nova, baixa e reinicia.
    Retorna True se reiniciou (processo novo no ar), False se nao havia update.
    servidor_http: URL HTTP, ex: http://192.168.0.10:8000
    """
    import json as _json
    import tkinter as _tk
    import tkinter.messagebox as _mb

    def _aviso(titulo, msg):
        """Mostra caixa de dialogo sem janela principal visivel."""
        r = _tk.Tk()
        r.withdraw()
        _mb.showinfo(titulo, msg, parent=r)
        r.destroy()

    try:
        url_versao = f"{servidor_http}/api/agente/versao"
        print(f"Verificando update em {url_versao}...")
        with abrir_url(url_versao, timeout=5) as r:
            dados = _json.loads(r.read())
        versao_servidor = dados.get("versao", "0.0.0")
        print(f"Versao local: {VERSAO} | Versao servidor: {versao_servidor}")

        if _versao_tuple(versao_servidor) <= _versao_tuple(VERSAO):
            print("Agente ja esta na versao mais recente.")
            return False

        # Avisa o usuario antes de atualizar
        _aviso(
            "Atualizacao disponivel",
            f"Nova versao encontrada: {versao_servidor}\nVersao atual: {VERSAO}\n\nO agente sera atualizado e reiniciado automaticamente."
        )

        print(f"Baixando versao {versao_servidor}...")
        url_download = f"{servidor_http}/api/agente/download"
        caminho_atual = os.path.abspath(__file__)
        caminho_novo = caminho_atual + ".novo"

        with abrir_url(url_download, timeout=30) as r:
            conteudo = r.read()

        with open(caminho_novo, "wb") as f:
            f.write(conteudo)

        os.replace(caminho_novo, caminho_atual)
        print(f"Agente atualizado para {versao_servidor}. Reiniciando...")
        import sys as _sys
        os.execv(_sys.executable, [_sys.executable] + _sys.argv)
        return True

    except Exception as e:
        print(f"Aviso: falha ao verificar update: {e}")
        return False


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

def salvar_cfg(servidor, estacao):
    """Persiste servidor e estacao em agente.cfg para a proxima inicializacao."""
    try:
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            f.write(f"# MatheCafe - configuracao da estacao (gerado automaticamente)\n")
            f.write(f"SERVIDOR={servidor}\n")
            f.write(f"ESTACAO={estacao}\n")
    except Exception as e:
        print(f"Aviso: nao foi possivel salvar agente.cfg: {e}")

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

    # Normaliza protocolo (aceita IP puro, http://, https://)
    servidor = servidor.strip().replace("https://", "wss://").replace("http://", "ws://")
    if not servidor.startswith("ws"):
        servidor = "ws://" + servidor

    # Salva para a proxima vez
    salvar_cfg(servidor, estacao)

    # Verifica update antes de abrir a janela
    # Converte ws:// -> http:// para a chamada REST
    servidor_http = servidor.replace("wss://", "https://").replace("ws://", "http://")
    verificar_update(servidor_http)  # reinicia automaticamente se houver update

    root = tk.Tk()
    # Erros dentro da interface: só no arquivo, sem janela (o agente segue rodando)
    root.report_callback_exception = lambda t, v, tb: registrar_erro(t, v, tb, mostrar=False)
    app = AgenteApp(root, servidor, estacao)
    root.mainloop()


if __name__ == "__main__":
    main()
