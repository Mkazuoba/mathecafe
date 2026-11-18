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
    # o olho mostra/esconde a senha (13/11: dentro do campo arredondado da senha)
    campo = src[src.index("    def _campo_arredondado("):src.index("    def _desenhar_marca_login(")]
    assert "self._alternar_senha" in campo and "senha=True" in login
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
    assert "LARGURA_ABERTO, LARGURA_FECHADO = 240, 64" in menu  # 9.13: recolhido em 64 px
    direito = src[src.index("class PainelDireito:"):src.index("class AgenteApp:")]
    assert "AVISOS DA BIBLIOTECA" in direito and "TEMPO RESTANTE DE USO" in direito  # 9.13
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
    assert "Abrir Inscrição / Programação" in prog  # 9.13: o texto do botão mudou
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
    assert "min(340" in prog  # 9.13: h-[340px] (encolhe em tela baixa)
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


def test_area_do_cliente_terceira_versao():
    # 11/11 (9.13): imagem + prompt do Matheus. Menu so com a marca, Inicio, Meus
    # Apps e Configuracoes no rodape (sem o cartao do cliente, sem Historico); o
    # cliente vai para o card da sessao, a direita; avisos com tipo e horario;
    # dock com abas dos apps abertos a esquerda
    src = _fonte()
    menu = src[src.index("class MenuLateral:"):src.index("class PainelDireito:")]
    assert "LARGURA_ABERTO, LARGURA_FECHADO = 240, 64" in menu
    assert '"Início"' in menu and '"Meus Apps"' in menu and '"Configurações"' in menu
    assert "Histórico" not in menu and "avatar" not in menu  # o cliente saiu do menu
    direito = src[src.index("class PainelDireito:"):src.index("class AgenteApp:")]
    assert "TEMPO RESTANTE DE USO" in direito and "Login:" in direito and "Online" in direito
    assert '"alerta"' in direito and '"evento"' in direito and 'aviso.get("horario")' in direito
    assert "+30" not in src
    tela = src[src.index("class TelaApps:"):src.index("class TelaLogin:")]
    assert "Aplicativos da Estação" in tela and "liberados" in tela
    assert "Buscar por nome ou categoria" in tela
    assert '"Aberto"' in tela and '"Pronto"' in tela  # situacao do app no card
    prog = src[src.index("class Programacao:"):src.index("class TelaApps:")]
    assert 'item.get("descricao")' in prog or '"descricao"' in prog
    assert "Abrir Inscrição / Programação" in prog
    dock = src[src.index("class BarraSessao:"):src.index("class Notificacoes:")]
    assert "_caixas(" in dock  # abas da esquerda, cada uma com a sua largura
    inicio = src[src.index("    def __init__(self, root"):src.index("        self._build_ui()")]
    assert '"Inter"' in src and "FONTE" in inicio  # Inter se estiver instalada


def test_busca_acha_pela_categoria():
    ns = _carregar("normalizar_busca", "categorias_da_tela", "filtrar_apps")
    apps = [{"nome": "Kindle", "categoria": "Estudo & Leitura"}, {"nome": "Chrome", "categoria": "Navegação"}]
    assert [a["nome"] for a in ns["filtrar_apps"](apps, "todos", "navegacao")] == ["Chrome"]


