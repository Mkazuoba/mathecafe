@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo   MatheCafe - Instalador do Agente
echo ============================================================
echo.
echo Este instalador vai:
echo   1. Criar o usuario Windows "cliente" (autologin)
echo   2. Copiar o agente para C:\MatheCafe, baixar e instalar o Python do
echo      agente e as dependencias (precisa de internet)
echo   3. Configurar o agente para abrir sozinho no login do "cliente"
echo   4. Ligar esta estacao ao servidor: ela aparece no painel em
echo      Mapa -^> Novas estacoes, para um admin aprovar
echo.
echo Rode como Administrador. Se ainda nao fez isso, feche e
echo clique com botao direito -^> Executar como administrador.
echo.

:: Verificar se e administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este arquivo como Administrador.
    pause
    exit /b 1
)

:: ---- Caminhos ----
set ORIGEM=%~dp0
set DESTINO=C:\MatheCafe

if not exist "%ORIGEM%agente.py" (
    echo ERRO: agente.py nao encontrado em %ORIGEM%
    pause
    exit /b 1
)

:: ---- Python do agente ----
:: O agente usa um Python so dele, em %DESTINO%\python (com Tkinter), baixado
:: do python.org na etapa 3 se ainda nao estiver la. Nao mexe em outro Python
:: da maquina. Para trocar a versao, mude PY_VERSAO (ver python.org/downloads).
set PY_VERSAO=3.13.17

:: ---- Coletar dados ----
echo.
echo ---- Dados da estacao ----
echo.

:: Enter vazio = o nome do Windows. O nome pode ser trocado depois no painel.
set ESTACAO=
set /p ESTACAO="Nome da estacao [Enter = %COMPUTERNAME%]: "
if "!ESTACAO!"=="" set ESTACAO=%COMPUTERNAME%
:: o servidor guarda ate 20 caracteres
set ESTACAO=!ESTACAO:~0,20!

:: Endereco sugerido: a 1a linha do servidor.txt ao lado deste instalador
:: (troque la se o servidor mudar de IP). Enter vazio = ele.
set SERVIDOR_PADRAO=
if exist "%ORIGEM%servidor.txt" set /p SERVIDOR_PADRAO=<"%ORIGEM%servidor.txt"
if defined SERVIDOR_PADRAO set SERVIDOR_PADRAO=!SERVIDOR_PADRAO: =!

:pedir_servidor
set SERVIDOR=
if defined SERVIDOR_PADRAO (
    set /p SERVIDOR="Endereco do servidor [Enter = !SERVIDOR_PADRAO!]: "
    if "!SERVIDOR!"=="" set SERVIDOR=!SERVIDOR_PADRAO!
) else (
    set /p SERVIDOR="Endereco do servidor (IP:porta, ex: 10.26.31.77:8000): "
)
if "!SERVIDOR!"=="" (
    echo Informe o endereco do servidor.
    goto pedir_servidor
)
:: Aceita o endereco com ou sem protocolo e barra no fim
set SERVIDOR=!SERVIDOR: =!
set SERVIDOR=!SERVIDOR:https://=!
set SERVIDOR=!SERVIDOR:http://=!
set SERVIDOR=!SERVIDOR:wss://=!
set SERVIDOR=!SERVIDOR:ws://=!
if "!SERVIDOR:~-1!"=="/" set SERVIDOR=!SERVIDOR:~0,-1!

:: Confere agora se o servidor responde: endereco errado nao da erro nenhum
:: depois, o PC so nunca aparece no painel. --noproxy: a rede tem proxy.
echo Testando a conexao com o servidor !SERVIDOR!...
set SERVIDOR_OK=
curl -s -f -m 5 --noproxy "*" -o nul "http://!SERVIDOR!/health"
if errorlevel 1 (
    echo.
    echo ATENCAO: o servidor nao respondeu em http://!SERVIDOR!
    echo Confira o endereco, se o servidor esta ligado e se este PC esta na rede.
    set RESPOSTA=
    set /p RESPOSTA="Digitar o endereco de novo [Enter] ou continuar assim mesmo [C]? "
    if /i not "!RESPOSTA!"=="C" goto pedir_servidor
    echo Continuando: o PC aparece no painel quando conseguir falar com o servidor.
) else (
    echo   O servidor respondeu.
    set SERVIDOR_OK=1
)

:: ---- Piso (6.18) ----
:: O mesmo nome pode existir no Adulto e no Infantil: o piso diz de qual mapa
:: e este PC. Se o mapa do piso ja tem uma estacao com esse nome, o PC entra
:: direto nela; senao espera em Mapa -^> Novas estacoes. Sem servidor, sem piso.
set PISO=
if defined SERVIDOR_OK call :escolher_piso

