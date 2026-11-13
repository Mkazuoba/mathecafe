"""MatheCafe - simulador da tela do cliente (so para desenvolver o visual).

Roda o agente de verdade numa janela comum DESTE computador, ligado ao servidor
de teste, como o servidor de teste faz com o painel. NAO vai para as estacoes
(o instalar.bat nao copia este arquivo).

O que o agente faz numa estacao e aqui fica DESLIGADO (para nao mexer no seu PC):
- tela cheia e "sempre por cima"     -> janela comum de 1366x768
- bloqueio de teclas (Win, Alt+Tab)  -> desligado
- esconder a barra do Windows        -> desligado
- fechar programas fora da lista     -> desligado
- esvaziar Downloads / vigia do Explorador -> desligado
- desligar ou reiniciar o PC         -> so mostra na tela
- atualizar o agente pelo painel     -> ignorado (nao sobrescreve o agente.py)

Uso (pasta agente/):  simular.bat   ou   python simular.py [--servidor ws://127.0.0.1:8011]
A configuracao fica em agente_simulacao.cfg (o agente.cfg de verdade nao e tocado).
A estacao aparece no painel de teste em Mapa -> Novas estacoes (aprove uma vez).
"""
import argparse
import importlib.util
import os
import sys
import tkinter as tk

AQUI = os.path.dirname(os.path.abspath(__file__))

args = argparse.ArgumentParser(description="MatheCafe - simulador da tela do cliente")
args.add_argument("--servidor", default="ws://127.0.0.1:8011", help="servidor de TESTE (padrao: ws://127.0.0.1:8011)")
args.add_argument("--estacao", default="SIMULADOR", help="nome da estacao simulada")
args.add_argument("--piso", default=None, help="id do piso (opcional)")
args.add_argument("--tamanho", default="1366x768", help="tamanho da janela (padrao 1366x768)")
args.add_argument("--navegador", action="store_true",
                  help="em vez da janela, mostra a tela numa pagina (http://127.0.0.1:PORTA), com mouse e teclado")
args.add_argument("--porta", type=int, default=5190, help="porta da pagina do --navegador (padrao 5190)")
opcoes = args.parse_args()
LARGURA, ALTURA = (int(v) for v in opcoes.tamanho.lower().split("x"))
# no --navegador a "tela" do cliente fica no canto do monitor, mas ESCONDIDA pelo
# DWM ("cloak"): o Windows continua desenhando (o espelho captura), ela nao aparece
# e nao recebe cliques. Fora do monitor ou transparente, o Windows nao a desenha.
ORIGEM = (0, 0) if opcoes.navegador else (40, 40)
ALFA_PEDIDO = {}  # a transparencia que o agente pediu, por janela (o espelho aplica)

# o agente de verdade, carregado como modulo (nao roda o main dele sozinho)
spec = importlib.util.spec_from_file_location("agente", os.path.join(AQUI, "agente.py"))
ag = importlib.util.module_from_spec(spec)
sys.modules["agente"] = ag
spec.loader.exec_module(ag)

# configuracao separada
ag.CFG_FILE = os.path.join(AQUI, "agente_simulacao.cfg")
ag.gravar_cfg(SERVIDOR=ag.normalizar_servidor(opcoes.servidor), ESTACAO=opcoes.estacao, PISO=opcoes.piso)


def _nada(*_a, **_k):
    return None


# ---- o que mexeria no Windows: desligado -----------------------------------
class SemBloqueioDeTeclas:
    """No lugar do BloqueioTeclado: nao instala o hook de teclado."""

    def __init__(self, *_a, **_k):
        pass

    def __getattr__(self, _nome):
        return _nada


ag.BloqueioTeclado = SemBloqueioDeTeclas
ag.barra_do_windows = _nada                    # nao esconde a barra do Windows
ag.barra_do_windows_visivel = lambda: True
ag.iniciar_vigia = _nada                       # sem vigia prendendo o Explorador em Downloads
ag.limpar_pasta = _nada                        # nao apaga nada

App = ag.AgenteApp
App._verificar_processos = _nada               # nao fecha programas fora da lista
App._fechar_janelas_fora_da_whitelist = _nada
App._encerrar_apps_do_cliente = _nada
App._limpar_downloads = _nada


def _sem_desligar(self, segundos, desligar=False):
    verbo = "desligaria" if desligar else "reiniciaria"
    self.lbl_login_erro.config(text=f"Simulador: aqui o PC {verbo}.", fg="#f59e0b")
    self._log(f"Simulador: o PC {verbo} (ignorado)")