def test_simulador_desliga_o_que_mexe_no_windows():
    # 12/11: simulador da tela do cliente para desenvolver o visual neste PC.
    # Tudo o que o agente faz no Windows tem de estar desligado nele, e os nomes
    # que ele troca tem de existir no agente (renomear quebraria o simulador).
    pasta = os.path.dirname(AGENTE)
    sim = open(os.path.join(pasta, 'simular.py'), encoding='utf-8').read()
    src = _fonte()
    for nome in ('BloqueioTeclado', 'barra_do_windows', 'iniciar_vigia', 'limpar_pasta', 'CFG_FILE'):
        assert f'ag.{nome} = ' in sim, nome
        assert (f'class {nome}' in src) or (f'def {nome}(' in src) or (f'{nome} = ' in src), nome
    for metodo in ('_verificar_processos', '_fechar_janelas_fora_da_whitelist', '_encerrar_apps_do_cliente',
                   '_limpar_downloads', '_countdown_reinicio', '_aplicar_atualizacao'):
        assert f'App.{metodo} = ' in sim, metodo
        assert f'    def {metodo}(' in src, metodo
    assert 'agente_simulacao.cfg' in sim and '-fullscreen' in sim
    # nao vai para as estacoes
    instalar = open(os.path.join(pasta, 'instalar.bat'), 'rb').read().decode('ascii')
    assert 'simular' not in instalar
    # --navegador: a pagina do espelho, com a janela escondida pelo DWM
    assert '--navegador' in sim and 'DwmSetWindowAttribute' in sim and 'focus_force' in sim
    espelho = open(os.path.join(pasta, 'simulador_navegador.py'), encoding='utf-8').read()
    assert '127.0.0.1' in espelho and 'PrintWindow' in espelho and 'multipart/x-mixed-replace' in espelho


def test_login_no_visual_da_area_do_cliente():
    # 13/11: o login do PC com a tipografia e as cores da Area do Cliente:
    # marca no canto, rotulos em caixa alta, campos arredondados, Entrar azul
    src = _fonte()
    login = src[src.index("        # ── Frame de login ──"):src.index("        # ── Frame de sessão (launcher) ──")]
    assert "self._desenhar_marca_login()" in login
    marca = src[src.index("    def _desenhar_marca_login("):src.index("    def _redesenhar_login(")]
    assert "Sistema de Estações" in marca
    assert '"LOGIN"' in login and '"SENHA"' in login
    assert login.count("self._campo_arredondado(") == 2
    assert "BotaoPrimario(" in login and "tk.Button(" not in login
    assert '"#ef4444"' not in login and 'fg="white"' not in login
    botao = src[src.index("class BotaoPrimario:"):]
    botao = botao[:botao.index("\nclass ")]
    assert "AZUL" in botao and 'state="disabled"' not in botao and "def config(" in botao
    assert 'COR_CONECTANDO, COR_ONLINE, COR_OFFLINE = "#f59e0b", "#10b981", "#f43f5e"' in src


def test_apps_atualizados_no_meio_da_sessao():
    # 13/11 (9.15): desligar o Chrome no painel nao tirava o app da tela do
    # cliente (a lista so vinha no login). Agora o servidor manda
    # apps_atualizados e o agente troca a whitelist e refaz a tela de apps
    ns = _carregar("normalizar_whitelist", metodos=("_definir_whitelist", "_apps_atualizados"))

    class Falso:
        sessao_ativa = True
        montou = 0
        _log = staticmethod(lambda *a: None)

        def _montar_launcher(self):
            self.montou += 1

        # 1.27: a troca vai com fade no centro (o veu); aqui troca na hora
        frame_centro = "centro"
        _tela_apps = type("Tela", (), {"animar_entrada": lambda self: None})()

        def _transicao(self, trocar, area=None, **_):
            self.areas.append(area)
            trocar()

    pc = Falso()
    pc.areas = []
    pc._definir_whitelist = ns["_definir_whitelist"].__get__(pc)
    ns["_apps_atualizados"](pc, {"whitelist": [
        {"nome": "Chrome", "processo": "chrome.exe", "caminho": "C:/chrome.exe"},
        {"nome": "Word", "processo": " WINWORD.exe ", "caminho": None}]})
    assert pc.whitelist_procs == {"chrome.exe", "winword.exe"}
    assert pc.montou == 1
    ns["_apps_atualizados"](pc, {"whitelist": [{"nome": "Word", "processo": "winword.exe", "caminho": None}]})
    assert pc.whitelist_procs == {"winword.exe"}  # o Chrome aberto passa a ser fechado
    pc.sessao_ativa = False
    ns["_apps_atualizados"](pc, {"whitelist": []})
    assert pc.whitelist_procs == {"winword.exe"} and pc.montou == 2  # sem sessao: ignora
    assert pc.areas == ["centro", "centro"]  # com fade so no centro, nao na tela toda
    src = _fonte()
    assert 'evento == "apps_atualizados"' in src