echo.
echo ---- Conta Windows do cliente ----
echo (Esta conta loga automaticamente quando o PC liga)
echo.

set /p SENHA_CLIENTE="Senha para o usuario 'cliente': "
if "!SENHA_CLIENTE!"=="" (
    echo ERRO: Senha nao pode ser vazia.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Iniciando instalacao...
echo ============================================================
echo.

:: ---- 1. Criar usuario cliente ----
echo [1/6] Criando usuario Windows "cliente"...
net user cliente >nul 2>&1
if %errorlevel%==0 (
    echo       Usuario ja existe. Atualizando senha...
    net user cliente "!SENHA_CLIENTE!" >nul
) else (
    net user cliente "!SENHA_CLIENTE!" /add /fullname:"Cliente" /comment:"Usuario restrito MatheCafe" >nul
    if !errorlevel! neq 0 (
        echo ERRO: Nao foi possivel criar o usuario cliente.
        pause
        exit /b 1
    )
    echo       Usuario "cliente" criado.
)
:: Senha do cliente nao expira (senao o autologin para de funcionar)
powershell -NoProfile -Command "Set-LocalUser -Name cliente -PasswordNeverExpires $true" >nul 2>&1

:: Remover do grupo Administradores (garantia)
net localgroup Administradores cliente /delete >nul 2>&1
net localgroup Administrators cliente /delete >nul 2>&1

:: ---- 2. Configurar autologin ----
echo [2/6] Configurando autologin...
set WINLOGON=HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon
reg add "%WINLOGON%" /v AutoAdminLogon    /t REG_SZ /d "1"          /f >nul
reg add "%WINLOGON%" /v DefaultUserName   /t REG_SZ /d "cliente"    /f >nul
reg add "%WINLOGON%" /v DefaultPassword   /t REG_SZ /d "!SENHA_CLIENTE!" /f >nul
reg add "%WINLOGON%" /v DefaultDomainName /t REG_SZ /d "."          /f >nul
echo       Autologin configurado.

:: ---- 3. Copiar o agente e instalar dependencias ----
echo [3/6] Copiando o agente para %DESTINO% e instalando dependencias...
if not exist "%DESTINO%" mkdir "%DESTINO%"
:: Reinstalacao: fecha o agente que esteja rodando de %DESTINO% (prende os arquivos)
powershell -NoProfile -Command "Get-Process | Where-Object { $_.Path -like '%DESTINO%\*' } | Stop-Process -Force" >nul 2>&1
call :preparar_proxy
call :python_do_agente
if errorlevel 1 (
    pause
    exit /b 1
)
if /i not "%ORIGEM%"=="%DESTINO%\" (
    for %%f in (agente.py requirements.txt iniciar.bat registrar_tarefa.ps1 registrar_politicas.ps1 politicas_cliente.ps1 desinstalar.bat) do (
        copy /y "%ORIGEM%%%f" "%DESTINO%\" >nul
    )
)
if exist "%DESTINO%\venv" rmdir /s /q "%DESTINO%\venv"
"%DESTINO%\python\python.exe" -m venv "%DESTINO%\venv"
if !errorlevel! neq 0 (
    echo ERRO: Nao foi possivel criar o ambiente Python em %DESTINO%\venv.
    pause
    exit /b 1
)
"%DESTINO%\venv\Scripts\python.exe" -m pip install --upgrade pip -q
"%DESTINO%\venv\Scripts\python.exe" -m pip install -r "%DESTINO%\requirements.txt" -q
if !errorlevel! neq 0 (
    echo ERRO: Falha ao instalar as dependencias ^(websockets, psutil, Pillow^).
    echo Confira a internet deste PC e o proxy da rede.
    pause
    exit /b 1
)
echo       Agente e dependencias instalados.

