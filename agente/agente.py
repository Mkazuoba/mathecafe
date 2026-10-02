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
import urllib.request
import tkinter as tk
from tkinter import font as tkfont, scrolledtext

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
        with urllib.request.urlopen(url, timeout=5) as response:
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

        self.root.title(f"MatheCafe - {estacao}")
        self.root.geometry("420x480")
        self.root.configure(bg="#0f1117")
        self.root.resizable(False, False)

        # Impede fechar a janela durante a sessão
        self.root.protocol("WM_DELETE_WINDOW", self._tentar_fechar)

        self._build_ui()
        self._start_ws_thread()

        # Atalhos
        self.root.bind("<Escape>", self._tentar_esc)
        self.root.bind("<Control-Shift-M>", self._abrir_prompt_admin)
        self.root.bind("<Control-Shift-KeyPress-M>", self._abrir_prompt_admin)

        self.root.after(100, self._processar_fila)
        self.root.after(500, self._verificar_privilegios)
        self.root.after(1000, self._atualizar_countdown)
        self.root.after(3000, self._verificar_processos)

    # ── Controle de janela ────────────────────────────────────────────────────
    def _tentar_fechar(self):
        """Bloqueia fechamento durante sessão ativa fora do modo manutenção."""
        if self.sessao_ativa and not self.modo_manutencao_ativo:
            return  # ignora — não fecha
        self.root.destroy()

    def _tentar_esc(self, event=None):
        """ESC só sai da tela cheia fora de sessão ativa ou em manutenção."""
        if self.sessao_ativa and not self.modo_manutencao_ativo:
            return  # bloqueado durante sessão
        self.root.attributes("-fullscreen", False)

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
        tk.Label(header, text="MatheCafe", font=title_font, fg=accent, bg=bg2).pack(side="left", padx=14, pady=10)
        self.lbl_estacao = tk.Label(header, text=self.estacao, font=normal_font, fg=text2, bg=bg2)
        self.lbl_estacao.pack(side="left", padx=4)
        self.lbl_status = tk.Label(header, text="conectando...", font=small_font, fg="#f97316", bg=bg2)
        self.lbl_status.pack(side="right", padx=14)

        # ── Frame de login ──
        self.frame_login = tk.Frame(self.root, bg=bg)
        tk.Label(self.frame_login, text="Faca login para iniciar sua sessao",
                 font=normal_font, fg=text, bg=bg).pack(pady=(40, 20))

        tk.Label(self.frame_login, text="LOGIN", font=small_font, fg=text2, bg=bg).pack(anchor="w", padx=40)
        self.entry_login = tk.Entry(self.frame_login, font=normal_font, bg=bg3, fg=text,
                                     insertbackground=text, relief="flat")
        self.entry_login.pack(fill="x", padx=40, pady=(2, 12), ipady=6)

        tk.Label(self.frame_login, text="SENHA", font=small_font, fg=text2, bg=bg).pack(anchor="w", padx=40)
        self.entry_senha = tk.Entry(self.frame_login, font=normal_font, bg=bg3, fg=text,
                                     insertbackground=text, relief="flat", show="*")
        self.entry_senha.pack(fill="x", padx=40, pady=(2, 16), ipady=6)
        self.entry_senha.bind("<Return>", lambda e: self._fazer_login())

        self.btn_login = tk.Button(self.frame_login, text="Entrar", font=normal_font,
                                    bg=accent, fg="white", relief="flat", activebackground="#4f46e5",
                                    command=self._fazer_login, state="disabled")
        self.btn_login.pack(fill="x", padx=40, ipady=8)

        self.lbl_login_erro = tk.Label(self.frame_login, text="", font=small_font, fg="#ef4444", bg=bg)
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

        tk.Label(self.frame_sessao, text="Selecione um aplicativo para abrir",
                 font=small_font, fg=text2, bg=bg).pack(pady=(16, 8))

        self.frame_launcher = tk.Frame(self.frame_sessao, bg=bg)
        self.frame_launcher.pack(expand=True, fill="both", padx=20)

        self.btn_encerrar = tk.Button(self.frame_sessao, text="Encerrar sessao", font=normal_font,
                                       bg="#ef4444", fg="white", relief="flat", activebackground="#dc2626",
                                       command=self._encerrar_manual)
        self.btn_encerrar.pack(fill="x", padx=40, pady=20, ipady=8)

        self.frame_login.pack(fill="both", expand=True)

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

    def _log(self, msg):
        self.log.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ── WebSocket (thread separada) ──────────────────────────────────────────
    def _start_ws_thread(self):
        t = threading.Thread(target=self._thread_main, daemon=True)
        t.start()

    def _thread_main(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self):
        url = f"{self.servidor}/ws/estacao/{self.estacao}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    self.ws = ws
                    self.conectado = True
                    self.incoming.put({"evento": "_conectado"})
                    async for raw in ws:
                        self.incoming.put(json.loads(raw))
            except Exception as e:
                self.incoming.put({"evento": "_erro", "dados": {"msg": str(e)}})

            self.ws = None
            self.conectado = False
            self.incoming.put({"evento": "_desconectado"})
            await asyncio.sleep(3)

    def _enviar(self, msg: dict):
        if self.loop and self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(msg)), self.loop)
            self._log(f"-> enviado: {msg.get('evento')}")
        else:
            self._log("AVISO: nao conectado, mensagem nao enviada")

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

        elif evento == "_erro":
            self._log(f"Erro de conexao: {dados.get('msg')}")

        elif evento == "login_resultado":
            self._log(f"<- login_resultado: {dados}")
            if dados.get("ok"):
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

        else:
            self._log(f"<- evento: {evento} | {dados}")

    # ── Fluxo de sessão ───────────────────────────────────────────────────────
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
        if self.sessao_ativa:
            decorrido = time.time() - self.inicio_sessao
            restante = max(0, self.tempo_total - decorrido)
            self.lbl_countdown.config(text=self._fmt(restante))

            if restante < 300:
                self.lbl_countdown.config(fg="#ef4444")
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
        self._countdown_reinicio(30)

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
        self._encerrar_apps_do_cliente()

        self.sessao_ativa = False
        self.sessao_id = None
        self.whitelist_apps = []
        self.whitelist_procs = set()
        self._img_refs = []
        self._pids_pre_sessao = set()

        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass

        self.root.deiconify()  # garante que a janela nao fica minimizada
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.frame_sessao.pack_forget()
        self.frame_login.pack(fill="both", expand=True)
        self.frame_log.pack(fill="both", expand=False)

    # ── Manutenção admin ─────────────────────────────────────────────────────
    def _verificar_privilegios(self):
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                self._log("AVISO: rodando sem privilegios de admin.")
                self._log("  Bloqueio de processos pode nao funcionar.")
        except Exception:
            pass

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
        self._enviar({"evento": "status_estacao", "status": "manutencao"})
        self.frame_manutencao.pack(fill="x", before=self.header_frame)
        self._log("Modo manutencao ativado")

    def _sair_modo_manutencao(self):
        self.modo_manutencao_ativo = False
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
        if self.sessao_ativa:
            pid_atual = os.getpid()
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    nome = (proc.info["name"] or "").lower()
                    pid = proc.info["pid"]

                    if pid == pid_atual or not nome:
                        continue

                    # Processos que existiam antes da sessao: nunca toca
                    if pid in self._pids_pre_sessao:
                        continue

                    if nome in PROCESSOS_SEMPRE_BLOQUEADOS:
                        proc.kill()
                        self._log(f"Bloqueado (proibido): {nome}")
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

        self.root.after(3000, self._verificar_processos)


def main():
    parser = argparse.ArgumentParser(description="MatheCafe - Agente da Estacao")
    parser.add_argument("--servidor", required=True,
                         help="URL do servidor: ws://localhost:8000 ou wss://mathecafe.onrender.com")
    parser.add_argument("--estacao", required=True,
                         help="Nome da estacao cadastrada no painel, ex: PC-01")
    args = parser.parse_args()

    root = tk.Tk()
    app = AgenteApp(root, args.servidor, args.estacao)
    root.mainloop()


if __name__ == "__main__":
    main()
