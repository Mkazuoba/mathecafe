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
    assert "url_da_estacao(self.servidor, self.estacao, self.identificador, piso_da_instalacao())" in src
    assert "4004" in src


def test_url_leva_o_id_da_instalacao():
    # 1.14: o servidor reconhece o PC pelo id; PC novo aparece em "Novas estacoes"
    url = _carregar("url_da_estacao")["url_da_estacao"]
    assert url("ws://10.0.0.1:8000", "PC 01", "abc123") == "ws://10.0.0.1:8000/ws/estacao/PC%2001?id=abc123"
    assert url("ws://10.0.0.1:8000", "PC-01") == "ws://10.0.0.1:8000/ws/estacao/PC-01"


def test_url_leva_o_piso_escolhido_na_instalacao():
    # 1.20 (6.18): o instalador grava PISO= no agente.cfg; o servidor poe o PC
    # na estacao com esse nome naquele piso (o mesmo nome pode estar nos dois)
    url = _carregar("url_da_estacao")["url_da_estacao"]
    assert url("ws://s:8000", "AD-01", "abc", "2") == "ws://s:8000/ws/estacao/AD-01?id=abc&piso=2"
    assert url("ws://s:8000", "AD-01", "abc", None) == "ws://s:8000/ws/estacao/AD-01?id=abc"
    ns = _carregar("piso_da_instalacao")
    ns["carregar_cfg"] = lambda: {"PISO": " 2 "}
    assert ns["piso_da_instalacao"]() == "2"
    ns["carregar_cfg"] = lambda: {"PISO": "Infantil"}  # so o id vale
    assert ns["piso_da_instalacao"]() is None
    ns["carregar_cfg"] = lambda: {}
    assert ns["piso_da_instalacao"]() is None
    src = _fonte()
    assert "url_da_estacao(servidor, estacao, identificador_da_estacao(), piso_da_instalacao())" in src


def test_id_e_criado_uma_vez_e_guardado():
    guardado = {}
    ns = _carregar("identificador_da_estacao")
    ns["carregar_cfg"] = lambda: dict(guardado)
    ns["gravar_cfg"] = lambda **v: guardado.update(v)
    ns["uuid"] = __import__("uuid")
    primeiro = ns["identificador_da_estacao"]()
    assert guardado["ID"] == primeiro and len(primeiro) == 32
    assert ns["identificador_da_estacao"]() == primeiro


def test_renomeado_no_painel_grava_o_nome_novo():
    src = _fonte()
    aplicar = src[src.index("def _aplicar_info_estacao"):src.index("def _tirar_screenshot")]
    assert "gravar_cfg(ESTACAO=nome)" in aplicar
    assert "self.estacao = nome" in aplicar
    # a URL e refeita a cada reconexao (dentro do laco)
    laco = src[src.index("async def _ws_loop"):src.index("def _enviar(self")]
    assert laco.index("while True:") < laco.index("url = url_da_estacao(")


def test_whitelist_confere_janelas_de_processos_antigos():
    # Edge aberto em segundo plano antes do login abria janelas sem criar
    # processo novo e escapava da whitelist; Explorador e o explorer.exe
    src = _fonte()
    verificar = src[src.index("def _verificar_processos"):src.index("def _fechar_janelas_fora_da_whitelist")]
    assert "self._fechar_janelas_fora_da_whitelist(pid_atual, self.whitelist_procs)" in verificar
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
    barra = []
    ns["barra_do_windows"] = barra.append  # fechar devolve a barra do Windows

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
    assert barra == [True]


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


def test_tela_do_agente_abre_antes_de_tudo():
    # Na inicializacao do Windows o cliente abria apps antes do agente: a
    # tarefa esperava 5s e o agente so abria a janela depois de consultar
    # a atualizacao (ate 5s)
    src = _fonte()
    main = src[src.index("def main():"):]
    assert main.index("root = tk.Tk()") < main.index("checar_atualizacao")
    assert "verificar_update(" not in main
    tarefa = open(os.path.join(os.path.dirname(AGENTE), "registrar_tarefa.ps1"), encoding="utf-8").read()
    assert "PT5S" not in tarefa


def test_tela_de_login_fecha_o_que_abriram_antes():
    # O que fosse aberto antes do agente continuava rodando atras da tela de
    # login (ali so o Gerenciador de Tarefas era fechado)
    src = _fonte()
    verificar = src[src.index("def _verificar_processos"):src.index("def _fechar_janelas_fora_da_whitelist")]
    login = verificar[:verificar.index("if self.sessao_ativa:")]
    assert "PROCESSOS_SEMPRE_BLOQUEADOS" in login
    assert "self._fechar_janelas_fora_da_whitelist(pid_atual, set())" in login
    assert 'self.root.after(500, self._verificar_processos)' in src


def test_janela_da_sessao_nao_diminui():
    # 1.6.5: o botao de restaurar deixava diminuir o agente; 1.6.6: ainda dava
    # para arrastar e a barra do Windows sumia. Na 1.7.0 a sessao e tela cheia
    # (sem barra de titulo) com a barra propria do MatheCafe
    ns = _carregar(metodos=("_ao_redimensionar",))

    class Root:
        def __init__(self, cheia):
            self.cheia = cheia
            self.agendado = []

        def attributes(self, nome):
            assert nome == "-fullscreen"
            return self.cheia

        def after(self, ms, func, *args):
            self.agendado.append(func)

    class Evento:
        pass

    e = _Estado()
    e._restaurar_janela = lambda: None
    e.sessao_ativa = True
    e.root = Root(False)
    ev = Evento()
    ev.widget = e.root
    ns["_ao_redimensionar"](e, ev)
    assert e.root.agendado == [e._restaurar_janela]

    # eventos dos widgets de dentro da janela nao contam
    e.root = Root(False)
    outro = Evento()
    outro.widget = object()
    ns["_ao_redimensionar"](e, outro)
    assert not e.root.agendado

    # em tela cheia, na tela de login ou na manutencao: deixa como esta
    for sessao, manutencao, cheia in ((True, False, True), (False, False, False), (True, True, False)):
        e.sessao_ativa, e.modo_manutencao_ativo = sessao, manutencao
        e.root = Root(cheia)
        ev.widget = e.root
        ns["_ao_redimensionar"](e, ev)
        assert not e.root.agendado

    src = _fonte()
    assert 'self.root.bind("<Configure>", self._ao_redimensionar)' in src
    inicio = src[src.index("def _iniciar_sessao"):src.index("def _montar_launcher")]
    assert '"zoomed"' not in inicio and 'self.root.attributes("-fullscreen", True)' in inicio