:: ---- 4. Gravar agente.cfg e permissoes ----
echo [4/6] Salvando configuracao do agente...
:: Reinstalacao: mantem o ID= do agente.cfg antigo. E por ele que o servidor
:: reconhece este PC; sem ele, o PC voltaria como uma estacao nova a aprovar.
set ID_PC=
if exist "%DESTINO%\agente.cfg" (
    for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"ID=" "%DESTINO%\agente.cfg"') do set ID_PC=%%b
)
:: Reinstalacao escolhendo OUTRO piso: o ID antigo prenderia o PC a estacao do
:: piso anterior (o servidor reconhece pelo ID antes de olhar o piso). Pergunta
:: ao servidor que estacao este ID e hoje; com o piso diferente, sem o ID.
if defined ID_PC if defined PISO if defined SERVIDOR_OK call :conferir_piso_do_id
(
    echo # MatheCafe - configuracao da estacao ^(gerado automaticamente^)
    echo SERVIDOR=ws://!SERVIDOR!
    echo ESTACAO=!ESTACAO!
    if defined ID_PC echo ID=!ID_PC!
    if defined PISO echo PISO=!PISO!
) > "%DESTINO%\agente.cfg"
:: O agente roda como "cliente" e precisa gravar na pasta: agente.cfg e o
:: auto-update (substitui o proprio agente.py)
icacls "%DESTINO%" /grant cliente:(OI)(CI)M /T /Q >nul
echo       agente.cfg salvo em %DESTINO%

:: ---- 5. Criar tarefa agendada ----
echo [5/6] Criando tarefa agendada...
powershell -NoProfile -ExecutionPolicy Bypass -File "%DESTINO%\registrar_tarefa.ps1" -Pasta "%DESTINO%"
if !errorlevel! neq 0 (
    echo ERRO: Nao foi possivel criar a tarefa agendada.
    pause
    exit /b 1
)
echo       O agente abre sozinho quando o "cliente" entrar no Windows.

:: ---- 6. Politicas do cliente ----
:: Ctrl+Alt+Del nao passa pelo agente: desliga Gerenciador de Tarefas,
:: Bloquear e Alterar senha no perfil do "cliente"
echo [6/6] Bloqueando o Gerenciador de Tarefas para o "cliente"...
:: A tarefa grava as politicas a cada logon do cliente (como SYSTEM, com o
:: perfil dele carregado): valem mesmo se a gravacao abaixo falhar
powershell -NoProfile -ExecutionPolicy Bypass -File "%DESTINO%\registrar_politicas.ps1" -Pasta "%DESTINO%"
if !errorlevel! neq 0 (
    echo ERRO: Nao foi possivel criar a tarefa das politicas ^(Ctrl+Alt+Del^).
    pause
    exit /b 1
)
:: E grava ja agora, se o perfil do cliente puder ser aberto
set MC_SENHA=!SENHA_CLIENTE!
powershell -NoProfile -ExecutionPolicy Bypass -File "%DESTINO%\politicas_cliente.ps1" >nul 2>&1
if !errorlevel! neq 0 (
    echo       As politicas entram no primeiro logon do "cliente" ^(pela tarefa^).
) else (
    echo       Politicas gravadas.
)
set MC_SENHA=

:fim
echo.
echo ============================================================
echo   Instalacao concluida!
echo ============================================================
echo.
echo Proximos passos:
echo   - Reinicie o PC: ele entra sozinho como "cliente" e o agente abre
echo   - No painel, em Mapa -^> Novas estacoes, aprove "!ESTACAO!" e escolha o mapa
echo     ^(ate aprovar, ninguem faz login neste PC^)
echo   - Agente instalado em %DESTINO% (pode apagar esta pasta de origem)
echo   - Para desinstalar: %DESTINO%\desinstalar.bat como Administrador
echo.
pause
exit /b 0

:: ============================================================
:: Sub-rotinas (call :nome)
:: ============================================================

:conferir_piso_do_id
:: O servidor responde "piso_id;nome" (ou nada, se nao conhece este ID)
set PISO_ATUAL=
set NOME_ATUAL=
for /f "usebackq tokens=1,* delims=;" %%a in (`curl -s -f -m 5 --noproxy "*" "http://!SERVIDOR!/api/agente/estacao?id=!ID_PC!"`) do (
    set PISO_ATUAL=%%a
    set NOME_ATUAL=%%b
)
if not defined PISO_ATUAL exit /b 0
if "!PISO_ATUAL!"=="!PISO!" exit /b 0
echo       Este PC era a estacao !NOME_ATUAL! de outro piso: entra no piso escolhido
echo       como computador novo. A !NOME_ATUAL! antiga fica no mapa ^(exclua no painel^).
set ID_PC=
exit /b 0