App._countdown_reinicio = _sem_desligar


def _sem_atualizar(self, *_a, **_k):
    self._log("Simulador: atualizacao do agente ignorada (rode o simulador de novo para ver a versao nova)")


App._aplicar_atualizacao = _sem_atualizar

# ---- janela comum, em vez de tela cheia por cima de tudo -------------------
_attributes = tk.Wm.wm_attributes


def _attributes_sem_tela_cheia(self, *a):
    pares = list(a)
    if len(pares) >= 2 and pares[0] in ("-fullscreen", "-topmost") and pares[1] not in (False, 0, "0"):
        return None
    if opcoes.navegador and pares and pares[0] == "-alpha":
        if len(pares) == 1:
            return ALFA_PEDIDO.get(str(self), 1.0)
        ALFA_PEDIDO[str(self)] = float(pares[1])  # o espelho aplica; a janela fica opaca
        return None
    return _attributes(self, *a)


def _invisivel(janela):
    """Escondida pelo DWM (cloak), sem receber cliques e fora do Alt+Tab. So no --navegador."""
    def esconder():
        try:
            import ctypes
            hwnd = int(janela.wm_frame(), 16)
            sim = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 13, ctypes.byref(sim), 4)  # DWMWA_CLOAK
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x20 | 0x80)  # TRANSPARENT | TOOLWINDOW
        except Exception as e:
            print("simulador: esconder a janela", e)
    esconder()
    janela.after_idle(esconder)


tk.Wm.wm_attributes = tk.Wm.attributes = _attributes_sem_tela_cheia

_tk_init = tk.Tk.__init__


def _tk_janela(self, *a, **k):
    _tk_init(self, *a, **k)
    self.title(f"MatheCafé - simulador ({opcoes.estacao})")
    _geometry(self, f"{LARGURA}x{ALTURA}+{ORIGEM[0]}+{ORIGEM[1]}")
    if opcoes.navegador:
        self.overrideredirect(True)  # sem moldura nem botao na barra do Windows
        _invisivel(self)
        from simulador_navegador import Espelho
        self.after(800, lambda: Espelho(self, ORIGEM, (LARGURA, ALTURA), opcoes.porta))


_geometry = tk.Wm.wm_geometry
tk.Tk.__init__ = _tk_janela

if opcoes.navegador:
    # a "tela" simulada: as janelinhas (dock, notificacoes, avisos) se posicionam
    # nela, relativas a ORIGEM, e o tamanho da tela e o da janela
    import re as _re

    def _geometry_na_tela(self, novo=None):
        if novo and not isinstance(self, tk.Tk):
            m = _re.match(r"^(\d+x\d+)?([+-]-?\d+)([+-]-?\d+)$", str(novo))
            if m:
                x, y = int(m.group(2)) + ORIGEM[0], int(m.group(3)) + ORIGEM[1]
                novo = f"{m.group(1) or ''}+{x}+{y}"
        return _geometry(self, novo)

    tk.Wm.wm_geometry = tk.Wm.geometry = _geometry_na_tela

    _top_init = tk.Toplevel.__init__

    def _toplevel_invisivel(self, *a, **k):
        _top_init(self, *a, **k)
        _invisivel(self)

    tk.Toplevel.__init__ = _toplevel_invisivel
    # nunca tira o foco do seu programa (a janela e invisivel): so o foco interno do Tk
    tk.Misc.focus_force = tk.Misc.focus_set
    tk.Misc.winfo_screenwidth = lambda self: LARGURA
    tk.Misc.winfo_screenheight = lambda self: ALTURA
    ag.area_da_barra_do_windows = lambda: None

# o X da janela fecha o simulador (na estacao o agente nao deixa fechar)
_protocol = tk.Wm.wm_protocol


def _protocol_fechar(self, name=None, func=None):
    if name == "WM_DELETE_WINDOW" and isinstance(self, tk.Tk):
        func = lambda: os._exit(0)
    return _protocol(self, name, func)


tk.Wm.wm_protocol = tk.Wm.protocol = _protocol_fechar

if __name__ == "__main__":
    print("Simulador da tela do cliente:", opcoes.servidor, opcoes.estacao)
    sys.argv = [sys.argv[0]]  # o main do agente le o agente_simulacao.cfg
    ag.main()
