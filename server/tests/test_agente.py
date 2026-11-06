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
    assert paletas["escuro"]["fundo"] == "#0f1117"  # o escuro continua como era


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