def test_menu_lateral_tem_as_categorias():
    # 13/11 (9.16): pedido do Matheus: os filtros (Jogos, Internet, Estudos...)
    # tambem no menu da esquerda, abaixo de Inicio e Meus Apps
    src = _fonte()
    menu = src[src.index("class MenuLateral:"):src.index("class PainelDireito:")]
    assert '"CATEGORIAS"' in menu
    assert "def definir_categorias(" in menu
    assert "icone_da_categoria(" in menu
    assert "acao=self.app._filtrar_categoria" in menu
    tela = src[src.index("class TelaApps:"):src.index("class TelaLogin:")]
    assert "definir_categorias(categorias_da_tela(self.apps)[1:])" in tela  # sem o "Todos"
    escolher = tela[tela.index("    def escolher("):tela.index("    # ── entrada suave")]
    assert "_menu" in escolher  # a pilula escolhida acende tambem no menu
    assert "def _filtrar_categoria(" in src


def test_atualizar_tela_pelo_painel():
    # 13/11 (pedido do Matheus): ao retirar um app no painel, o botao "Atualizar
    # telas" manda a lista nova e o agente refaz a tela sem deslogar o cliente
    ns = _carregar("normalizar_whitelist")
    norm = ns["normalizar_whitelist"]
    assert norm(["chrome.exe"]) == [{"nome": "chrome.exe", "processo": "chrome.exe", "caminho": None}]
    apps = [{"nome": "Chrome", "processo": "chrome.exe", "caminho": "C:/chrome.exe"}]
    assert norm(apps) == apps and norm([]) == []
    src = _fonte()
    assert 'elif evento == "atualizar_tela":' in src
    metodo = src[src.index("    def _atualizar_tela(self, dados):"):src.index("    def _montar_launcher(self):")]
    # a lista vai pelo mesmo caminho do envio automatico (9.15), que fora da
    # sessao nao mexe nos apps: so cartazes e avisos
    assert "self._apps_atualizados(dados)" in metodo


def test_transicao_com_veu():
    # 13/11 (pedido do Matheus): login <-> sessao, secoes do menu e Atualizar tela
    # trocam com fade. O veu (janela por cima) entra, a tela troca uma vez por
    # baixo dele e ele some; nunca fica preso, mesmo com erro na troca.
    import time as _time
    import tkinter as tk
    nomes = ("_suave", "_transicao", "_passo_veu", "_trocar_sob_veu", "_fim_veu")
    ns = _carregar(metodos=nomes)
    ns.update(tk=tk, time=_time)
    App = type("App", (), {n: ns[n] for n in nomes} | {
        "VEU_ENTRA_MS": 60, "VEU_SAI_MS": 80, "VEU_QUADRO_MS": 10, "_log": lambda self, m: self.logs.append(m)})
    app = App()
    app.logs, app.paleta = [], {"fundo": "#09090b"}
    app.root = _tk_raiz()
    try:
        # fora da tela e transparente: nada aparece para quem roda os testes
        app.root.geometry("200x120+-4000+-4000")
        app.root.attributes("-alpha", 0.0)
        app.root.update()

        def esperar_veu(limite=2.0):
            fim = _time.monotonic() + limite
            while getattr(app, "_veu", None) and _time.monotonic() < fim:
                app.root.update()
                _time.sleep(0.005)

        trocas = []
        app._transicao(lambda: trocas.append(1))
        assert trocas == [] and app._veu["top"].winfo_exists()  # primeiro o veu entra
        esperar_veu()
        assert trocas == [1] and app._veu is None
        assert not [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]

        # uma no meio da outra: a primeira troca na hora, a segunda segue com fade
        app._transicao(lambda: trocas.append(2))
        app._transicao(lambda: trocas.append(3))
        assert trocas == [1, 2]
        esperar_veu()
        assert trocas == [1, 2, 3]

        # erro na troca: o veu some do mesmo jeito
        app._transicao(lambda: 1 / 0)
        esperar_veu()
        assert app._veu is None and any("troca de tela" in m for m in app.logs)
        assert not [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]

        # area escondida: troca direto, sem veu
        escondido = tk.Frame(app.root)
        app._transicao(lambda: trocas.append(4), area=escondido)
        assert trocas[-1] == 4 and getattr(app, "_veu", None) is None
    finally:
        import gc
        gc.collect()  # os objetos do Tk somem aqui, com a janela viva (noutra thread derrubam o Python)
        app.root.destroy()

    src = _fonte()
    assert "self._transicao(mostrar_sessao)" in src and "self._transicao(mostrar_login)" in src
    assert "self._transicao(mostrar_encerramento)" in src
    assert "self._transicao(refazer, area=self.frame_centro)" in src


