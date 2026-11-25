"""Instalador do servidor com tela: server/instalador_servidor.py vira o
MatheCafe-Servidor-Instalador.exe. As regras de dados sao tiradas do
codigo-fonte (o instalador nao e importado: abriria janela e mexeria no Windows)."""
import ast
import os

INSTALADOR = os.path.join(os.path.dirname(__file__), "..", "instalador_servidor.py")
GERAR = os.path.join(os.path.dirname(__file__), "..", "gerar_instalador_servidor.bat")


def _fonte(caminho=INSTALADOR):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _carregar(*nomes):
    arvore = ast.parse(_fonte())
    corpo = [no for no in arvore.body
             if (isinstance(no, ast.FunctionDef) and no.name in nomes)
             or (isinstance(no, ast.Assign) and any(getattr(t, "id", "") in nomes for t in no.targets))]
    achados = {no.name if isinstance(no, ast.FunctionDef) else no.targets[0].id for no in corpo}
    assert achados == set(nomes), "sumiu do instalador_servidor.py: " + str(set(nomes) - achados)
    ns = {"os": os}
    exec(compile(ast.Module(body=corpo, type_ignores=[]), INSTALADOR, "exec"), ns)
    return ns


def test_porta():
    porta = _carregar("porta_valida")["porta_valida"]
    assert porta(" 8000 ") == 8000 and porta("80") == 80
    assert porta("") is None and porta("abc") is None and porta("0") is None and porta("70000") is None


def test_administrador():
    problema = _carregar("problema_no_admin")["problema_no_admin"]
    assert problema("admin", "senha-forte-1", "senha-forte-1") is None
    assert "login" in problema("", "senha-forte-1", "senha-forte-1").lower()
    assert "10" in problema("admin", "curta", "curta")
    assert "iguais" in problema("admin", "senha-forte-1", "senha-forte-2")
    assert "espa" in problema("meu admin", "senha-forte-1", "senha-forte-1").lower()


def test_env_mantem_o_que_ja_existia():
    env = _carregar("conteudo_env")["conteudo_env"]
    antigo = "# comentario\nSECRET_KEY=\nBACKUP_DIAS=30\nBACKUP_COPIA=\\velho\pasta\n"
    novo = env(antigo, {"BACKUP_COPIA": "\\nas\backup", "DATABASE_URL": "sqlite:///./cybercafe.db"})
    linhas = novo.splitlines()
    assert "# comentario" in linhas and "BACKUP_DIAS=30" in linhas  # o resto fica
    assert "BACKUP_COPIA=\\nas\backup" in linhas and "BACKUP_COPIA=\\velho\pasta" not in linhas
    assert "DATABASE_URL=sqlite:///./cybercafe.db" in linhas  # chave nova vai no fim
    assert env("", {"X": "1"}) == "X=1\n"
    # None: nao mexe na chave
    assert "BACKUP_DIAS=30" in env(antigo, {"BACKUP_DIAS": None}).splitlines()


def test_endereco_para_as_estacoes():
    enderecos = _carregar("enderecos_para_estacoes")["enderecos_para_estacoes"]
    ips = ["127.0.0.1", "169.254.10.2", "10.26.31.50", "192.168.0.7", "10.26.31.50"]
    assert enderecos(ips, 8000) == ["10.26.31.50:8000", "192.168.0.7:8000"]
    assert enderecos(["127.0.0.1"], 8001) == []


def test_reinstalar_nao_apaga_os_dados():
    ns = _carregar("ARQUIVOS_DO_PROGRAMA", "DADOS_PRESERVADOS")
    programa, dados = set(ns["ARQUIVOS_DO_PROGRAMA"]), set(ns["DADOS_PRESERVADOS"])
    assert {"app", "agente_dist", "requirements.txt", "iniciar_servidor.bat", "registrar_servidor.ps1",
            "reiniciar_servidor.bat", ".env.example"} <= programa
    assert {"cybercafe.db", ".env", ".secret_key", "backups", "logs"} <= dados
    assert not programa & dados


def test_passos_e_build():
    src = _fonte()
    for passo in ("python_do_servidor", "arquivos_do_servidor", "dependencias", "configuracao",
                  "banco_e_administrador", "tarefa_e_firewall", "conferir_no_ar"):
        assert f"def {passo}(" in src
    # para o servidor antes de trocar os arquivos (a tarefa o subiria de novo)
    assert "schtasks" in src and "/end" in src
    # admin criado sem a senha na linha de comando
    assert "MATHECAFE_SENHA_ADMIN" in src
    gerar = _fonte(GERAR)
    assert "instalador_servidor.py" in gerar and "--uac-admin" in gerar and "--paths" in gerar
    for item in ("app", "agente_dist", "registrar_servidor.ps1", "iniciar_servidor.bat"):
        assert item in gerar


def test_descobre_a_instalacao_pela_tarefa():
    # a tarefa MatheCafe-Servidor guarda a pasta e a porta: e assim que o
    # instalador sabe que o servidor ja esta neste PC (e onde)
    ler = _carregar("ler_tarefa")["ler_tarefa"]
    xml = """<?xml version="1.0" encoding="UTF-16"?><Task><Actions Context="Author"><Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c set "PORTA=8010" &amp;&amp; "D:\MatheCafe\Servidor\iniciar_servidor.bat"</Arguments>
      <WorkingDirectory>D:\MatheCafe\Servidor</WorkingDirectory></Exec></Actions></Task>"""
    assert ler(xml) == ("D:\MatheCafe\Servidor", 8010)
    assert ler("") is None and ler("<Task></Task>") is None
    sem_porta = xml.replace('set "PORTA=8010" &amp;&amp; ', "")
    assert ler(sem_porta) == ("D:\MatheCafe\Servidor", 8000)
