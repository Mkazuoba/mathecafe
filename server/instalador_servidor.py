"""
MatheCafé - Instalador do SERVIDOR com tela

Vira o MatheCafe-Servidor-Instalador.exe (gerar_instalador_servidor.bat,
PyInstaller): um arquivo só, que pede administrador ao abrir. Usa as mesmas
peças de tela e os mesmos passos de Python do instalador das estações
(agente/instalador.py), no mesmo visual.

  Instalar:    para o servidor (se havia) -> Python (python.org) -> arquivos do
               servidor -> ambiente e bibliotecas -> .env -> banco (backup
               trazido, opcional) e administrador -> tarefa MatheCafe-Servidor
               e firewall -> confere que subiu
  Reinstalar:  o mesmo, por cima: troca só o programa; banco, .env, chave,
               backups e logs ficam (DADOS_PRESERVADOS)
  Desinstalar: tira a tarefa e a regra do firewall e o programa; os dados só
               saem se marcar

  python instalador_servidor.py              de verdade (como admin)
  python instalador_servidor.py --simular    só as telas, sem mexer no Windows
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import filedialog

AQUI = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.join(AQUI, "..", "agente"))
import instalador as base  # noqa: E402  (peças da tela e passos do Python)
from instalador import (AMBAR, BORDA, Botao, Campo, EMERALD_TEXTO, ErroDeInstalacao, FRACO,  # noqa: E402
                        FUNDO, ROSA_TEXTO, SEM_JANELA, SIMULAR, SUPERFICIE, TEXTO, TEXTO2, pedir,
                        sou_administrador)

DESTINO_SERVIDOR = r"C:\MatheCafe\Servidor"
PORTA_PADRAO = 8000
TAREFA = "MatheCafe-Servidor"
NOME_DO_EXE = "MatheCafe-Servidor-Instalador.exe"
# O que a reinstalação troca (o programa) e o que nunca apaga (os dados)
ARQUIVOS_DO_PROGRAMA = ("app", "agente_dist", "main.py", "requirements.txt", "iniciar_servidor.bat",
                        "reiniciar_servidor.bat", "registrar_servidor.ps1", ".env.example",
                        "importar_vscyber.py", "importar_historico.py", "importar_infantil.py")
DADOS_PRESERVADOS = ("cybercafe.db", "cybercafe.db-wal", "cybercafe.db-shm", ".env", ".secret_key",
                     "backups", "logs")


# ════════════════════════════════════════════════════════════════════
#  Regras de dados (testadas em tests/test_instalador_servidor.py)
# ════════════════════════════════════════════════════════════════════

def porta_valida(texto):
    try:
        porta = int(str(texto).strip())
    except ValueError:
        return None
    return porta if 0 < porta < 65536 else None


def problema_no_admin(login, senha, confirmacao):
    login = (login or "").strip()
    if not login:
        return "Escolha o login do administrador."
    if " " in login:
        return "O login não pode ter espaço."
    if len(senha or "") < 10:
        return "A senha precisa de pelo menos 10 caracteres."
    if senha != confirmacao:
        return "As duas senhas não são iguais."
    return None


def conteudo_env(antigo, valores):
    """O .env com as chaves trocadas (None = não mexe), mantendo o resto."""
    linhas = (antigo or "").splitlines()
    pendentes = {k: v for k, v in valores.items() if v is not None}
    saida = []
    for linha in linhas:
        chave = linha.split("=", 1)[0].strip() if "=" in linha and not linha.lstrip().startswith("#") else None
        if chave in pendentes:
            saida.append(f"{chave}={pendentes.pop(chave)}")
        else:
            saida.append(linha)
    saida += [f"{k}={v}" for k, v in pendentes.items()]
    return "\n".join(saida) + "\n" if saida else ""


def enderecos_para_estacoes(ips, porta):
    """Os endereços da rede deste PC (sem o próprio PC e sem APIPA), sem repetir."""
    vistos = []
    for ip in ips:
        if ip.startswith("127.") or ip.startswith("169.254.") or ":" in ip:
            continue
        endereco = f"{ip}:{porta}"
        if endereco not in vistos:
            vistos.append(endereco)
    return vistos


def ler_tarefa(xml):
    """(pasta, porta) da tarefa MatheCafe-Servidor (schtasks /query /xml), ou None."""
    inicio, fim = "<WorkingDirectory>", "</WorkingDirectory>"
    if not xml or inicio not in xml or fim not in xml:
        return None
    pasta = xml.split(inicio, 1)[1].split(fim, 1)[0].strip()
    porta = 8000
    if "PORTA=" in xml:
        numero = ""
        for ch in xml.split("PORTA=", 1)[1]:
            if not ch.isdigit():
                break
            numero += ch
        porta = int(numero) if numero else 8000
    return (pasta, porta) if pasta else None


# ════════════════════════════════════════════════════════════════════
#  Arquivos e Windows
# ════════════════════════════════════════════════════════════════════

def origem_dos_arquivos():
    """Os arquivos do servidor: dentro do .exe ou a pasta server deste repositório."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "servidor")
    return AQUI