def test_menu_lateral_com_fade():
    # 13/11 (pedido do Matheus): o menu da esquerda com fade suave. O destaque
    # (mouse em cima, pagina escolhida) passa por cores do meio ate chegar; recolher
    # anda a largura aos poucos e termina em 64 px (abrir volta a 240)
    import time as _time
    import tkinter as tk
    import tkinter.font as tkfont
    arvore = ast.parse(_fonte())
    corpo = [no for no in arvore.body if
             (isinstance(no, ast.FunctionDef) and no.name in ("misturar", "_linha_menu")) or
             (isinstance(no, ast.ClassDef) and no.name == "MenuLateral")]
    desenhos = []

    class BarraSessao:
        @staticmethod
        def _retangulo(c, x0, y0, x1, y1, r, **k):
            desenhos.append(k.get("fill"))
            return c.create_rectangle(x0, y0, x1, y1, fill=k.get("fill"), outline="")

    ns = {"tk": tk, "tkfont": tkfont, "time": _time, "BarraSessao": BarraSessao, "FONTE": "Segoe UI",
          "AZUL": "#3b82f6", "AZUL_CLARO": "#60a5fa", "TEXTO_CLARO": "#ffffff"}
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)

    root = _tk_raiz()
    try:
        root.geometry("400x500+-4000+-4000")  # fora da tela e transparente
        root.attributes("-alpha", 0.0)
        app = type("App", (), {})()
        app.root, app._pagina = root, "inicio"
        app.paleta = {"fundo": "#09090b", "borda": "#27272a", "superficie": "#18181b", "texto": "#fafafa",
                      "texto2": "#a1a1aa", "fraco": "#71717a"}
        frame = tk.Frame(root)
        frame.pack(side="left", fill="y")
        menu = ns["MenuLateral"](app, frame)
        root.update()

        def rodar(seg):
            fim = _time.monotonic() + seg
            while _time.monotonic() < fim:
                root.update()
                _time.sleep(0.005)

        rodar(0.1)
        assert menu._nivel["inicio"] == [1.0, 0.0] and menu._nivel["apps"] == [0.0, 0.0]

        # mouse em cima de Meus Apps: o nivel passa pelo meio antes de chegar a 1
        menu.pintar(sobre="apps")
        root.update()
        rodar(0.02)
        meio = menu._nivel["apps"][1]
        assert 0 < meio < 1
        rodar(0.5)
        assert menu._nivel["apps"][1] == 1.0
        menu._saiu("apps")
        rodar(0.5)
        assert menu._nivel["apps"][1] == 0.0

        # trocar de pagina: o destaque azul sai de um e entra no outro em fade
        app._pagina = "apps"
        menu.pintar()
        rodar(0.03)
        assert 0 < menu._nivel["apps"][0] < 1 and 0 < menu._nivel["inicio"][0] < 1
        rodar(0.5)
        assert menu._nivel["apps"][0] == 1.0 and menu._nivel["inicio"][0] == 0.0

        # recolher: larguras do meio, termina em 64 e sem o texto NAVEGACAO
        menu.alternar()
        larguras = set()
        fim = _time.monotonic() + 0.6
        while _time.monotonic() < fim:
            root.update()
            larguras.add(int(frame.cget("width")))
            _time.sleep(0.005)
        assert int(frame.cget("width")) == 64 and menu.abertura == 0.0 and menu.lbl_menu.cget("text") == ""
        assert any(64 < w < 240 for w in larguras)
        menu.alternar()
        rodar(0.6)
        assert int(frame.cget("width")) == 240 and menu.abertura == 1.0
        assert menu.lbl_menu.cget("text") == "NAVEGAÇÃO"
    finally:
        import gc
        menu = app = frame = None
        gc.collect()  # os objetos do Tk somem aqui, com a janela viva (noutra thread derrubam o Python)
        root.destroy()