def test_barra_propria_substitui_a_do_windows():
    src = _fonte()
    inicio = src[src.index("def _iniciar_sessao"):src.index("def _montar_launcher")]
    assert "self.barra.mostrar()" in inicio
    voltar = src[src.index("def _voltar_login"):src.index("def _countdown_encerramento")]
    assert "self.barra.esconder()" in voltar
    manutencao = src[src.index("def _modo_manutencao"):src.index("def _sair_modo_manutencao")]
    assert "self.barra.esconder()" in manutencao
    # se o agente fechar, a barra do Windows volta
    assert "atexit.register(barra_do_windows, True)" in src
    # na pausa a barra some (senao o cliente usaria os apps pausado)
    manter = src[src.index("    def manter(self):"):]
    assert "self.app._sessao_pausada" in manter[:manter.index("\n    def ", 1)]
    # o que aparece na barra so pode ser app liberado
    janelas = src[src.index("def _janelas_dos_apps"):]
    janelas = janelas[:janelas.index("\n    def ", 1)]
    assert "self.whitelist_procs" in janelas


def test_paletas_do_tema():
    ns = {}
    arvore = ast.parse(_fonte())
    for no in arvore.body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "PALETAS" for t in no.targets):
            exec(compile(ast.Module(body=[no], type_ignores=[]), AGENTE, "exec"), ns)
    paletas = ns["PALETAS"]
    assert set(paletas) == {"escuro", "claro"}
    assert set(paletas["escuro"]) == set(paletas["claro"])
    for p in paletas.values():
        # cores repetidas numa paleta tornariam a troca ambigua
        assert len({v.lower() for v in p.values()}) == len(p)
    # 11/11 (9.11): tokens Zinc do prompt da Area do Cliente
    assert paletas["escuro"]["fundo"] == "#09090b" and paletas["escuro"]["superficie"] == "#18181b"
    assert paletas["claro"]["fundo"] == "#fafafa" and paletas["claro"]["superficie"] == "#ffffff"


def test_trocar_cores_percorre_toda_a_janela():
    import types
    arvore = ast.parse(_fonte())
    corpo = [no for no in arvore.body
             if (isinstance(no, ast.FunctionDef) and no.name == "trocar_cores")
             or (isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "CORES_DOS_WIDGETS" for t in no.targets))]
    ns = {"tk": types.SimpleNamespace(TclError=KeyError)}
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)

    class W:
        def __init__(self, filhos=(), **cores):
            self.cores, self.filhos = cores, list(filhos)

        def cget(self, opcao):
            return self.cores[opcao]  # KeyError faz o papel do TclError

        def configure(self, d):
            self.cores.update(d)

        def winfo_children(self):
            return self.filhos

    neto = W(background="#0F1117", foreground="white")
    raiz = W([W([neto], background="#171b26")], background="#0f1117")
    ns["trocar_cores"](raiz, {"#0f1117": "#f4f5fa", "#171b26": "#ffffff"})
    assert raiz.cores["background"] == "#f4f5fa"
    assert raiz.filhos[0].cores["background"] == "#ffffff"
    assert neto.cores == {"background": "#f4f5fa", "foreground": "white"}


def test_programacao_no_agente():
    src = _fonte()
    assert 'evento == "programacao_atualizada"' in src
    assert "/api/programacao/agente" in src
    # carregamento antigo que chegue atrasado nao substitui o novo
    mostrar = src[src.index("def _mostrar_lista"):]
    assert "self._geracao" in mostrar[:mostrar.index("\n    def ", 1)]


def _funcoes_do_agente(*nomes, **globais):
    arvore = ast.parse(_fonte())
    corpo = [no for no in arvore.body
             if (isinstance(no, ast.FunctionDef) and no.name in nomes)
             or (isinstance(no, ast.Assign) and any(getattr(t, "id", "") in nomes for t in no.targets))]
    ns = dict(globais)
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    return ns


def test_endereco_do_servidor_normalizado():
    ns = _funcoes_do_agente("normalizar_servidor")
    n = ns["normalizar_servidor"]
    assert n(" 10.26.31.99:8000 ") == "ws://10.26.31.99:8000"
    assert n("http://10.26.31.99:8000/") == "ws://10.26.31.99:8000"
    assert n("https://mathecafe.onrender.com") == "wss://mathecafe.onrender.com"
    assert n("ws://localhost:8000") == "ws://localhost:8000"
    assert n("   ") == ""


def test_cfg_guarda_as_outras_chaves(tmp_path):
    import os as _os
    cfg = tmp_path / "agente.cfg"
    ns = _funcoes_do_agente("carregar_cfg", "gravar_cfg", "salvar_cfg", "salvar_tema",
                            os=_os, CFG_FILE=str(cfg))
    ns["salvar_cfg"]("ws://a:8000", "PC-01")
    ns["salvar_tema"]("claro")
    ns["gravar_cfg"](OPERADORES="x")
    ns["salvar_cfg"]("ws://b:8000", "PC-02")  # trocar o servidor não apaga tema nem operadores
    assert ns["carregar_cfg"]() == {"SERVIDOR": "ws://b:8000", "ESTACAO": "PC-02",
                                    "TEMA": "claro", "OPERADORES": "x"}