:escolher_piso
:: Os pisos vem do servidor, uma linha "id;nome" cada (sem login)
set N_PISOS=0
for /f "usebackq tokens=1,* delims=;" %%a in (`curl -s -f -m 5 --noproxy "*" "http://!SERVIDOR!/api/agente/pisos"`) do (
    set /a N_PISOS+=1
    set PISO_ID_!N_PISOS!=%%a
    set PISO_NOME_!N_PISOS!=%%b
)
if !N_PISOS!==0 exit /b 0
if !N_PISOS!==1 (
    set PISO=!PISO_ID_1!
    echo   Piso: !PISO_NOME_1!
    exit /b 0
)
echo.
echo Em qual piso fica este computador?
for /l %%i in (1,1,!N_PISOS!) do echo   %%i - !PISO_NOME_%%i!
:perguntar_piso
set ESCOLHA=
set /p ESCOLHA="Numero do piso: "
set PISO=
for /l %%i in (1,1,!N_PISOS!) do if "!ESCOLHA!"=="%%i" set PISO=!PISO_ID_%%i!
if not defined PISO (
    echo Digite um dos numeros da lista.
    goto perguntar_piso
)
exit /b 0

:preparar_proxy
:: O pip e o download nao usam o proxy do Windows sozinhos: pega o do sistema
:: (o mesmo do navegador) e passa adiante. Sem proxy, nada muda.
set PROXY=
for /f "delims=" %%p in ('powershell -NoProfile -Command "$u=[Uri]'https://pypi.org/'; $p=[Net.WebRequest]::GetSystemWebProxy().GetProxy($u); if ($p.AbsoluteUri -ne $u.AbsoluteUri) { $p.AbsoluteUri.TrimEnd('/') }"') do set PROXY=%%p
if defined PROXY (
    echo       Usando o proxy da rede: !PROXY!
    set HTTPS_PROXY=!PROXY!
    set HTTP_PROXY=!PROXY!
)
exit /b 0

:python_do_agente
set PY_AGENTE=%DESTINO%\python\python.exe
"%PY_AGENTE%" -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo       Python do agente ja instalado em %DESTINO%\python.
    exit /b 0
)
:instalar_python
set PY_INSTALADOR=%TEMP%\mathecafe-python-%PY_VERSAO%-amd64.exe
if exist "%PY_INSTALADOR%" del "%PY_INSTALADOR%" >nul 2>&1
echo       Baixando o Python %PY_VERSAO% do python.org ^(cerca de 30 MB^)...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $w=New-Object Net.WebClient; $w.Proxy=[Net.WebRequest]::GetSystemWebProxy(); $w.Proxy.Credentials=[Net.CredentialCache]::DefaultCredentials; $w.DownloadFile('https://www.python.org/ftp/python/%PY_VERSAO%/python-%PY_VERSAO%-amd64.exe', '%PY_INSTALADOR%')"
if not exist "%PY_INSTALADOR%" (
    echo ERRO: Nao foi possivel baixar o Python. Confira a internet deste PC e o proxy da rede.
    exit /b 1
)
echo       Instalando o Python em %DESTINO%\python ^(1 a 3 minutos^)...
"%PY_INSTALADOR%" /quiet InstallAllUsers=1 TargetDir="%DESTINO%\python" Include_launcher=0 InstallLauncherAllUsers=0 PrependPath=0 Shortcuts=0 AssociateFiles=0 Include_test=0 Include_doc=0 Include_tcltk=1 Include_pip=1 CompileAll=0
del "%PY_INSTALADOR%" >nul 2>&1
:: Se esta mesma versao ja estava instalada em outro lugar, o instalador do
:: python.org so "modifica" aquela: copia ela para %DESTINO%\python
if not exist "%PY_AGENTE%" call :copiar_python_existente
"%PY_AGENTE%" -c "import sys, tkinter" >nul 2>&1
if errorlevel 1 (
    echo ERRO: O Python nao ficou pronto em %DESTINO%\python.
    echo Instale o Python %PY_VERSAO% pelo python.org ^(com tcl/tk^) e rode este instalador de novo.
    exit /b 1
)
echo       Python instalado.
exit /b 0

:copiar_python_existente
set PY_BASE=
for /f "tokens=1,2 delims=." %%a in ("%PY_VERSAO%") do set PY_MM=%%a.%%b
for %%h in (HKLM HKCU) do (
    if not defined PY_BASE (
        for /f "tokens=2,*" %%a in ('reg query "%%h\SOFTWARE\Python\PythonCore\!PY_MM!\InstallPath" /ve 2^>nul ^| findstr REG_SZ') do set PY_BASE=%%b
    )
)
if not defined PY_BASE exit /b 1
if "!PY_BASE:~-1!"=="\" set PY_BASE=!PY_BASE:~0,-1!
echo       Copiando o Python que ja existia ^(!PY_BASE!^) para %DESTINO%\python...
robocopy "!PY_BASE!" "%DESTINO%\python" /MIR /XD "!PY_BASE!\Lib\site-packages" __pycache__ /NFL /NDL /NJH /NJS /NP >nul
exit /b 0