def _tk_raiz():
    # Neste PC o Windows as vezes nao deixa ler os .tcl do Tk na hora de abrir
    # (antivirus olhando o arquivo): tenta de novo antes de dar erro
    import time as _time
    import tkinter as tk
    for tentativa in range(3):
        try:
            return tk.Tk()
        except tk.TclError:
            if tentativa == 2:
                raise
            _time.sleep(0.5)


def _constantes(*nomes):
    ns = {}
    for no in ast.parse(_fonte()).body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", "") in nomes for t in no.targets):
            exec(compile(ast.Module(body=[no], type_ignores=[]), AGENTE, "exec"), ns)
    return ns


def test_estilos_da_tela_batem_com_o_servidor():
    # 17/11: estilo da tela escolhido por estacao no painel
    from app.estilos import ESTILOS as DO_SERVIDOR
    ns = _constantes("PALETAS", "ESTILOS")
    estilos, chaves = ns["ESTILOS"], set(ns["PALETAS"]["escuro"])
    assert set(estilos) == set(DO_SERVIDOR)
    assert estilos["padrao"] == {}  # o padrao e o visual de hoje, sem trocar nada
    for nome, e in estilos.items():
        for tema, paleta in e.get("paletas", {}).items():
            assert tema in ("escuro", "claro"), nome
            assert set(paleta) == chaves, (nome, tema)
            assert len({v.lower() for v in paleta.values()}) == len(paleta), (nome, tema)


def test_estilo_novo_so_reabre_o_agente_fora_da_sessao():
    fonte = _fonte()
    assert 'evento == "estilo_estacao"' in fonte
    trecho = fonte[fonte.index("    def _aplicar_estilo("):]
    trecho = trecho[:trecho.index("\n    def ", 1)]
    # com cliente usando, so guarda; reabre ao voltar ao login
    assert "self.sessao_ativa" in trecho and "gravar_cfg(ESTILO=" in trecho
    login = fonte[fonte.index("    def _ir_para_login("):]
    login = login[:login.index("\n    def ", 1)]
    assert "_estilo_pendente" in login


def test_caderno_le_os_caminhos_svg_e_escolhe_os_bichinhos():
    # 17/11: estilo Caderno desenha os bichinhos a partir de trechos de SVG
    import math as _math
    import re as _re
    ns = {"re": _re, "math": _math}
    corpo = [no for no in ast.parse(_fonte()).body
             if (isinstance(no, ast.FunctionDef) and no.name in ("_svg_caminho", "_elenco_caderno"))
             or (isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "_SVG_TOKEN" for t in no.targets))]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    # relativo, curva e fechamento
    subs = ns["_svg_caminho"]("M0 0 l10 0 C10 5 5 10 0 10 Z M20 20 L30 20", passos=2)
    assert subs[0][1] is True and subs[0][0][:2] == [(0.0, 0.0), (10.0, 0.0)] and subs[0][0][-1] == (0.0, 10.0)
    assert subs[1] == ([(20.0, 20.0), (30.0, 20.0)], False)
    elenco = ns["_elenco_caderno"](list("AD-10"))
    assert [e[0] for e in elenco] == ["yeti", "bird", "cat"]
    assert all(list("AD-10")[e[1]].isalnum() for e in elenco)  # ninguem sentado no hifen
    assert [e[0] for e in ns["_elenco_caderno"](list("X"))] == ["cat"]
    assert ns["_elenco_caderno"](list("--")) == []