def test_operador_entra_na_manutencao_sem_rede(tmp_path):
    # Agente apontando para o servidor errado fica sem conexão: sem isto não
    # daria para entrar na manutenção e corrigir o endereço
    import os as _os, hashlib, hmac
    cfg = tmp_path / "agente.cfg"
    ns = _funcoes_do_agente("carregar_cfg", "gravar_cfg", "_hash_operador", "lembrar_operador",
                            "esquecer_operador", "operador_conferido_sem_rede",
                            "_operadores_guardados", "OPERADORES_LEMBRADOS",
                            os=_os, hashlib=hashlib, hmac=hmac, CFG_FILE=str(cfg))
    conferir = ns["operador_conferido_sem_rede"]
    assert not conferir("maria", "senha-da-maria")  # nunca entrou nesta estação
    ns["lembrar_operador"]("Maria", "senha-da-maria")
    ns["lembrar_operador"]("joao", "senha-do-joao")
    assert conferir("maria", "senha-da-maria") and conferir("joao", "senha-do-joao")
    assert not conferir("maria", "errada") and not conferir("ana", "senha-da-maria")
    assert "senha-da-maria" not in cfg.read_text(encoding="utf-8")  # só o hash
    ns["lembrar_operador"]("maria", "senha-nova")  # trocou a senha: vale a nova
    assert conferir("maria", "senha-nova") and not conferir("maria", "senha-da-maria")
    ns["esquecer_operador"]("maria")  # servidor recusou: some daqui também
    assert not conferir("maria", "senha-nova") and conferir("joao", "senha-do-joao")
    for i in range(10):
        ns["lembrar_operador"](f"op{i}", "s")
    assert len(ns["carregar_cfg"]()["OPERADORES"].split(",")) == 5  # só os últimos


def test_configurar_conexao_na_manutencao():
    src = _fonte()
    barra = src[src.index("self.frame_manutencao = tk.Frame"):src.index("def _log(")]
    assert "self._abrir_config_conexao" in barra
    prompt = src[src.index("def _abrir_prompt_admin"):src.index("def _exibir_mensagem_operador")]
    assert "operador_conferido_sem_rede(" in prompt
    resultado = src[src.index('evento == "validar_manutencao_resultado"'):]
    resultado = resultado[:resultado.index("elif evento ==")]
    assert "lembrar_operador(" in resultado and "esquecer_operador(" in resultado
    config = src[src.index("def _abrir_config_conexao"):]
    config = config[:config.index("\n    def ", 1)]
    # só dentro da manutenção, e reinicia o agente com a configuração nova
    assert "self.modo_manutencao_ativo" in config and "salvar_cfg(" in config and "os.execv" in config


def test_reconectar_na_manutencao_avisa_o_servidor():
    src = _fonte()
    conectado = src[src.index('if evento == "_conectado":'):]
    conectado = conectado[:conectado.index("elif evento ==")]
    assert "self.modo_manutencao_ativo" in conectado and '"status": "manutencao"' in conectado


def test_queda_do_servidor_nao_derruba_a_sessao():
    # Antes o agente voltava ao login quando perdia o servidor e o cliente caia
    # junto; agora segue a sessao e, ao reconectar, diz em que sessao esta
    src = _fonte()
    i = src.index('elif evento == "_desconectado":')
    trecho = src[i:src.index("elif evento ==", i + 10)]
    assert "_voltar_login" not in trecho
    conexao = src[src.index("async def _ws_loop"):src.index("def _enviar(")]
    assert '"evento": "estado"' in conexao and '"evento": "ping"' not in conexao
    # o fim de sessao sem conexao fica guardado para depois
    enviar = src[src.index("def _enviar("):src.index("def _processar_fila")]
    assert "_pendentes.append" in enviar


def test_fim_de_sessao_guardado_diz_ha_quanto_tempo_foi():
    ns = _funcoes_do_agente("mensagens_pendentes")
    msgs = ns["mensagens_pendentes"]([({"evento": "sessao_encerrada", "sessao_id": 7}, 100.0)], 700.9)
    assert msgs == [{"evento": "sessao_encerrada", "sessao_id": 7, "segundos_atras": 600}]


def test_testar_conexao_nao_mexe_na_sessao_da_estacao():
    # "ping" como primeira mensagem e o agente antigo: o servidor encerraria a
    # sessao aberta daquela estacao
    src = _fonte()
    trecho = src[src.index("def testar_conexao("):src.index("# Operadores que ja entraram")]
    assert '"teste_conexao"' in trecho and '"ping"' not in trecho


def test_desligar_pelo_painel():
    src = _fonte()
    i = src.index('elif evento == "desligar_pc":')
    trecho = src[i:src.index("elif evento ==", i + 10)]
    assert "_voltar_login" in trecho and "desligar=True" in trecho
    contagem = src[src.index("def _countdown_reinicio"):src.index("def _encerrar_apps_do_cliente")]
    assert '"/s" if desligar else "/r"' in contagem


def test_dock_e_notificacoes_do_agente():
    # 9.4: dock no lugar da barra (fundo transparente, sininho com o numero) e
    # notificacoes no canto: a mensagem do operador na sessao vira notificacao
    src = _fonte()
    dock = src[src.index("class BarraSessao:"):src.index("class Notificacoes:")]
    assert "-transparentcolor" in dock and "self.sininho" in dock and "lbl_relogio" in dock
    msg = src[src.index('elif evento == "mensagem_tela":'):]
    msg = msg[:msg.index("elif evento ==", 10)]
    assert "self.notificacoes.notificar(" in msg and 'dados.get("origem") == "horario"' in msg
    saldo = src[src.index("def _avisar_saldo_baixo"):]
    assert "messagebox" not in saldo[:saldo.index("\n    def ", 1)]
    # nada passa para o proximo cliente
    voltar = src[src.index("def _voltar_login"):src.index("def _countdown_encerramento")]
    assert "self.notificacoes.limpar()" in voltar


def test_dock_nao_pisca_e_sininho_junto_da_hora():
    # 1.9.1 piscava: redesenhava o dock inteiro a cada 16 ms com o mouse em cima.
    # Agora o mouse so troca o contorno do icone e o sininho fica no bloco da hora.
    src = _fonte()
    dock = src[src.index("class BarraSessao:"):src.index("class Notificacoes:")]
    assert "after(16" not in dock
    mover = dock[dock.index("def _ao_mover"):dock.index("def _ao_sair")]
    assert "desenhar(" not in mover
    assert "tk.Canvas(self.bloco" in dock  # sininho dentro do bloco, ao lado do relogio
    montar = dock[dock.index("def _montar_itens"):dock.index("def atualizar_apps")]
    assert "sininho" not in montar  # fora do dock
    assert dock.count("create_window(") == 1 and "_janela_bloco is None" in dock


def test_cor_do_piso_no_agente():
    ns = _funcoes_do_agente("escurecer", "cor_valida", re=__import__("re"))
    assert ns["escurecer"]("#ec4899") == "#c13b7d"
    assert ns["cor_valida"]("#ec4899") and not ns["cor_valida"]("rosa")
    src = _fonte()
    assert 'elif evento == "piso_estacao":' in src
    inicio = src[src.index("    def _iniciar_sessao(self, dados):"):]
    assert "_aplicar_cor_piso" in inicio[:300]


