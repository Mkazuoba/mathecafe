"""Instalador com tela (10.11): agente/instalador.py vira o MatheCafe-Instalador.exe.
As regras de dados sao testadas tiradas do codigo-fonte (como no test_agente):
o instalador nao e importado para nao abrir janela nem mexer no Windows."""
import ast
import os

INSTALADOR = os.path.join(os.path.dirname(__file__), "..", "..", "agente", "instalador.py")
BAT = os.path.join(os.path.dirname(__file__), "..", "..", "agente", "instalar.bat")


def _fonte(caminho=INSTALADOR):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _carregar(*nomes):
    arvore = ast.parse(_fonte())
    corpo = [no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name in nomes]
    assert {no.name for no in corpo} == set(nomes), "funcao sumiu do instalador.py"
    ns = {}
    exec(compile(ast.Module(body=corpo, type_ignores=[]), INSTALADOR, "exec"), ns)
    return ns


def test_endereco_do_servidor_aceita_protocolo_e_barra():
    norm = _carregar("normalizar_endereco")["normalizar_endereco"]
    assert norm(" 10.26.31.77:8000 ") == "10.26.31.77:8000"
    assert norm("http://10.26.31.77:8000/") == "10.26.31.77:8000"
    assert norm("ws://10.26.31.77:8000") == "10.26.31.77:8000"
    assert norm("https://servidor.local") == "servidor.local"
    assert norm("") == ""


def test_nome_da_estacao():
    nome = _carregar("nome_da_estacao")["nome_da_estacao"]
    assert nome("", "PC-BIBLIO") == "PC-BIBLIO"  # vazio: o nome do Windows
    assert nome("  AD-01 ", "X") == "AD-01"
    assert len(nome("A" * 40, "X")) == 20  # o servidor guarda ate 20


def test_pisos_do_servidor():
    ler = _carregar("ler_pisos")["ler_pisos"]
    assert ler("1;Adulto\n2;Infantil\n") == [("1", "Adulto"), ("2", "Infantil")]
    assert ler("") == []
    assert ler("lixo\n3;Terraço\n") == [("3", "Terraço")]


def test_agente_cfg_mantem_o_id_na_reinstalacao():
    ns = _carregar("conteudo_cfg", "ler_cfg", "id_para_manter")
    cfg = ns["conteudo_cfg"]("10.26.31.77:8000", "AD-01", "abc-123", "2")
    lido = ns["ler_cfg"](cfg)
    assert lido == {"SERVIDOR": "ws://10.26.31.77:8000", "ESTACAO": "AD-01", "ID": "abc-123", "PISO": "2"}
    assert "ID=" not in ns["conteudo_cfg"]("x:1", "AD-01", None, None)
    manter = ns["id_para_manter"]
    assert manter("abc", "2", "2;AD-01") == "abc"  # mesmo piso: continua a mesma estacao
    assert manter("abc", "1", "2;AD-01") is None  # 10.13: outro piso entra como PC novo
    assert manter("abc", "1", "") == "abc"  # o servidor nao conhece: mantem
    assert manter(None, "1", "2;AD-01") is None


def test_senha_do_cliente():
    conferir = _carregar("problema_na_senha")["problema_na_senha"]
    assert conferir("", "") == "Escolha uma senha para o usuário cliente."
    assert conferir("abc1", "abc2") == "As duas senhas não são iguais."
    assert conferir("abc1", "abc1") is None


def test_instalador_faz_os_mesmos_passos_do_bat():
    # o .exe substitui o instalar.bat: nenhum passo pode ficar para tras
    src = _fonte()
    for trecho in ("PasswordNeverExpires", "AutoAdminLogon", "DefaultPassword", "registrar_tarefa.ps1",
                   "registrar_politicas.ps1", "politicas_cliente.ps1", "MC_SENHA", "icacls",
                   "/api/agente/pisos", "/api/agente/estacao?id=", "/api/agente/download", "/health",
                   "Include_tcltk=1", "PY_VERSAO", "-m\", \"venv", "requirements.txt"):
        assert trecho in src, trecho
    assert _fonte(BAT).count("set PY_VERSAO=") == 1
    versao_bat = _fonte(BAT).split("set PY_VERSAO=")[1].split()[0]
    assert f'PY_VERSAO = "{versao_bat}"' in src  # a mesma versao do Python nos dois


def test_desinstalador_faz_os_mesmos_passos_do_bat():
    src = _fonte()
    for trecho in ('"/delete", "/tn", "MatheCafe-Agente"', "MatheCafe-Politicas", "Win32_UserProfile",
                   '"net", "user", "cliente", "/delete"', "QuietUninstallString"):
        assert trecho in src, trecho


def test_simulacao_nao_mexe_no_windows():
    # --simular (para conferir as telas) troca cada passo por uma espera
    src = _fonte()
    assert '"--simular"' in src
    rodar = src[src.index("def rodar(self, comando"):]
    rodar = rodar[:rodar.index("\n    def ", 1)]
    assert "if self.simular:" in rodar