def test_caderno_bichinho_clicado_se_mexe_e_volta_ao_lugar():
    # 18/11: clicar num bichinho do nome carimbado faz ele se mexer
    import math as _math
    ns = {"math": _math}
    corpo = [no for no in ast.parse(_fonte()).body
             if isinstance(no, ast.FunctionDef) and no.name in ("_movimento_bicho", "_bicho_no_ponto")]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    mov = ns["_movimento_bicho"]
    parado = (0, 0, 0, 1, 1)
    for bicho in ("yeti", "bird", "cat", "mushroom"):
        assert tuple(mov(bicho, 0)) == parado and tuple(mov(bicho, 1)) == parado and tuple(mov(bicho, 2)) == parado
        meio = [mov(bicho, k / 20) for k in range(1, 20)]
        assert any(m != parado for m in meio), bicho
    assert min(mov("yeti", k / 20)[1] for k in range(20)) < -5  # pula
    assert min(mov("bird", k / 20)[1] for k in range(20)) < -5  # voa um pouco
    assert any(abs(mov("cat", k / 20)[2]) > 5 for k in range(20))  # balança
    assert min(mov("mushroom", k / 20)[4] for k in range(20)) < 0.95  # amassa
    # o clique cai no bichinho de cima quando as caixas se encostam
    bichos = [{"caixa": (0, 0, 50, 50)}, {"caixa": (40, 10, 90, 60)}]
    assert ns["_bicho_no_ponto"](bichos, 45, 20) == 1
    assert ns["_bicho_no_ponto"](bichos, 5, 5) == 0
    assert ns["_bicho_no_ponto"](bichos, 95, 5) is None


def test_dock_some_com_app_em_tela_cheia():
    # 18/11: o dock ficava por cima de vídeo e de conteúdo em tela cheia
    ns = {}
    corpo = [no for no in ast.parse(_fonte()).body if isinstance(no, ast.FunctionDef) and no.name == "cobre_a_tela"]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    cobre = ns["cobre_a_tela"]
    W, H = 1366, 768
    assert cobre((0, 0, W, H), W, H)  # vídeo em tela cheia
    assert cobre((-2, -2, W + 2, H + 2), W, H)  # com borda sobrando
    assert not cobre((-8, -8, W + 8, H - 40), W, H)  # maximizada: para em cima do dock
    assert not cobre((100, 100, 900, 600), W, H)  # janela comum
    assert not cobre((0, 0, 0, 0), W, H)
    fonte = _fonte()
    manter = fonte[fonte.index("    def manter(self):"):]
    manter = manter[:manter.index("\n    def ", 10)]
    assert "tela_cheia" in manter  # o dock confere antes de voltar para a frente
    # janelas do próprio Windows que cobrem a tela (Iniciar, pesquisa, central) não contam
    funcao = fonte[fonte.index("def app_em_tela_cheia("):]
    funcao = funcao[:funcao.index("\ndef ", 5)]
    assert "Windows.UI.Core.CoreWindow" in funcao and "_camuflada(" in funcao