def _funcoes_de_arquivos():
    ns = _carregar("listar_arquivos", "limpar_pasta", "pode_abrir_arquivo", "tamanho_legivel")
    arvore = ast.parse(_fonte())
    for no in arvore.body:
        if isinstance(no, ast.Assign) and getattr(no.targets[0], "id", "") == "EXTENSOES_DOCUMENTOS":
            ns["EXTENSOES_DOCUMENTOS"] = ast.literal_eval(no.value)
    ns["os"] = os
    return ns


def test_meus_arquivos_lista_e_so_abre_documentos(tmp_path):
    # 9.5: tela Meus arquivos mostra os downloads da sessao; so abre documentos e imagens
    ns = _funcoes_de_arquivos()
    (tmp_path / "boleto.pdf").write_bytes(b"x" * 2048)
    (tmp_path / "foto.JPG").write_bytes(b"x")
    (tmp_path / "virus.exe").write_bytes(b"x")
    (tmp_path / "baixando.pdf.crdownload").write_bytes(b"x")
    (tmp_path / "desktop.ini").write_bytes(b"x")
    (tmp_path / "pasta").mkdir()
    nomes = [a["nome"] for a in ns["listar_arquivos"](str(tmp_path))]
    assert sorted(nomes) == ["boleto.pdf", "foto.JPG", "virus.exe"]
    pode = ns["pode_abrir_arquivo"]
    assert pode("boleto.pdf") and pode("foto.JPG") and pode("planilha.xlsx")
    assert not pode("virus.exe") and not pode("script.bat") and not pode("atalho.lnk")
    assert ns["tamanho_legivel"](2048) == "2 KB" and ns["tamanho_legivel"](3 * 1024 * 1024) == "3,0 MB"


def test_downloads_limpos_entre_clientes(tmp_path):
    # o proximo cliente nao ve o que o anterior baixou
    ns = _funcoes_de_arquivos()
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_bytes(b"x")
    assert ns["limpar_pasta"](str(tmp_path)) == 2
    assert list(tmp_path.iterdir()) == [] and tmp_path.exists()
    # nunca limpa a pasta do usuario inteira nem a raiz do disco
    assert ns["limpar_pasta"](os.path.expanduser("~")) == 0
    assert ns["limpar_pasta"]("C:\\") == 0
    src = _fonte()
    voltar = src[src.index("def _voltar_login"):src.index("def _countdown_encerramento")]
    assert "self._limpar_downloads" in voltar
    voltar = voltar[:voltar.index("self._limpar_downloads")]
    assert "self._encerrar_apps_do_cliente()" in voltar  # fecha os apps antes (arquivos soltos)
    inicio = src[src.index("    def _iniciar_sessao(self, dados):"):src.index("    def _montar_launcher")]
    assert "self._limpar_downloads()" in inicio  # PC reiniciou no meio da sessao anterior
    dock = src[src.index("class BarraSessao:"):src.index("class Notificacoes:")]
    assert '"arquivos"' in dock and "abrir_meus_arquivos" in dock


def test_downloads_presos_na_pasta_downloads():
    # 1.10.0: o navegador deixava salvar em qualquer pasta (fora da limpeza)
    pol = _fonte(os.path.join(os.path.dirname(AGENTE), "politicas_cliente.ps1"))
    for navegador in ("Google\Chrome", "Microsoft\Edge"):
        assert navegador in pol
    assert "DownloadDirectory" in pol and "'${user_home}\Downloads'" in pol
    assert '"PromptForDownloadLocation" -Value 0' in pol


def test_meus_arquivos_abre_o_explorador_preso_em_downloads():
    # 9.5 refeito (09/11): o leque nao funcionou bem. O icone de pasta do dock
    # abre o Explorador de verdade na pasta Downloads, e um vigia (PowerShell
    # escondido, COM Shell.Application) traz de volta para Downloads qualquer
    # janela do Explorador que saia dela.
    src = _fonte()
    assert "class MeusArquivos:" not in src
    abrir = src[src.index("def abrir_meus_arquivos(self"):]
    abrir = abrir[:abrir.index("\n    def ", 10)]
    assert "explorer.exe" in abrir and "_ligar_vigia" in abrir
    mover = src[src.index("def _ao_mover(self"):src.index("def _ao_sair(self")]
    assert "espiar" not in mover
    # o vigia liga na sessao e desliga ao voltar ao login
    assert "self._ligar_vigia()" in src[src.index("def _iniciar_sessao("):src.index("def _iniciar_sessao(") + 3000]
    voltar = src[src.index("def _voltar_login(self"):]
    assert "self._desligar_vigia()" in voltar[:voltar.index("\n    def ", 10)]
    # o agente nao mata o proprio vigia, e com ele ligado o Explorador e permitido
    processos = src[src.index("def _verificar_processos(self"):src.index("def _fechar_janelas_fora_da_whitelist")]
    assert "self._pids_proprios" in processos
    janelas = src[src.index("def _fechar_janelas_fora_da_whitelist"):src.index("# ── Auto-update")]
    assert "_vigia" in janelas


def test_agente_so_se_atualiza_na_manutencao():
    # 6.13: antes o agente se atualizava e reiniciava sozinho ao abrir, ate com
    # cliente na tela de login. Agora so confere a versao; quem troca e o
    # operador, pelo botao da faixa da manutencao.
    src = _fonte()
    checar = src[src.index("def checar_atualizacao("):src.index("CFG_FILE =")]
    assert "os.replace" not in checar and "execv" not in checar
    aplicar = src[src.index("def _aplicar_atualizacao("):]
    aplicar = aplicar[:aplicar.index("\n    def ", 10)]
    # 1.16: tambem pelo painel, mas nunca com cliente usando
    assert "self.sessao_ativa or not (self.modo_manutencao_ativo or pelo_painel)" in aplicar
    assert "os.replace" in aplicar and "execv" in aplicar
    faixa = src[src.index("self.frame_manutencao = tk.Frame"):src.index("def _log(self")]
    assert "self.btn_atualizar" in faixa


