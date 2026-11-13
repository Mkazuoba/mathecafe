"""Espelho do simulador no navegador (simular.py --navegador).

A "tela" do cliente (a janela do agente e as janelinhas dela: dock, notificacoes,
avisos) fica fora da area visivel do Windows; este modulo:
- monta uma imagem dessa tela a cada ~200 ms (PrintWindow de cada janela, na
  posicao certa, com a cor transparente do dock respeitada);
- serve uma pagina em http://127.0.0.1:PORTA com a imagem ao vivo (MJPEG);
- recebe do navegador os cliques, a rodinha e as teclas e entrega aos widgets
  certos (event_generate no Tk), na thread do Tk.
Nada aparece na tela de verdade.
"""
import ctypes
import io
import json
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

_u32 = ctypes.windll.user32
_gdi = ctypes.windll.gdi32


class _BMI(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def capturar_janela(hwnd, w, h):
    """Imagem da janela (mesmo fora da tela), pelo PrintWindow."""
    if w <= 0 or h <= 0:
        return None
    hdc = _u32.GetWindowDC(hwnd)
    mdc = _gdi.CreateCompatibleDC(hdc)
    bmp = _gdi.CreateCompatibleBitmap(hdc, w, h)
    _gdi.SelectObject(mdc, bmp)
    _u32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT
    bi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    _gdi.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).copy()
    _gdi.DeleteObject(bmp)
    _gdi.DeleteDC(mdc)
    _u32.ReleaseDC(hwnd, hdc)
    return img