def test_caderno_linha_tremida_do_dock():
    # 18/11: no Caderno o topo do dock é um traço de tinta tremido, sempre igual
    import math as _math
    ns = {"math": _math}
    corpo = [no for no in ast.parse(_fonte()).body
             if isinstance(no, ast.FunctionDef) and no.name in ("_hash_caderno", "_linha_tremida")]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    linha = ns["_linha_tremida"](0, 1000, 2, amplitude=1.2)
    xs, ys = linha[0::2], linha[1::2]
    assert xs[0] == 0 and xs[-1] == 1000 and xs == sorted(xs) and len(xs) > 20
    assert all(0.8 <= y <= 3.2 for y in ys) and len(set(ys)) > 5  # treme, mas não sai da faixa
    assert linha == ns["_linha_tremida"](0, 1000, 2, amplitude=1.2)  # não pisca entre redesenhos
    fonte = _fonte()
    dock = fonte[fonte.index("class BarraSessao"):fonte.index("class Notificacoes")]
    assert "caderno" in dock and "_linha_tremida(" in dock


def test_caderno_cards_dos_apps():
    # 18/11: no Caderno os cards são papel e tinta; sem capa, cada app ganha um rabisco fixo
    import hashlib as _hashlib
    import math as _math
    ns = {"math": _math, "hashlib": _hashlib}
    corpo = [no for no in ast.parse(_fonte()).body
             if (isinstance(no, ast.FunctionDef) and no.name in ("_hash_caderno", "_rabisco_do_app"))
             or (isinstance(no, ast.Assign) and any(getattr(t, "id", "") in ("_CADERNO_RABISCOS", "_CADERNO_ACENTO")
                                                    for t in no.targets))]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    rabisco = ns["_rabisco_do_app"]
    escolhidos = [rabisco(i) for i in range(12)]
    assert all(r in ns["_CADERNO_RABISCOS"] for r in escolhidos)
    assert escolhidos == [rabisco(i) for i in range(12)]  # sempre o mesmo para o mesmo app
    assert all(a != b for a, b in zip(escolhidos, escolhidos[1:]))  # vizinhos nunca repetem
    assert len(set(escolhidos[:4])) == 4
    fonte = _fonte()
    tela = fonte[fonte.index("class TelaApps"):fonte.index("class TelaLogin")]
    assert "montar_cartao_caderno(" in tela and "caderno" in tela


def test_caderno_menu_da_esquerda_e_painel_da_direita():
    # 18/11: no Caderno o item escolhido do menu tem contorno de tinta e sombra na cor do piso
    import math as _math

    class _Canvas:
        def __init__(self):
            self.poligonos = []

        def delete(self, *a):
            self.poligonos = []

        def config(self, **k):
            pass

        def create_polygon(self, *pts, **k):
            self.poligonos.append(k)

        def create_text(self, *a, **k):
            pass

    ns = {"math": _math}
    corpo = [no for no in ast.parse(_fonte()).body
             if (isinstance(no, ast.FunctionDef) and no.name in ("_linha_menu", "_linha_menu_caderno", "misturar"))
             or (isinstance(no, ast.ClassDef) and no.name == "BarraSessao")
             or (isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "FONTE" for t in no.targets))]
    ns["AZUL"], ns["AZUL_CLARO"] = "#2563eb", "#3b82f6"
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    p = {"fundo": "#ffffff", "superficie": "#fbfaf7", "superficie2": "#f3f1ec", "superficie3": "#d9d5cc",
         "borda": "#e6e2da", "texto": "#0d0d0d", "texto2": "#4d4a45", "fraco": "#8a857c",
         "destaque": "#7c3aed", "destaque_forte": "#6d28d9"}
    cv = _Canvas()
    ns["_linha_menu"](cv, 200, 38, "Início", "x", 1, 1, 0, p, caderno=True)
    cores = [k.get("fill") for k in cv.poligonos]
    assert p["destaque"] in cores and p["texto"] in cores  # sombra na cor do piso e contorno de tinta
    ns["_linha_menu"](cv, 200, 38, "Início", "x", 1, 0, 0, p, caderno=True)
    assert cv.poligonos == []  # parado e não escolhido: só o texto
    ns["_linha_menu"](cv, 200, 38, "Início", "x", 1, 1, 0, p)  # fora do Caderno, nada de tinta
    assert p["texto"] not in [k.get("fill") for k in cv.poligonos]
    fonte = _fonte()
    menu = fonte[fonte.index("class MenuLateral"):fonte.index("class PaginaPreferencias")]
    assert menu.count("caderno") >= 4  # menu (topo e linhas) e painel da direita (card e avisos)