def test_compara_versoes_do_agente():
    ns = _funcoes_do_agente("_versao_tuple", "ha_versao_nova")
    assert ns["ha_versao_nova"]("1.11.0", "1.10.2") is True
    assert ns["ha_versao_nova"]("1.10.2", "1.10.2") is False
    assert ns["ha_versao_nova"]("1.9.9", "1.10.0") is False  # numero, nao texto
    assert ns["ha_versao_nova"](None, "1.0.0") is False


def test_script_do_vigia_volta_para_downloads():
    ns = _funcoes_do_agente("script_vigia")
    script = ns["script_vigia"](r"C:\Users\cli'ente\Downloads", 4321)
    assert r"C:\Users\cli''ente\Downloads" in script  # aspas escapadas para o PowerShell
    assert "Shell.Application" in script and "Navigate2" in script
    assert "Get-Process -Id 4321" in script  # termina sozinho se o agente cair


def test_notificacoes_com_fade_e_deslize():
    # 09/11: fade ao aparecer e deslize para a direita ao fechar
    src = _fonte()
    notif = src[src.index("class Notificacoes:"):src.index("def _fonte_pil(")]
    assert '"-alpha"' in notif  # fade da janela (aparece e some)
    dispensar = notif[notif.index("def _dispensar("):notif.index("def _tirar(")]
    assert 'item["saindo"] = True' in dispensar and "self.LARGURA" in dispensar  # sai pela direita
    assert "self._tirar(ident)" in notif  # so sai da lista depois de deslizar
    mostrar = notif[notif.index("def _mostrar("):notif.index("def _posicionar(")]
    assert "self._alpha_alvo, self._dx_alvo = 0.0" in mostrar  # some com fade, para a direita
    assert "self.top.withdraw()" not in mostrar  # nao some de uma vez


def test_dock_usa_a_capa_do_app():
    # 09/11: o icone do app no dock e a imagem cadastrada em Apps permitidos
    src = _fonte()
    assert "def icone_do_app(dados, lado, raio, fundo)" in src
    dock = src[src.index("class BarraSessao:"):src.index("class Notificacoes:")]
    assert '"imagem_url": (a.get("imagem_url") or "").strip() or None' in dock
    desenho = dock[dock.index("def desenhar(self)"):]
    assert "self._icone_do_item(item)" in desenho and "create_image(x, topo + t / 2, image=capa" in desenho
    # a imagem nao leva a etiqueta icone{k} (o _marcar_sobre muda o contorno, que imagem nao tem)
    assert 'image=capa, tags="desenho")' in desenho


def test_instalador_so_pergunta_nome_e_servidor():
    # 1.14: o PC aparece sozinho em "Novas estacoes"; sem login de admin no
    # instalador. Reinstalar mantem o ID (senao o PC voltaria como estacao nova).
    with open(os.path.join(os.path.dirname(AGENTE), "instalar.bat"), "rb") as f:
        bat = f.read()
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")  # CRLF
    texto = bat.decode("ascii")
    assert "ADMIN_" not in texto and "/api/auth/login" not in texto
    assert "%COMPUTERNAME%" in texto
    assert 'findstr /b /c:"ID="' in texto and "echo ID=!ID_PC!" in texto


def test_tela_de_apps_categorias_e_pesquisa():
    # 09/11: tela de apps estilo loja: Todos, as categorias do painel na ordem
    # dele e "Outros" (sem categoria) no fim; a pesquisa ignora acento e maiuscula
    ns = _carregar("normalizar_busca", "categorias_da_tela", "filtrar_apps")
    apps = [
        {"nome": "Paciência", "categoria": "Jogos", "categoria_ordem": 2},
        {"nome": "Google Chrome", "categoria": "Internet", "categoria_ordem": 1},
        {"nome": "Xadrez", "categoria": "Jogos", "categoria_ordem": 2},
        {"nome": "Calculadora", "categoria": None, "categoria_ordem": None},
    ]
    cats = ns["categorias_da_tela"](apps)
    assert cats == [("todos", "Todos", 4), ("cat:Internet", "Internet", 1), ("cat:Jogos", "Jogos", 2),
                    ("outros", "Outros", 1)]
    filtrar = ns["filtrar_apps"]
    assert [a["nome"] for a in filtrar(apps, "cat:Jogos", "")] == ["Paciência", "Xadrez"]
    assert [a["nome"] for a in filtrar(apps, "outros", "")] == ["Calculadora"]
    assert [a["nome"] for a in filtrar(apps, "todos", "PACIENCIA")] == ["Paciência"]
    assert [a["nome"] for a in filtrar(apps, "cat:Jogos", "chrome")] == []
    # servidor antigo (sem categoria): so "Todos", sem um "Outros" repetido
    antigos = [{"nome": "Chrome"}, {"nome": "Word"}]
    assert ns["categorias_da_tela"](antigos) == [("todos", "Todos", 2)]
    assert len(filtrar(antigos, "todos", "")) == 2


def test_tela_de_apps_com_banner_largo():
    # 09/11: a Programacao virou um banner largo no topo (cartaz inteiro sobre
    # ele mesmo desfocado) e a grade fica embaixo, com pesquisa e categorias
    src = _fonte()
    assert "class TelaApps:" in src
    banner = src[src.index("def montar_banner("):src.index("def montar_cartao(")]
    assert "GaussianBlur" in banner
    prog = src[src.index("class Programacao:"):src.index("class TelaApps:")]
    assert "montar_banner(" in prog
    assert 'side="top", fill="x"' in prog and "before=self.app.frame_launcher" in prog
    assert "Image.blend(" in prog  # troca de cartaz com fade
    tela = src[src.index("class TelaApps:"):src.index("class AgenteApp:")]
    assert "filtrar_apps(" in tela and "categorias_da_tela(" in tela
    assert 'itemconfig("capa"' in tela  # hover so troca a imagem (nao pisca)
    launcher = src[src.index("    def _montar_launcher(self):"):src.index("    def _abrir_app(self, app):")]
    assert "self._tela_apps.mostrar(" in launcher
    tema = src[src.index("    def alternar_tema(self):"):src.index("    def _ao_redimensionar(")]
    assert "self._tela_apps.redesenhar()" in tema and "self._programacao.redesenhar()" in tema