def servidor_instalado():
    """(pasta, porta) se a tarefa MatheCafe-Servidor existe neste PC."""
    if SIMULAR:
        return None
    try:
        r = subprocess.run(["schtasks", "/query", "/tn", TAREFA, "/xml"], capture_output=True,
                           creationflags=SEM_JANELA, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    for codificacao in ("utf-16", "utf-8", "mbcs"):
        try:
            return ler_tarefa(r.stdout.decode(codificacao))
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def ips_deste_pc():
    try:
        return [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        return []


# ════════════════════════════════════════════════════════════════════
#  Os passos
# ════════════════════════════════════════════════════════════════════

class ExecucaoServidor(base.Execucao):
    def __init__(self, dados, avisar, simular=False):
        super().__init__(dados, avisar, simular)
        self.destino = (os.path.join(tempfile.gettempdir(), "MatheCafe-Servidor-simulado") if simular
                        else dados["pasta"])

    def parar_servidor(self):
        """A tarefa sobe o servidor de novo se ele cair: termina a tarefa antes."""
        self.rodar(["schtasks", "/end", "/tn", TAREFA])
        self.fechar_o_agente()

    def fechar_o_agente(self):
        """Só o Python desta pasta (o servidor): o próprio instalador pode estar
        rodando daqui (a cópia que fica na pasta) e não pode se encerrar."""
        self.ps(f"Get-Process python, pythonw -ErrorAction SilentlyContinue | "
                f"Where-Object {{ $_.Path -like '{self.destino}\\*' }} | Stop-Process -Force")

    # ── instalar ──
    def passos_instalar(self):
        return [("Python do servidor", self.python_do_servidor),
                ("Arquivos do servidor", self.arquivos_do_servidor),
                ("Ambiente e bibliotecas", self.dependencias),
                ("Configuração (.env)", self.configuracao),
                ("Banco e administrador", self.banco_e_administrador),
                ("Subir sozinho com o Windows e liberar a porta", self.tarefa_e_firewall),
                ("Conferir que o servidor está no ar", self.conferir_no_ar)]

    def python_do_servidor(self):
        os.makedirs(self.destino, exist_ok=True)
        self.parar_servidor()
        self.python_do_agente()  # o mesmo Python do instalador das estações, em <pasta>\python

    def arquivos_do_servidor(self):
        origem = origem_dos_arquivos()
        if os.path.normcase(os.path.abspath(origem)) == os.path.normcase(os.path.abspath(self.destino)):
            self.detalhe("Instalando na própria pasta do programa: nada a copiar")
            return
        if self.simular:
            time.sleep(0.6)
            return
        for nome in ARQUIVOS_DO_PROGRAMA:
            de, para = os.path.join(origem, nome), os.path.join(self.destino, nome)
            if not os.path.exists(de):
                continue
            self.detalhe("Copiando " + nome)
            if os.path.isdir(de):
                shutil.rmtree(para, ignore_errors=True)  # o que saiu da versão nova não fica
                shutil.copytree(de, para, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(de, para)
        # uma cópia do instalador fica na pasta: é por ela que se desinstala
        if getattr(sys, "frozen", False):
            copia = os.path.join(self.destino, NOME_DO_EXE)
            if os.path.normcase(sys.executable) != os.path.normcase(copia):
                try:
                    shutil.copy2(sys.executable, copia)
                except OSError:
                    pass

    def dependencias(self):
        env = dict(os.environ)
        proxy = None if self.simular else self.proxy_do_windows()
        if proxy:
            self.detalhe("Usando o proxy da rede: " + proxy)
            env["HTTPS_PROXY"] = env["HTTP_PROXY"] = proxy
        venv = os.path.join(self.destino, "venv")
        if os.path.exists(venv) and not self.simular:
            shutil.rmtree(venv, ignore_errors=True)
        self.detalhe("Criando o ambiente do servidor")
        codigo, saida = self.rodar([os.path.join(self.destino, "python", "python.exe"), "-m", "venv", venv])
        if codigo != 0:
            raise ErroDeInstalacao(f"Não foi possível criar o ambiente Python em {venv}.\n" + saida.strip()[:300])
        py = os.path.join(venv, "Scripts", "python.exe")
        self.detalhe("Instalando FastAPI, uvicorn, SQLAlchemy e as outras bibliotecas (1 a 3 minutos)")
        self.avisar("progresso_passo", None)
        self.rodar([py, "-m", "pip", "install", "--upgrade", "pip", "-q"], env=env)
        codigo, saida = self.rodar([py, "-m", "pip", "install", "-r",
                                    os.path.join(self.destino, "requirements.txt"), "-q"], env=env)
        if codigo != 0:
            raise ErroDeInstalacao("Falha ao instalar as bibliotecas do servidor.\n"
                                   "Confira a internet deste PC e o proxy da rede.\n" + saida.strip()[-300:])

    def configuracao(self):
        caminho = os.path.join(self.destino, ".env")
        exemplo = os.path.join(self.destino, ".env.example")
        antigo = ""
        for arquivo in (caminho, exemplo):
            try:
                with open(arquivo, encoding="utf-8-sig") as f:
                    antigo = f.read()
                break
            except OSError:
                continue
        valores = {"DATABASE_URL": "sqlite:///./cybercafe.db" if "DATABASE_URL=" not in antigo else None,
                   "BACKUP_COPIA": self.dados.get("copia") or None}
        if self.simular:
            return
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(conteudo_env(antigo, valores))

    def banco_e_administrador(self):
        backup = self.dados.get("backup")
        banco = os.path.join(self.destino, "cybercafe.db")
        if backup:
            self.detalhe("Trazendo o banco de " + backup)
            if not self.simular:
                if os.path.exists(banco):
                    guardado = os.path.join(self.destino, datetime.now().strftime("cybercafe.antes-%Y%m%d-%H%M.db"))
                    os.replace(banco, guardado)
                    self.avisar("aviso", f"O banco que estava aqui foi guardado como {os.path.basename(guardado)}.")
                for resto in ("cybercafe.db-wal", "cybercafe.db-shm"):
                    try:
                        os.remove(os.path.join(self.destino, resto))
                    except OSError:
                        pass
                shutil.copy2(backup, banco)
        login = (self.dados.get("admin_login") or "").strip()
        if not login:
            return
        self.detalhe(f"Criando o administrador {login}")
        env = dict(os.environ, MATHECAFE_SENHA_ADMIN=self.dados["admin_senha"], PYTHONUTF8="1")
        py = os.path.join(self.destino, "venv", "Scripts", "python.exe")
        codigo, saida = self.rodar([py, "-m", "app.cli", "--login", login, "--nome",
                                    self.dados.get("admin_nome") or "Administrador"], env=env, cwd=self.destino)
        if codigo != 0:
            raise ErroDeInstalacao("Não foi possível criar o administrador.\n" + saida.strip()[-300:])

    def tarefa_e_firewall(self):
        codigo, saida = self.ps_arquivo("registrar_servidor.ps1", "-Porta", str(self.dados["porta"]))
        if codigo != 0:
            raise ErroDeInstalacao("Não foi possível criar a tarefa MatheCafe-Servidor.\n" + saida.strip()[-300:])

    def conferir_no_ar(self):
        porta = self.dados["porta"]
        self.detalhe(f"Esperando http://127.0.0.1:{porta}/health")
        if self.simular:
            time.sleep(0.8)
            return
        for i in range(60):
            if pedir(f"http://127.0.0.1:{porta}/health", timeout=2) is not None:
                return
            self.avisar("progresso_passo", i / 60)
            time.sleep(1)
        raise ErroDeInstalacao(f"O servidor não respondeu em 60 s. Veja {self.destino}\\logs\\servidor.log.\n"
                               f"Outro programa pode estar usando a porta {porta}.")

    # ── desinstalar ──
    def passos_desinstalar(self):
        passos = [("Parar o servidor e tirar o início automático", self.tirar_tarefa),
                  ("Apagar o programa", self.apagar_programa)]
        if self.dados.get("apagar_dados"):
            passos.append(("Apagar o banco, os backups e a configuração", self.apagar_dados))
        return passos

    def tirar_tarefa(self):
        self.parar_servidor()
        if os.path.exists(os.path.join(self.destino, "registrar_servidor.ps1")):
            self.ps_arquivo("registrar_servidor.ps1", "-Remover")
        else:
            self.rodar(["schtasks", "/delete", "/tn", TAREFA, "/f"])

    def apagar_programa(self):
        if self.simular:
            time.sleep(0.6)
            return
        for nome in ARQUIVOS_DO_PROGRAMA + ("python", "venv"):
            caminho = os.path.join(self.destino, nome)
            if os.path.isdir(caminho):
                shutil.rmtree(caminho, ignore_errors=True)
            elif os.path.exists(caminho):
                try:
                    os.remove(caminho)
                except OSError:
                    pass

    def apagar_dados(self):
        if self.simular:
            time.sleep(0.6)
            return
        shutil.rmtree(self.destino, ignore_errors=True)
        if os.path.exists(self.destino):
            self.avisar("aviso", f"{self.destino} não saiu inteira (arquivo em uso). Apague à mão.")


# ════════════════════════════════════════════════════════════════════
#  As telas
# ════════════════════════════════════════════════════════════════════

class InstaladorServidor(base.Instalador):
    SUBTITULO = "Instalador do servidor"
    ETAPAS_INSTALAR = ["Início", "Pasta e porta", "Dados", "Administrador", "Instalação", "Pronto"]
    ETAPAS_DESINSTALAR = ["Início", "Confirmar", "Desinstalação", "Pronto"]

    def __init__(self):
        super().__init__()
        self.root.title("MatheCafé - Instalador do servidor" + (" (simulação)" if SIMULAR else ""))

    def nova_execucao(self):
        self.geracao = getattr(self, "geracao", 0) + 1
        geracao = self.geracao
        return ExecucaoServidor(self.dados, lambda *a: self.fila.put((geracao,) + a), simular=SIMULAR)

    def _cartao(self, pai, linhas):
        cartao = tk.Frame(pai, bg=SUPERFICIE, highlightthickness=1, highlightbackground=BORDA)
        cartao.pack(fill="x")
        for chave, valor in linhas:
            linha = tk.Frame(cartao, bg=SUPERFICIE)
            linha.pack(fill="x", padx=18, pady=6)
            tk.Label(linha, text=chave, font=(base.FONTE, 9), fg=TEXTO2, bg=SUPERFICIE, width=12,
                     anchor="w").pack(side="left")
            tk.Label(linha, text=valor, font=(base.FONTE, 10, "bold"), fg=TEXTO, bg=SUPERFICIE).pack(side="left")

    # ── Início ──
    def pagina_inicio(self):
        self.modo = "instalar"
        if not hasattr(self, "servidor"):
            self.servidor = servidor_instalado()  # (pasta, porta) ou None
            pasta, porta = self.servidor or (DESTINO_SERVIDOR, PORTA_PADRAO)
            self.dados = {"pasta": pasta, "porta": porta, "backup": "", "copia": "", "admin_login": "",
                          "admin_nome": "Administrador", "admin_senha": "", "apagar_dados": False}
        if not SIMULAR and not sou_administrador():
            pag = self.nova_pagina(0, "Abra como administrador",
                                   "O instalador grava uma tarefa do Windows e libera a porta no firewall: "
                                   "só funciona como administrador.")
            self.dica(pag, "Feche e abra de novo com o botão direito \u2192 Executar como administrador.", TEXTO2)
            self.botoes(("Fechar", self.root.destroy, "neutro"))
            return
        if self.servidor:
            pag = self.nova_pagina(0, "Este computador já é o servidor do MatheCafé",
                                   "Reinstalar atualiza o programa e mantém o banco, os backups e a configuração.")
            self._cartao(pag, (("Pasta", self.servidor[0]), ("Porta", str(self.servidor[1]))))
            self.botoes(("Reinstalar", self.pagina_pasta, "primario"),
                        ("Desinstalar", self.ir_para_desinstalar, "perigo"))
            return
        pag = self.nova_pagina(0, "Instalar o servidor do MatheCafé",
                               "Este computador vai guardar o banco e atender o painel e as estações.")
        self.lista(pag, ["Instala o servidor numa pasta só dele, com um Python próprio (baixa da internet)",
                         "Pode trazer os dados de outro servidor (um backup do banco)",
                         "Cria o administrador do painel",
                         "Sobe sozinho quando o Windows liga, mesmo sem ninguém entrar, e libera a porta "
                         "no firewall",
                         "No fim mostra o endereço para as estações"])
        self.botoes(("Começar", self.pagina_pasta, "primario"))

    # ── Pasta e porta ──
    def pagina_pasta(self):
        pag = self.nova_pagina(1, "Pasta e porta", "Onde o servidor fica e em que porta as estações o encontram.")
        self.rotulo(pag, "Pasta")
        self.campo_pasta = Campo(pag, self.dados["pasta"], largura=420)
        self.campo_pasta.canvas.pack(anchor="w")
        self.dica(pag, "O banco e os backups ficam nesta pasta. Use um disco fixo deste PC.")
        self.rotulo(pag, "Porta")
        self.campo_porta = Campo(pag, str(self.dados["porta"]), largura=140)
        self.campo_porta.canvas.pack(anchor="w")
        self.dica(pag, "Deixe 8000, a não ser que outro programa já use esta porta.")
        self.lbl_erro = self.dica(pag, "", ROSA_TEXTO, pady=(4, 0))
        self.botoes(("Avançar", self.avancar_pasta, "primario"))
        Botao(self.rodape, "Voltar", self.pagina_inicio, "neutro", largura=110).canvas.pack(side="left")

    def avancar_pasta(self):
        pasta = self.campo_pasta.get().strip().rstrip("\\/")
        porta = porta_valida(self.campo_porta.get())
        if not pasta or not os.path.isabs(pasta) or pasta.startswith("\\\\"):
            self.lbl_erro.config(text="Use uma pasta completa num disco deste PC (ex.: C:\\MatheCafe\\Servidor).")
            return
        if porta is None:
            self.lbl_erro.config(text="Porta inválida (um número de 1 a 65535).")
            return
        self.dados.update(pasta=pasta, porta=porta)
        self.pagina_dados()

    # ── Dados ──
    def tem_banco(self):
        return not SIMULAR and os.path.exists(os.path.join(self.dados["pasta"], "cybercafe.db"))

    def pagina_dados(self):
        pag = self.nova_pagina(2, "Dados", "Opcional: trazer o banco de outro servidor e ligar a cópia extra "
                                           "do backup.")
        self.rotulo(pag, "Trazer um backup do banco")
        linha = tk.Frame(pag, bg=FUNDO)
        linha.pack(anchor="w", fill="x")
        Botao(linha, "Escolher arquivo", self.escolher_backup, "neutro", largura=160).canvas.pack(side="left")
        Botao(linha, "Sem backup", self.sem_backup, "neutro", largura=130).canvas.pack(side="left", padx=(10, 0))
        self.lbl_backup = self.dica(pag, "")
        self.mostrar_backup()
        self.rotulo(pag, "Cópia extra do backup (opcional)")
        self.campo_copia = Campo(pag, self.dados["copia"], largura=420)
        self.campo_copia.canvas.pack(anchor="w")
        self.dica(pag, "Outra pasta para cada backup diário: outro disco ou pasta de rede com o caminho completo "
                       "(ex.: \\\\outro-pc\\backup-mathecafe). Dá para ligar depois no painel.")
        self.botoes(("Avançar", self.avancar_dados, "primario"))
        Botao(self.rodape, "Voltar", self.pagina_pasta, "neutro", largura=110).canvas.pack(side="left")

    def escolher_backup(self):
        arquivo = filedialog.askopenfilename(parent=self.root, title="Backup do banco do MatheCafé",
                                             filetypes=[("Banco do MatheCafé", "*.db"), ("Todos", "*.*")])
        if arquivo:
            self.dados["backup"] = os.path.normpath(arquivo)
            self.mostrar_backup()

    def sem_backup(self):
        self.dados["backup"] = ""
        self.mostrar_backup()

    def mostrar_backup(self):
        if self.dados["backup"]:
            texto = "\u25CF  " + self.dados["backup"]
            if self.tem_banco():
                texto += "\nO banco que já está na pasta é guardado com outro nome e substituído por este."
            self.lbl_backup.config(text=texto, fg=AMBAR if self.tem_banco() else EMERALD_TEXTO)
        elif self.tem_banco():
            self.lbl_backup.config(text="Sem backup: continua com o banco que já está na pasta.", fg=TEXTO2)
        else:
            self.lbl_backup.config(text="Sem backup: o servidor começa vazio (pisos, mapas e clientes "
                                        "cadastrados depois no painel).", fg=FRACO)

    def avancar_dados(self):
        self.dados["copia"] = self.campo_copia.get().strip()
        self.pagina_admin()

    # ── Administrador ──
    def admin_obrigatorio(self):
        return not self.dados["backup"] and not self.tem_banco()

    def pagina_admin(self):
        obrigatorio = self.admin_obrigatorio()
        pag = self.nova_pagina(3, "Administrador do painel",
                               "Quem entra no painel com todas as permissões." if obrigatorio else
                               "Opcional: o banco já tem os administradores. Preencha só para criar um novo "
                               "ou trocar a senha de um login que já existe.")
        self.rotulo(pag, "Login")
        self.campo_login = Campo(pag, self.dados["admin_login"], largura=300)
        self.campo_login.canvas.pack(anchor="w", pady=(0, 10))
        self.rotulo(pag, "Nome")
        self.campo_nome_admin = Campo(pag, self.dados["admin_nome"], largura=300)
        self.campo_nome_admin.canvas.pack(anchor="w", pady=(0, 10))
        self.rotulo(pag, "Senha (10 caracteres ou mais)")
        self.campo_senha = Campo(pag, "", senha=True, largura=300)
        self.campo_senha.canvas.pack(anchor="w", pady=(0, 10))
        self.rotulo(pag, "Repita a senha")
        self.campo_senha2 = Campo(pag, "", senha=True, largura=300)
        self.campo_senha2.canvas.pack(anchor="w")
        self.lbl_erro = self.dica(pag, "", ROSA_TEXTO, pady=(8, 0))
        self.botoes(("Instalar", self.comecar_instalacao, "primario"))
        Botao(self.rodape, "Voltar", self.pagina_dados, "neutro", largura=110).canvas.pack(side="left")
        self.campo_login.entry.focus_set()

    def comecar_instalacao(self):
        login, senha = self.campo_login.get().strip(), self.campo_senha.get()
        if login or senha or self.admin_obrigatorio():
            problema = problema_no_admin(login, senha, self.campo_senha2.get())
            if problema:
                self.lbl_erro.config(text=problema)
                return
        self.dados.update(admin_login=login, admin_senha=senha,
                          admin_nome=self.campo_nome_admin.get().strip() or "Administrador")
        self.execucao = self.nova_execucao()
        self.pagina_execucao(4, "Instalando", "Pode levar alguns minutos (o Python e as bibliotecas vêm da "
                                              "internet). As estações seguem a sessão enquanto isso.",
                             self.execucao.passos_instalar(), self.pagina_pronto)

    def comecar_instalacao_de_novo(self):
        self.execucao = self.nova_execucao()
        self.pagina_execucao(4, "Instalando", "Os passos que já estavam prontos são refeitos sem problema.",
                             self.execucao.passos_instalar(), self.pagina_pronto)

    # ── Pronto ──
    def pagina_pronto(self):
        porta = self.dados["porta"]
        pag = self.nova_pagina(5, "Servidor no ar", f"O painel abre em http://127.0.0.1:{porta} neste PC.")
        enderecos = enderecos_para_estacoes(ips_deste_pc(), porta)
        self.rotulo(pag, "Endereço para as estações")
        self._cartao(pag, [("Endereço", e) for e in enderecos] or [("Endereço", f"(IP deste PC):{porta}")])
        passos = ["Use este endereço no instalador das estações (ou no servidor.txt ao lado dele)",
                  "Estações que já existem: manutenção (Ctrl+Shift+M) \u2192 Configurar conexão",
                  f"Para desinstalar ou reinstalar: {self.dados['pasta']}\\{NOME_DO_EXE} (como administrador)"]
        tk.Frame(pag, bg=FUNDO, height=12).pack()
        self.lista(pag, passos, cor=EMERALD_TEXTO)
        if len(enderecos) > 1:
            self.dica(pag, "Este PC tem mais de uma rede: use o endereço da rede das estações.", AMBAR, pady=(10, 0))
        if self.avisos:
            self.dica(pag, "\n".join("\u26A0  " + a for a in self.avisos), AMBAR, pady=(12, 0))
        self.botoes(("Abrir o painel", lambda: webbrowser.open(f"http://127.0.0.1:{porta}"), "primario"),
                    ("Fechar", self.root.destroy, "neutro"))

    # ── Desinstalar ──
    def ir_para_desinstalar(self):
        self.modo = "desinstalar"
        self.pagina_confirmar()

    def pagina_confirmar(self):
        pasta = self.dados["pasta"]
        pag = self.nova_pagina(1, "Desinstalar o servidor", f"Pasta: {pasta}")
        self.dica(pag, "Isto tira deste computador:", TEXTO2, pady=(0, 6))
        self.lista(pag, ["O início automático do servidor (tarefa MatheCafe-Servidor) e a regra do firewall",
                         "O programa (o Python e o código do servidor)"], cor=ROSA_TEXTO)
        self.dica(pag, "O banco, os backups e a configuração ficam na pasta, a não ser que marque abaixo. "
                       "Sem o servidor, as estações não liberam ninguém.", pady=(14, 10))
        self.var_dados = tk.BooleanVar(value=False)
        tk.Checkbutton(pag, text="Apagar também o banco (clientes, históricos) e os backups",
                       variable=self.var_dados, font=(base.FONTE, 10), fg=ROSA_TEXTO, bg=FUNDO,
                       selectcolor=SUPERFICIE, activebackground=FUNDO, activeforeground=TEXTO).pack(anchor="w")
        self.var_entendi = tk.BooleanVar(value=False)
        tk.Checkbutton(pag, text="Entendi: o servidor para e as estações ficam sem servidor",
                       variable=self.var_entendi, command=lambda: self.btn_desinstalar.config(
                           ativo=self.var_entendi.get()), font=(base.FONTE, 10), fg=TEXTO, bg=FUNDO,
                       selectcolor=SUPERFICIE, activebackground=FUNDO, activeforeground=TEXTO).pack(anchor="w")
        self.btn_desinstalar, = self.botoes(("Desinstalar", self.comecar_desinstalacao, "perigo"))
        self.btn_desinstalar.config(ativo=False)
        base_botao = Botao(self.rodape, "Voltar", self.pagina_inicio, "neutro", largura=110)
        base_botao.canvas.pack(side="left")

    def comecar_desinstalacao(self):
        self.dados["apagar_dados"] = self.var_dados.get() if hasattr(self, "var_dados") else False
        self.execucao = self.nova_execucao()
        self.pagina_execucao(2, "Desinstalando", "Parando o servidor e apagando o programa.",
                             self.execucao.passos_desinstalar(), self.pagina_desinstalado)

    def pagina_desinstalado(self):
        pag = self.nova_pagina(3, "Desinstalado", "O servidor do MatheCafé saiu deste computador.")
        itens = (["O banco e os backups foram apagados"] if self.dados.get("apagar_dados") else
                 [f"O banco e os backups continuam em {self.dados['pasta']}: reinstalar volta com eles"])
        self.lista(pag, itens, cor=EMERALD_TEXTO)
        if self.avisos:
            self.dica(pag, "\n".join("\u26A0  " + a for a in self.avisos), AMBAR, pady=(16, 0))
        self.botoes(("Fechar", self.root.destroy, "neutro"))


if __name__ == "__main__":
    InstaladorServidor().rodar()