def test_caderno_banner_da_programacao_e_notificacoes():
    # 18/11: no Caderno o banner é uma folha com o cartaz colado; as notificações, em tinta
    fonte = _fonte()
    assert "def montar_banner_caderno(" in fonte
    prog = fonte[fonte.index("class Programacao"):fonte.index("class TelaApps")]
    assert "montar_banner_caderno(" in prog and prog.count("caderno") >= 3  # o banner, os textos e os botões
    # o banner pronto fica guardado por tamanho e cor; o estilo também entra na chave
    quadro = prog[prog.index("    def _quadro("):prog.index("    def _exibir(")]
    assert "caderno" in quadro
    notif = fonte[fonte.index("class Notificacoes"):fonte.index("def montar_banner(")]
    assert notif.count("caderno") >= 2  # cabeçalho/pilha e o cartão


def test_capa_que_o_pillow_nao_le_conta_como_sem_capa():
    # 18/11: capa em SVG (o Pillow não lê) deixava o card sem a inicial grande
    import io as _io

    class _Imagem:
        def __init__(self, dados):
            if dados.lstrip().startswith(b"<svg"):
                raise OSError("cannot identify image file")

        def verify(self):
            pass

    class _Image:
        @staticmethod
        def open(f):
            return _Imagem(f.read())

    ns = {"Image": _Image, "BytesIO": _io.BytesIO}
    corpo = [no for no in ast.parse(_fonte()).body if isinstance(no, ast.FunctionDef) and no.name == "capa_legivel"]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    assert ns["capa_legivel"](b"\x89PNG....") is True
    assert ns["capa_legivel"](b"<svg xmlns='http://www.w3.org/2000/svg'/>") is False
    assert ns["capa_legivel"](None) is False and ns["capa_legivel"](...) is False
    fonte = _fonte()
    cartao = fonte[fonte.index("    def _desenhar_cartao("):fonte.index("    def _sobre(")]
    assert "capa_legivel(" in cartao


def test_caderno_bichinhos_se_mexem_de_leve_o_tempo_todo():
    # 18/11: parados eles respiram/balançam; o clique soma o pulo por cima
    import math as _math
    ns = {"math": _math}
    corpo = [no for no in ast.parse(_fonte()).body
             if isinstance(no, ast.FunctionDef) and no.name in ("_movimento_bicho", "_movimento_parado", "_somar_movimentos")]
    exec(compile(ast.Module(body=corpo, type_ignores=[]), AGENTE, "exec"), ns)
    parado = ns["_movimento_parado"]
    for bicho in ("yeti", "bird", "cat", "mushroom"):
        quadros = [parado(bicho, k * 0.1) for k in range(80)]
        assert len(set(quadros)) > 10, bicho  # mexe
        for dx, dy, giro, sx, sy in quadros:  # mas de leve
            assert abs(dx) <= 3 and abs(dy) <= 4 and abs(giro) <= 5 and 0.94 <= sx <= 1.06 and 0.94 <= sy <= 1.06
    # cada um no seu ritmo
    assert parado("yeti", 1.3) != parado("cat", 1.3)
    soma = ns["_somar_movimentos"]((1, 2, 3, 1.1, 0.9), (1, -2, 1, 1.0, 1.1))
    assert soma[:3] == (2, 0, 4) and abs(soma[3] - 1.1) < 1e-9 and abs(soma[4] - 0.99) < 1e-9