def test_atualiza_pelo_painel_sem_cliente_usando():
    # 1.16: o painel manda "atualizar_agente"; nunca com sessao ativa
    src = _fonte()
    assert 'evento == "atualizar_agente"' in src
    metodo = src[src.index("def _atualizar_pelo_painel"):src.index("def _aplicar_atualizacao")]
    assert "if self.sessao_ativa:" in metodo
    aplicar = src[src.index("def _aplicar_atualizacao"):src.index("def _modo_manutencao")]
    assert "self.sessao_ativa or not (self.modo_manutencao_ativo or pelo_painel)" in aplicar
    # a versao precisa bater com a que o servidor exige para mandar o comando
    import re
    from app.routers.estacoes import ATUALIZA_PELO_PAINEL
    versao = re.search(r'^VERSAO = "([\d.]+)"', src, re.M).group(1)
    assert tuple(map(int, versao.split("."))) >= tuple(map(int, ATUALIZA_PELO_PAINEL.split(".")))


def test_mensagem_longa_nao_corta():
    # 09/11: a janela era 380x160 fixa e cortava a mensagem; agora cresce com o
    # texto (rola passando de 60% da tela) e o cartao da notificacao abre ela inteira
    linhas = _carregar("linhas_do_texto")["linhas_do_texto"]
    medir = lambda t: len(t) * 10  # 10 px por letra
    assert linhas("", medir, 100) == 1
    assert linhas("uma linha", medir, 100) == 1
    assert linhas("aaaa bbbb cccc dddd", medir, 100) == 2  # 9 letras por linha
    assert linhas("a\nb\nc", medir, 100) == 3
    assert linhas("x" * 35, medir, 100) == 4  # palavra enorme quebra
    src = _fonte()
    janela = src[src.index("def _exibir_mensagem_operador"):src.index("def _servidor_http")]
    assert "w, h = 380, 160" not in janela and "linhas_do_texto(" in janela
    cartao = src[src.index("    def _cartao(self, c, item"):src.index("    def _caber(")]
    assert "_exibir_mensagem_operador(" in cartao and "modal=False" in cartao


def test_login_em_duas_metades_com_os_cartazes():
    # 09/11: login do PC no modelo enviado pelo Matheus: formulario a esquerda,
    # cartazes da Programacao a direita com o titulo digitando; sem "criar
    # conta" nem Google, so o aviso do balcao
    src = _fonte()
    assert "class TelaLogin:" in src
    login = src[src.index("        # ── Frame de login ──"):src.index("        # ── Frame de sessão (launcher) ──")]
    assert "TelaLogin(self" in login
    assert "self.entry_login" in login and "self.entry_senha" in login and "self.btn_login" in login
    assert "Fale com um funcionário" in login
    assert "self._alternar_senha" in login  # o olho mostra/esconde a senha
    tela = src[src.index("class TelaLogin:"):src.index("class AgenteApp:")]
    assert "def _digitar(" in tela and "root.after(" in tela  # frase digitando
    # os cartazes chegam ao login mesmo sem sessao, e ja ao conectar
    prog = src[src.index("    def _mostrar_lista(self, geracao"):src.index("    def _ao_mudar_tamanho(")]
    assert prog.index("self.app._tela_login.definir(") < prog.index("if not imagens or not self.app.sessao_ativa")
    conectado = src[src.index('if evento == "_conectado":'):src.index('elif evento == "_desconectado":')]
    assert "self._programacao.recarregar()" in conectado
    atualizada = src[src.index('elif evento == "programacao_atualizada":'):src.index('elif evento == "parar_streaming":')]
    assert "if self.sessao_ativa" not in atualizada
    tema = src[src.index("    def alternar_tema(self):"):src.index("    def _ao_redimensionar(")]
    assert "self._tela_login.redesenhar()" in tema


def test_rolagem_da_grade_volta_em_cada_sessao():
    # _voltar_login tira o <MouseWheel> de tudo: a grade liga de novo a cada sessao
    src = _fonte()
    assert 'self.root.unbind_all("<MouseWheel>")' in src
    mostrar = src[src.index("class TelaApps:"):]
    mostrar = mostrar[mostrar.index("    def mostrar(self, apps):"):mostrar.index("    def _baixar_capa(")]
    assert 'bind_all("<MouseWheel>", self._rolar)' in mostrar


def test_instalador_sugere_e_testa_o_servidor():
    # 10/11: o exemplo apontava para 10.26.31.99 (o servidor e o .77) e um
    # endereco errado so aparecia como "o PC nunca chega ao painel"
    pasta = os.path.dirname(AGENTE)
    texto = open(os.path.join(pasta, "instalar.bat"), "rb").read().decode("ascii")
    assert "10.26.31.99" not in texto
    assert 'servidor.txt' in texto and "SERVIDOR_PADRAO" in texto
    assert "/health" in texto and "goto pedir_servidor" in texto
    assert "--noproxy" in texto  # rede da biblioteca tem proxy
    padrao = open(os.path.join(pasta, "servidor.txt"), encoding="ascii").readline().strip()
    host, porta = padrao.rsplit(":", 1)
    assert host.count(".") == 3 and porta.isdigit() and "://" not in padrao


def test_instalador_instala_python_proprio():
    # 10/11: maquina nova nao tem Python; o instalador baixa do python.org e
    # instala um Python so do agente em C:\MatheCafe\python (com Tkinter), sem
    # mexer em outro Python da maquina; dependencias pelo pip com o proxy do Windows
    texto = open(os.path.join(os.path.dirname(AGENTE), "instalar.bat"), "rb").read().decode("ascii")
    assert "where py" not in texto and "python_ausente" not in texto  # nao exige Python antes
    assert "set PY_VERSAO=3." in texto and "https://www.python.org/ftp/python/" in texto
    instalar = texto[texto.index(":instalar_python"):]
    for opcao in ("/quiet", "InstallAllUsers=1", 'TargetDir="%DESTINO%\python"', "Include_tcltk=1",
                  "Include_pip=1", "PrependPath=0", "Include_launcher=0", "AssociateFiles=0", "Shortcuts=0"):
        assert opcao in instalar, opcao
    assert "import sys, tkinter" in texto  # o agente e Tkinter
    assert "GetSystemWebProxy" in texto and "HTTPS_PROXY" in texto  # rede da biblioteca tem proxy
    assert '"%DESTINO%\python\python.exe" -m venv' in texto


