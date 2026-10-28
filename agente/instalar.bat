@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo   MatheCafe - Instalador do Agente
echo ============================================================
echo.
echo Este instalador vai:
echo   1. Criar o usuario Windows "cliente" (autologin)
echo   2. Copiar o agente para C:\MatheCafe e instalar as dependencias
echo   3. Configurar o agente para abrir sozinho no login do "cliente"
echo   4. Registrar esta estacao no servidor
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

:: ---- Descobrir Python ----
:: O usuario "cliente" precisa conseguir ler a instalacao do Python. Uma
:: instalacao "so para mim" (o padrao do instalador do python.org) fica no
:: perfil de quem instalou e o cliente nao tem acesso: nesse caso o Python e
:: copiado para %DESTINO%\python (funciona de qualquer pasta). O da Microsoft
:: Store (WindowsApps) nao pode ser copiado.
set PYTHON=
where py >nul 2>&1
if !errorlevel!==0 (
    set PYTHON=py -3
) else (
    where python >nul 2>&1
    if !errorlevel!==0 set PYTHON=python
)
if "!PYTHON!"=="" goto :python_ausente

set PYBASE=
for /f "delims=" %%i in ('!PYTHON! -c "import sys; print(sys.base_prefix)" 2^>nul') do set PYBASE=%%i
if "!PYBASE!"=="" goto :python_ausente

if not "!PYBASE:WindowsApps=!"=="!PYBASE!" (
    echo ERRO: o Python encontrado e o da Microsoft Store:
    echo        !PYBASE!
    echo Ele nao pode ser usado pelo usuario "cliente". Instale pelo python.org
    echo ou, num terminal de administrador:
    echo     winget install -e --id Python.Python.3.13 --scope machine
    pause
    exit /b 1
)
set COPIAR_PY=
if not "!PYBASE:\Users\=!"=="!PYBASE!" set COPIAR_PY=1
echo Python encontrado: !PYBASE!
if defined COPIAR_PY echo   ^(instalado so para este usuario: sera copiado para %DESTINO%\python^)

:: ---- Coletar dados ----
echo.
echo ---- Dados da estacao ----
echo.

set /p ESTACAO="Nome da estacao (ex: PC-01): "
if "!ESTACAO!"=="" (
    echo ERRO: Nome da estacao nao pode ser vazio.
    pause
    exit /b 1
)

set /p SERVIDOR="Endereco do servidor (ex: 10.26.31.99:8000): "
if "!SERVIDOR!"=="" (
    echo ERRO: Endereco do servidor nao pode ser vazio.
    pause
    exit /b 1
)
:: Aceita o endereco com ou sem protocolo
set SERVIDOR=!SERVIDOR: =!
set SERVIDOR=!SERVIDOR:http://=!
set SERVIDOR=!SERVIDOR:ws://=!

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
echo ---- Credenciais do painel MatheCafe ----
echo (Para registrar esta estacao no servidor)
echo.

set /p ADMIN_LOGIN="Login admin do painel: "
set /p ADMIN_SENHA="Senha admin do painel: "

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
if defined COPIAR_PY (
    robocopy "!PYBASE!" "%DESTINO%\python" /MIR /XD "!PYBASE!\Lib\site-packages" __pycache__ /NFL /NDL /NJH /NJS /NP >nul
    if !errorlevel! geq 8 (
        echo ERRO: Nao foi possivel copiar o Python para %DESTINO%\python.
        pause
        exit /b 1
    )
    set PYTHON="%DESTINO%\python\python.exe"
)
if /i not "%ORIGEM%"=="%DESTINO%\" (
    for %%f in (agente.py requirements.txt iniciar.bat registrar_tarefa.ps1 desinstalar.bat) do (
        copy /y "%ORIGEM%%%f" "%DESTINO%\" >nul
    )
)
if exist "%DESTINO%\venv" rmdir /s /q "%DESTINO%\venv"
!PYTHON! -m venv "%DESTINO%\venv"
if !errorlevel! neq 0 (
    echo ERRO: Nao foi possivel criar o ambiente Python em %DESTINO%\venv.
    pause
    exit /b 1
)
"%DESTINO%\venv\Scripts\python.exe" -m pip install --upgrade pip -q
"%DESTINO%\venv\Scripts\python.exe" -m pip install -r "%DESTINO%\requirements.txt" -q
if !errorlevel! neq 0 (
    echo ERRO: Falha ao instalar as dependencias. Confira a conexao com a internet.
    pause
    exit /b 1
)
echo       Agente e dependencias instalados.

:: ---- 4. Gravar agente.cfg e permissoes ----
echo [4/6] Salvando configuracao do agente...
(
    echo # MatheCafe - configuracao da estacao ^(gerado automaticamente^)
    echo SERVIDOR=ws://!SERVIDOR!
    echo ESTACAO=!ESTACAO!
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

:: ---- 6. Registrar estacao no servidor ----
echo [6/6] Registrando estacao "%ESTACAO%" no servidor...

:: Obter token de admin
set TOKEN_FILE=%TEMP%\mc_token.json
curl -s -X POST "http://!SERVIDOR!/api/auth/login" ^
    -H "Content-Type: application/x-www-form-urlencoded" ^
    -d "username=!ADMIN_LOGIN!&password=!ADMIN_SENHA!" ^
    -o "%TOKEN_FILE%" >nul 2>&1

if not exist "%TOKEN_FILE%" (
    echo       AVISO: Nao foi possivel conectar ao servidor. Cadastre a estacao manualmente no painel.
    goto :fim
)

:: Extrair token (busca simples por access_token)
set TOKEN=
for /f "tokens=2 delims=:," %%a in ('findstr "access_token" "%TOKEN_FILE%"') do (
    set TOKEN=%%a
    set TOKEN=!TOKEN: =!
    set TOKEN=!TOKEN:"=!
)
del "%TOKEN_FILE%" >nul 2>&1

if "!TOKEN!"=="" (
    echo       AVISO: Login admin falhou. Verifique as credenciais e cadastre a estacao manualmente no painel.
    goto :fim
)

:: Cadastrar estacao
curl -s -X POST "http://!SERVIDOR!/api/estacoes/?nome=!ESTACAO!" ^
    -H "Authorization: Bearer !TOKEN!" >nul 2>&1

echo       Estacao "!ESTACAO!" registrada no servidor.

:fim
echo.
echo ============================================================
echo   Instalacao concluida!
echo ============================================================
echo.
echo Proximos passos:
echo   - Reinicie o PC: ele entra sozinho como "cliente" e o agente abre
echo   - Agente instalado em %DESTINO% (pode apagar esta pasta de origem)
echo   - Para desinstalar: %DESTINO%\desinstalar.bat como Administrador
echo.
pause
exit /b 0

:python_ausente
echo ERRO: Python nao encontrado. Instale o Python 3.11+ para todos os usuarios:
echo     winget install -e --id Python.Python.3.13 --scope machine
echo ou pelo python.org ("Customize installation" -^> "Install Python for all users").
pause
exit /b 1