def _cor_hex(cor):
    cor = (cor or "").strip()
    if cor.startswith("#") and len(cor) == 7:
        return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))
    return None


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>MatheCafé - simulador da tela do cliente</title>
<style>
 html,body{margin:0;height:100%;background:#0b0b0d;color:#a1a1aa;font:12px system-ui,sans-serif}
#tela{display:block;margin:0 auto;max-width:100%;max-height:100%;cursor:default;outline:none}
</style></head><body>
<img id="tela" src="/video" draggable="false" alt="tela do cliente">
<textarea id="digitar" aria-label="teclado da tela simulada" autocomplete="off" spellcheck="false"
 style="position:fixed;left:-9999px;top:0;width:10px;height:10px;opacity:0"></textarea>
<script>
const tela=document.getElementById('tela');
function ponto(ev){const r=tela.getBoundingClientRect();return{x:Math.round((ev.clientX-r.left)*tela.naturalWidth/r.width),y:Math.round((ev.clientY-r.top)*tela.naturalHeight/r.height)}}
function mandar(d){fetch('/evento',{method:'POST',body:JSON.stringify(d)}).catch(()=>{})}
const digitar=document.getElementById('digitar');
tela.addEventListener('mousedown',ev=>{ev.preventDefault();digitar.focus();mandar({tipo:'apertar',botao:ev.button,...ponto(ev)})});
// texto (com acento e ç) chega pelo campo escondido; as teclas especiais pelo keydown
digitar.addEventListener('input',ev=>{const t=digitar.value;digitar.value='';if(t)mandar({tipo:'texto',texto:t})});
tela.addEventListener('mouseup',ev=>{ev.preventDefault();mandar({tipo:'soltar',botao:ev.button,...ponto(ev)})});
tela.addEventListener('contextmenu',ev=>ev.preventDefault());
let ultimo=0;tela.addEventListener('mousemove',ev=>{const t=Date.now();if(t-ultimo<60)return;ultimo=t;mandar({tipo:'mover',...ponto(ev)})});
tela.addEventListener('wheel',ev=>{ev.preventDefault();mandar({tipo:'rodinha',delta:ev.deltaY>0?-120:120,...ponto(ev)})},{passive:false});
digitar.addEventListener('keydown',ev=>{if(ev.key.length===1&&!ev.ctrlKey&&!ev.altKey)return;ev.preventDefault();mandar({tipo:'tecla',key:ev.key,ctrl:ev.ctrlKey,shift:ev.shiftKey,alt:ev.altKey})});
</script></body></html>"""

TECLAS = {"Enter": "Return", "Backspace": "BackSpace", "Tab": "Tab", "Escape": "Escape", "Delete": "Delete",
          "ArrowLeft": "Left", "ArrowRight": "Right", "ArrowUp": "Up", "ArrowDown": "Down",
          "Home": "Home", "End": "End", " ": "space"}


class Espelho:
    def __init__(self, root, origem, tamanho, porta):
        self.root, (self.x0, self.y0), (self.w, self.h) = root, origem, tamanho
        self.porta = porta
        self.jpeg = b""
        self.eventos = queue.Queue()
        self._sob_mouse = None
        self._foco = None  # campo clicado por ultimo (o Tk nao tem foco de verdade: a janela e invisivel)
        self.root.after(500, self._quadro)
        self.root.after(50, self._processar)
        threading.Thread(target=self._servir, daemon=True).start()

    # ---- janelas da "tela", de baixo para cima ----
    def _janelas(self):
        tops = [self.root]
        pilha = list(self.root.winfo_children())
        while pilha:
            w = pilha.pop()
            if isinstance(w, tk.Toplevel):
                tops.append(w)
            pilha.extend(w.winfo_children())
        vis = []
        for t in tops:
            try:
                if t.winfo_ismapped() and t.state() != "withdrawn":
                    vis.append(t)
            except tk.TclError:
                pass
        return vis  # a raiz primeiro; as outras por cima

    def _quadro(self):
        try:
            tela = Image.new("RGB", (self.w, self.h), (9, 9, 11))
            for t in self._janelas():
                hwnd = int(t.wm_frame(), 16) if t is not self.root else int(self.root.wm_frame(), 16)
                img = capturar_janela(hwnd, t.winfo_width(), t.winfo_height()) if t is not self.root else \
                    capturar_janela(hwnd, self.w, self.h)
                if img is None:
                    continue
                mascara = None
                chave = _cor_hex(str(t.wm_attributes("-transparentcolor") or ""))
                if chave:
                    dados = img.getdata()
                    mascara = Image.new("L", img.size)
                    mascara.putdata([0 if p == chave else 255 for p in dados])
                alfa = float(t.wm_attributes("-alpha") or 1.0)  # o que o agente pediu (simular.py)
                if alfa < 1.0:
                    base = mascara or Image.new("L", img.size, 255)
                    mascara = base.point(lambda v: int(v * alfa))
                tela.paste(img, (t.winfo_rootx() - self.x0, t.winfo_rooty() - self.y0), mascara)
            saida = io.BytesIO()
            tela.save(saida, "JPEG", quality=85)
            self.jpeg = saida.getvalue()
        except Exception as ex:  # nunca derruba o simulador
            print("espelho:", ex)
        self.root.after(50, self._quadro)  # ~20 quadros/s: dá para ver as animações

    # ---- entrada vinda do navegador ----
    def _widget_em(self, x, y):
        """O widget mais de cima e mais fundo no ponto (coordenadas da tela simulada)."""
        sx, sy = self.x0 + x, self.y0 + y
        achado = None
        for t in self._janelas():  # as de cima por ultimo: ganham
            alvo = self._no_ponto(t, sx, sy)
            if alvo is not None:
                achado = alvo
        return achado

    def _no_ponto(self, w, sx, sy):
        try:
            if not w.winfo_ismapped():
                return None
            x, y = w.winfo_rootx(), w.winfo_rooty()
            if not (x <= sx < x + w.winfo_width() and y <= sy < y + w.winfo_height()):
                return None
        except tk.TclError:
            return None
        for filho in reversed(w.winfo_children()):  # os criados por ultimo ficam por cima
            if isinstance(filho, tk.Toplevel):
                continue
            achado = self._no_ponto(filho, sx, sy)
            if achado is not None:
                return achado
        return w

    def _processar(self):
        try:
            while True:
                self._entregar(self.eventos.get_nowait())
        except queue.Empty:
            pass
        except Exception as ex:
            print("espelho (evento):", ex)
        self.root.after(30, self._processar)

    def _entregar(self, ev):
        tipo = ev.get("tipo")
        if tipo == "tecla":
            return self._tecla(ev)
        if tipo == "texto":
            for ch in ev.get("texto", ""):
                self._tecla({"key": ch})
            return
        w = self._widget_em(ev.get("x", 0), ev.get("y", 0))
        if w is None:
            return
        lx = self.x0 + ev["x"] - w.winfo_rootx()
        ly = self.y0 + ev["y"] - w.winfo_rooty()
        if w is not self._sob_mouse:
            if self._sob_mouse is not None:
                try:
                    self._sob_mouse.event_generate("<Leave>", x=0, y=0)
                except tk.TclError:
                    pass
            w.event_generate("<Enter>", x=lx, y=ly)
            self._sob_mouse = w
        w.event_generate("<Motion>", x=lx, y=ly)
        botao = 3 if ev.get("botao") == 2 else 1
        if tipo == "apertar":
            campo = w if isinstance(w, (tk.Entry, tk.Text)) else self._campo_dentro(w)
            if campo is not None:
                campo.focus_set()
            self._foco = campo
            w.event_generate(f"<ButtonPress-{botao}>", x=lx, y=ly)
        elif tipo == "soltar":
            w.event_generate(f"<ButtonRelease-{botao}>", x=lx, y=ly)
        elif tipo == "rodinha":
            w.event_generate("<MouseWheel>", x=lx, y=ly, delta=int(ev.get("delta", 0)))

    @staticmethod
    def _campo_dentro(w):
        """O campo de texto dentro do que foi clicado (a moldura em volta do campo)."""
        pilha = list(w.winfo_children())
        while pilha:
            f = pilha.pop(0)
            if isinstance(f, (tk.Entry, tk.Text)) and f.winfo_ismapped():
                return f
            pilha.extend(f.winfo_children())
        return None

    def _tecla(self, ev):
        alvo = self._foco if (self._foco is not None and self._foco.winfo_exists()) else (self.root.focus_get() or self.root)
        key = ev.get("key", "")
        mods = ("Control-" if ev.get("ctrl") else "") + ("Shift-" if ev.get("shift") else "") + \
               ("Alt-" if ev.get("alt") else "")
        if len(key) == 1 and not ev.get("ctrl") and not ev.get("alt"):
            # texto: direto no campo (o event_generate nao traz o caractere)
            if isinstance(alvo, tk.Entry):
                if alvo.selection_present():
                    alvo.delete("sel.first", "sel.last")
                alvo.insert("insert", key)
                return
            if isinstance(alvo, tk.Text):
                alvo.insert("insert", key)
                return
        sym = TECLAS.get(key, key if len(key) > 1 else (key.upper() if ev.get("shift") else key))
        try:
            alvo.event_generate(f"<{mods}KeyPress-{sym}>")
        except tk.TclError:
            pass

    # ---- servidor http ----
    def _servir(self):
        espelho = self

        class Pedido(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/video"):
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    try:
                        enviado = None
                        while True:
                            q = espelho.jpeg
                            if q and q is not enviado:  # so quadros novos
                                self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                                 + str(len(q)).encode() + b"\r\n\r\n" + q + b"\r\n")
                                enviado = q
                            time.sleep(0.03)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return
                corpo = PAGINA.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    espelho.eventos.put(json.loads(self.rfile.read(n) or b"{}"))
                except ValueError:
                    pass
                self.send_response(204)
                self.end_headers()

        ThreadingHTTPServer(("127.0.0.1", self.porta), Pedido).serve_forever()