def test_nome_trocado_no_pc_avisa_que_vai_para_aprovacao():
    # 1.18: trocar o nome em Configurar conexao nao muda sozinho (o servidor
    # reconhece o PC pelo id e devolve o nome atual); o tecnico e avisado
    src = _fonte()
    salvar = src[src.index("        def salvar():"):src.index('("Salvar e reiniciar"')]
    assert "Novas estações" in salvar and "self.identificador and self.aprovada" in salvar
    assert salvar.index("showinfo") < salvar.index("salvar_cfg(")


def test_login_sem_log_e_sem_barra_de_cima():
    # 10/11: o log de comunicacao saiu da tela do PC (vai so ao servidor) e a
    # barra de cima sumiu; o nome do PC fica grande acima do formulario, com
    # um computador verde (online) ou vermelho (offline)
    src = _fonte()
    assert "LOG DE COMUNICACAO" not in src
    assert "scrolledtext" not in src
    assert "self.frame_log " not in src and "self.frame_log." not in src and "self.header_frame" not in src
    login = src[src.index("        # ── Frame de login ──"):src.index("        # ── Frame de sessão (launcher) ──")]
    assert login.index("self.lbl_estacao") < login.index("self.entry_login")
    assert "self._icone_pc" in login
    conectado = src[src.index('if evento == "_conectado":'):src.index('elif evento == "_info":')]
    assert 'self._desenhar_icone_pc(COR_ONLINE)' in conectado
    assert 'self._desenhar_icone_pc(COR_OFFLINE)' in conectado


def test_log_sem_conexao_vai_ao_servidor_depois():
    # As linhas de quando o PC estava sem servidor (as que mais ajudam) ficam
    # guardadas e vao com a hora original quando ele reconecta
    src = _fonte()
    log = src[src.index("    def _log(self, msg, _remoto=True):"):src.index("    # ── WebSocket (thread separada)")]
    assert "self._logs_offline.append(" in log
    assert '"ts": ' in log
    conectado = src[src.index('if evento == "_conectado":'):src.index('elif evento == "_desconectado":')]
    assert "self._enviar_logs_offline()" in conectado


def test_instalador_pergunta_o_piso():
    # 6.18 parte B: com o servidor respondendo, lista os pisos dele
    # (/api/agente/pisos, "id;nome") e grava PISO= no agente.cfg
    texto = open(os.path.join(os.path.dirname(AGENTE), "instalar.bat"), "rb").read().decode("ascii")
    assert "/api/agente/pisos" in texto and "call :escolher_piso" in texto
    assert texto.index("call :escolher_piso") < texto.index("[1/6]")
    assert "if defined PISO echo PISO=!PISO!" in texto
    rotina = texto[texto.index(":escolher_piso"):]
    assert 'delims=;' in rotina and "goto perguntar_piso" in rotina


def test_area_do_cliente_menu_widgets_e_cards():
    # 11/11 (9.11): Area do Cliente do prompt do Matheus, em Tkinter. Menu da
    # esquerda (Inicio e Meus Apps, sem Historico), widgets da direita (sessao e
    # avisos, sem pedir +30 min), pilulas de categoria e cards com "Abrir"
    src = _fonte()
    assert "class MenuLateral:" in src and "class PainelDireito:" in src
    menu = src[src.index("class MenuLateral:"):src.index("class PainelDireito:")]
    assert '"Início"' in menu and '"Meus Apps"' in menu
    assert "Histórico" not in menu and "Biblioteca" not in menu
    assert "LARGURA_ABERTO, LARGURA_FECHADO = 240, 70" in menu
    direito = src[src.index("class PainelDireito:"):src.index("class AgenteApp:")]
    assert "AVISOS DA BIBLIOTECA" in direito and "SESSÃO ATIVA" in direito
    assert "/api/avisos/agente" in direito
    assert "+30" not in src
    assert "topo_sessao" not in src  # o tempo e o Encerrar estao no widget e no dock
    tela = src[src.index("class TelaApps:"):src.index("class TelaLogin:")]
    assert '"Abrir"' in tela and "self.lista_cat" not in tela  # categorias viraram pilulas
    atualizado = src[src.index('elif evento == "avisos_atualizados":'):]
    assert "self._painel_direito.recarregar_avisos()" in atualizado[:300]


def test_cor_da_categoria_no_agente():
    ns = _carregar("cor_do_app", "cor_valida", "_paleta_categorias")
    ns["re"] = __import__("re")
    cor = ns["cor_do_app"]
    assert cor({"categoria": "Jogos", "categoria_cor": "#E11D48"}, "#6366f1") == "#e11d48"
    # servidor antigo (sem cor): uma da paleta pela ordem da categoria
    a = cor({"categoria": "Jogos", "categoria_ordem": 1}, "#6366f1")
    assert a.startswith("#") and a != "#6366f1"
    assert cor({"categoria": "Jogos", "categoria_ordem": 1}, "#000000") == a
    assert cor({"categoria": None}, "#6366f1") == "#6366f1"  # Outros: o destaque do piso


def test_banner_abre_o_link_do_cartaz():
    src = _fonte()
    prog = src[src.index("class Programacao:"):src.index("class TelaApps:")]
    assert "Ver no navegador / Inscrição" in prog
    assert "webbrowser.open(" in prog
    assert 'item.get("link")' in prog


def test_area_do_cliente_acabamento_shadcn():
    # 11/11 (9.12): segundo prompt do Matheus: cards com capa em cima e rodape
    # (titulo, descricao e Abrir azul a direita), selo no canto de cima a
    # esquerda, banner de 250 px com degrade do fundo, dock em barra inteira com
    # Encerrar rosa suave, relogio e tempo juntos e contador azul
    src = _fonte()
    tela = src[src.index("class TelaApps:"):src.index("class TelaLogin:")]
    assert "CAPA_H = 128" in tela
    assert 'a.get("descricao")' in tela
    assert "AZUL" in tela and '"Abrir"' in tela
    cartao = src[src.index("def montar_cartao("):src.index("def baixar_imagem(")]
    assert "0.4)  # opacity-60" in cartao  # capa escurecida: 40% do zinc-950 por cima
    prog = src[src.index("class Programacao:"):src.index("class TelaApps:")]
    assert "return 250" in prog
    assert "AZUL" in prog  # botao do banner em pilula azul
    banner = src[src.index("def montar_banner("):src.index("def montar_cartao(")]
    assert "#09090b" in banner  # degrade da esquerda no zinc-950, nao em preto
    dock = src[src.index("class BarraSessao:"):src.index("class Notificacoes:")]
    assert "Pilula(" in dock and "ROSA" in dock
    assert '"#ef4444", fg="white"' not in dock  # sem o vermelho vivo no Encerrar
    assert "AZUL" in dock[dock.index("def atualizar_sininho"):]  # contador azul
    assert "class Pilula:" in src
    # sem branco puro nos textos dos cards e do banner
    assert 'fill="#ffffff"' not in tela and 'fill="#ffffff"' not in prog


