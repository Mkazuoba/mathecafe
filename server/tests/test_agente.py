"""Regras do agente que já se perderam uma vez (agente.py reescrito a partir de
uma cópia antiga). O venv do servidor não tem psutil/websockets, então as
funções são tiradas do código-fonte em vez de importar o agente."""
import ast
import os

AGENTE = os.path.join(os.path.dirname(__file__), "..", "..", "agente", "agente.py")
DIST = os.path.join(os.path.dirname(__file__), "..", "agente_dist", "agente.py")


def _fonte(caminho=AGENTE):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _carregar(*nomes, metodos=()):
    """Executa só as funções/constantes pedidas do agente.py."""
    arvore = ast.parse(_fonte())
    corpo = []
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef) and no.name in nomes:
            corpo.append(no)
        elif isinstance(no, ast.Assign) and any(
                isinstance(t, ast.Tuple) and any(getattr(e, "id", "").startswith("VK_") for e in t.elts)
                for t in no.targets):
            corpo.append(no)
        elif isinstance(no, ast.ClassDef) and no.name == "AgenteApp":
            corpo += [m for m in no.body if isinstance(m, ast.FunctionDef) and m.name in metodos]
    ns = {"urllib": __import__("urllib.parse")}
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    return ns


def test_servidor_interno_conecta_sem_proxy():
    # Com o proxy do Windows o usuario "cliente" nunca chegava ao 10.26.31.99
    ns = _carregar("servidor_na_rede_local")
    local = ns["servidor_na_rede_local"]
    assert local("ws://10.26.31.99:8000/ws/estacao/PC-01")
    assert local("ws://192.168.0.10:8000")
    assert local("ws://localhost:8000")
    assert local("ws://SERVIDOR:8000")
    assert not local("wss://mathecafe.onrender.com/ws/estacao/PC-01")
    src = _fonte()
    assert "proxy=proxy" in src  # websockets.connect
    assert "urllib.request.urlopen(url_versao" not in src  # auto-update tambem sem proxy


def test_estacao_com_espaco_e_nao_cadastrada():
    src = _fonte()
    assert "urllib.parse.quote(self.estacao)" in src
    assert "4004" in src


def test_whitelist_confere_janelas_de_processos_antigos():
    # Edge aberto em segundo plano antes do login abria janelas sem criar
    # processo novo e escapava da whitelist; Explorador e o explorer.exe
    src = _fonte()
    verificar = src[src.index("def _verificar_processos"):src.index("def _fechar_janelas_fora_da_whitelist")]
    assert "self._fechar_janelas_fora_da_whitelist(pid_atual)" in verificar
    # proibidos (cmd, regedit...) caem mesmo se ja existiam antes da sessao
    assert verificar.index("PROCESSOS_SEMPRE_BLOQUEADOS") < verificar.index("_pids_pre_sessao")
    assert '"CabinetWClass"' in src
    # Configurações, Calculadora e apps da Loja moram no ApplicationFrameHost
    # (processo seguro): a janela precisa ser fechada
    assert "JANELAS_DE_PROCESSOS_SEGUROS" in src[src.index("def _fechar_janelas_fora_da_whitelist"):]
    assert '"ApplicationFrameWindow"' in src[src.index("JANELAS_DE_PROCESSOS_SEGUROS = {"):src.index("# ── Janelas abertas")]


class _Estado:
    modo_manutencao_ativo = False
    sessao_ativa = False


def test_atalhos_bloqueados_fora_da_manutencao():
    ns = _carregar(metodos=("_tecla_bloqueada", "_tentar_fechar", "_tentar_esc"))
    bloq = ns["_tecla_bloqueada"]
    esc, tab, f4, win = ns["VK_ESCAPE"], ns["VK_TAB"], ns["VK_F4"], ns["VK_LWIN"]
    e = _Estado()

    # Tela de login: nada sai do agente
    assert bloq(e, win, False, False, False)
    assert bloq(e, tab, True, False, False)
    assert bloq(e, f4, True, False, False)
    assert bloq(e, esc, False, True, False)
    assert bloq(e, esc, False, True, True)
    assert not bloq(e, 0x41, False, False, False)  # digitar o login

    # Sessão: alterna entre os apps (Alt+Tab, Alt+F4), mas sem Iniciar,
    # Win+R/Win+E nem Gerenciador de Tarefas (na 1.6.1 tudo isso abria)
    e.sessao_ativa = True
    assert not bloq(e, tab, True, False, False)
    assert not bloq(e, f4, True, False, False)
    assert bloq(e, win, False, False, False)
    assert bloq(e, ns["VK_RWIN"], False, False, False)
    assert bloq(e, esc, False, True, False)
    assert bloq(e, esc, False, True, True)
    assert not bloq(e, esc, False, False, False)  # Esc dentro dos apps

    # Manutenção: tudo liberado
    e.modo_manutencao_ativo = True
    assert not bloq(e, esc, False, True, True)


def test_esc_e_fechar_so_na_manutencao():
    ns = _carregar(metodos=("_tentar_fechar", "_tentar_esc"))

    class Root:
        fechou = False
        atributos = {}

        def destroy(self):
            self.fechou = True

        def attributes(self, nome, valor):
            self.atributos[nome] = valor

    e = _Estado()
    e.root = Root()
    for sessao in (False, True):
        e.sessao_ativa = sessao
        ns["_tentar_fechar"](e)
        ns["_tentar_esc"](e)
        assert not e.root.fechou and not e.root.atributos

    e.modo_manutencao_ativo = True
    ns["_tentar_fechar"](e)
    ns["_tentar_esc"](e)
    assert e.root.fechou and e.root.atributos == {"-fullscreen": False}


def test_agente_dist_igual_ao_agente():
    # O auto-update distribui server/agente_dist: precisa ser o mesmo arquivo
    assert _fonte(DIST).replace("\r\n", "\n") == _fonte().replace("\r\n", "\n")


def test_minimizar_so_na_manutencao():
    # Na 1.6.2 o cliente minimizava o agente pelo botao da barra de titulo
    ns = _carregar(metodos=("_ao_minimizar",))

    class Root:
        def __init__(self):
            self.estado = "iconic"
            self.agendado = []

        def state(self, valor=None):
            if valor is None:
                return self.estado
            self.estado = valor

        def deiconify(self):
            self.estado = "normal"

        def after(self, ms, func, *args):
            self.agendado.append(func)

    e = _Estado()
    e.root = Root()
    e.sessao_ativa = True
    e._restaurar_janela = lambda: e.root.deiconify()
    ns["_ao_minimizar"](e)
    for f in e.root.agendado:
        f()
    assert e.root.estado != "iconic"

    e.modo_manutencao_ativo = True
    e.root = Root()
    ns["_ao_minimizar"](e)
    assert e.root.estado == "iconic" and not e.root.agendado

    src = _fonte()
    assert 'self.root.bind("<Unmap>", self._ao_minimizar)' in src


def test_streaming_nao_mexe_no_tkinter_fora_da_thread_principal():
    # _enviar e _log escrevem no log da janela: chamados pela thread do
    # streaming, o Tkinter pode travar (e o log enchia a cada 1,2s)
    src = _fonte()
    loop = src[src.index("def _loop_streaming"):]
    loop = loop[:loop.index("\n    def ", 1)]
    assert "self._enviar(" not in loop and "self._log(" not in loop