def test_paleta_das_categorias_no_agente():
    ns = _carregar("_paleta_categorias")
    assert ns["_paleta_categorias"]()[:5] == ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#f43f5e"]


def test_desinstalador_limpa_tudo():
    # 11/11: para testar a instalacao de novo numa maquina, o desinstalar.bat
    # precisa deixar o PC como antes: tarefa, autologin, usuario cliente e perfil,
    # Python do agente (so o instalado pelo instalar.bat) e a pasta inteira
    pasta = os.path.dirname(AGENTE)
    bat = open(os.path.join(pasta, "desinstalar.bat"), "rb").read()
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")  # CRLF
    texto = bat.decode("ascii")
    assert "net session" in texto  # so como administrador
    assert 'set /p CONFIRMA=' in texto and '"SIM"' in texto  # pede confirmacao
    assert 'schtasks /delete /tn "MatheCafe-Agente"' in texto
    assert "AutoAdminLogon /t REG_SZ /d \"0\"" in texto and "DefaultPassword" in texto
    assert "Win32_UserProfile" in texto and "net user cliente /delete" in texto
    # o Python so sai se for o registrado na pasta do agente
    assert "PythonCore" in texto and "QuietUninstallString" in texto and "$alvo" in texto
    assert 'rmdir /s /q "%DESTINO%"' in texto
    # rodando de dentro da pasta que vai apagar, continua de uma copia
    assert '%TEMP%\mathecafe_desinstalar.bat' in texto
    assert texto.index("[6/6]") > texto.index("[5/6]") > texto.index("[4/6]")
    # o instalador leva o desinstalador para C:\MatheCafe
    instalador = open(os.path.join(pasta, "instalar.bat"), "rb").read().decode("ascii")
    assert "desinstalar.bat" in instalador


def test_politicas_do_ctrl_alt_del_valem_mesmo_se_a_instalacao_falhar():
    # 11/11: numa maquina nova o passo [6/6] falhou (perfil do cliente ainda nao
    # existia) e o Ctrl+Alt+Del deixava trocar a senha e abrir o Gerenciador de
    # Tarefas. Agora uma tarefa como SYSTEM grava as politicas a cada logon do
    # cliente (o perfil dele ja esta carregado), sem depender da instalacao.
    pasta = os.path.dirname(AGENTE)
    reg = open(os.path.join(pasta, "registrar_politicas.ps1"), "rb").read()
    assert b"\r\n" in reg and b"\n" not in reg.replace(b"\r\n", b"")
    reg = reg.decode("ascii")
    assert '"MatheCafe-Politicas"' in reg and "-AtLogOn -User" in reg
    assert 'New-ScheduledTaskPrincipal -UserId "SYSTEM"' in reg and "politicas_cliente.ps1" in reg
    pol = _fonte(os.path.join(pasta, "politicas_cliente.ps1"))
    for nome in ("DisableTaskMgr", "DisableLockWorkstation", "DisableChangePassword"):
        assert nome in pol
    instalar = open(os.path.join(pasta, "instalar.bat"), "rb").read().decode("ascii")
    assert "registrar_politicas.ps1" in instalar
    copia = instalar[instalar.index("for %%f in (agente.py"):]
    assert "registrar_politicas.ps1" in copia[:copia.index(")")]
    seis = instalar[instalar.index("[6/6]"):instalar.index(":fim")]
    assert seis.index("registrar_politicas.ps1") < seis.index("politicas_cliente.ps1")
    desinstalar = open(os.path.join(pasta, "desinstalar.bat"), "rb").read().decode("ascii")
    assert 'schtasks /delete /tn "MatheCafe-Politicas"' in desinstalar


def test_reinstalar_em_outro_piso_troca_o_id():
    # 11/11: reinstalado escolhendo o Infantil, o PC continuou no Adulto (o ID
    # antigo, mantido na reinstalacao, achava a estacao antes do piso)
    texto = open(os.path.join(os.path.dirname(AGENTE), "instalar.bat"), "rb").read().decode("ascii")
    assert "call :conferir_piso_do_id" in texto and "/api/agente/estacao?id=!ID_PC!" in texto
    passo4 = texto[texto.index("[4/6]"):texto.index("[5/6]")]
    assert passo4.index("call :conferir_piso_do_id") < passo4.index("echo ID=!ID_PC!")
    rotina = texto[texto.index("\r\n:conferir_piso_do_id"):texto.index("\r\n:escolher_piso")]
    assert 'if "!PISO_ATUAL!"=="!PISO!" exit /b 0' in rotina and "set ID_PC=" in rotina


def test_trocar_o_piso_pela_manutencao():
    # 11/11 (pedido do Matheus): trocar o piso sem reinstalar, em Configurar
    # conexao (Ctrl+Shift+M). Mesma regra do instalar.bat: outro piso, ID novo
    ns = _carregar("linhas_id_nome", "piso_mudou")
    assert ns["linhas_id_nome"]("1;Adulto\r\n2;Infantil\r\n") == [("1", "Adulto"), ("2", "Infantil")]
    mudou = ns["piso_mudou"]
    assert mudou("1;AD-01\r\n", "2") and not mudou("1;AD-01\r\n", "1")
    assert not mudou("", "2")  # o servidor nao conhece este ID: nada a trocar
    assert not mudou("1;AD-01", None)  # pisos nao carregaram
    src = _fonte()
    janela = src[src.index('janela.title("Configurar conexao")'):src.index("def _exibir_mensagem_operador")]
    assert "/api/agente/pisos" in janela and "/api/agente/estacao?id=" in janela
    salvar = janela[janela.index("        def salvar():"):]
    assert 'gravar_cfg(PISO=piso, ID="")' in salvar and "askyesno" in salvar
    assert salvar.index("askyesno") < salvar.index('gravar_cfg(PISO=piso, ID="")') < salvar.index("os.execv")
