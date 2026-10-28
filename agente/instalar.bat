@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo   MatheCafe - Instalador do Agente
echo ============================================================
echo.
echo Este instalador vai:
echo   1. Criar o usuario Windows "cliente" (autologin)
echo   2. Configurar o agente para iniciar automaticamente
echo   3. Registrar esta estacao no servidor
echo.
echo Rode como Administrador. Se ainda nao fez isso, feche e
echo clique com botao direito -> Executar como administrador.
echo.

:: Verificar se e administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este arquivo como Administrador.
    pause
    exit /b 1
)

:: ---- Coletar dados ----
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

:: ---- Caminho do agente ----
set AGENTE_DIR=%~dp0
set AGENTE_PY=%AGENTE_DIR%agente.py

if not exist "%AGENTE_PY%" (
    echo ERRO: agente.py nao encontrado em %AGENTE_DIR%
    pause
    exit /b 1
)

:: Descobrir python
set PYTHON=
for %%p in (python.exe python3.exe) do (
    where %%p >nul 2>&1
    if !errorlevel!==0 (
        set PYTHON=%%p
        goto :python_ok
    )
)
:: Tentar caminho comum
if exist "%LOCALAPPDATA%\Programs\Python\Python3*\python.exe" (
    for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do set PYTHON=%%d\python.exe
    goto :python_ok
)
echo ERRO: Python nao encontrado. Instale o Python 3.10+ e tente novamente.
pause
exit /b 1
:python_ok
echo.
echo Python encontrado: %PYTHON%

echo.
echo ============================================================
echo   Iniciando instalacao...
echo ============================================================
echo.

:: ---- 1. Criar usuario cliente ----
echo [1/5] Criando usuario Windows "cliente"...
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

:: Remover do grupo Administradores (garantia)
net localgroup Administradores cliente /delete >nul 2>&1
net localgroup Administrators cliente /delete >nul 2>&1

:: ---- 2. Configurar autologin ----
echo [2/5] Configurando autologin...
set WINLOGON=HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon
reg add "%WINLOGON%" /v AutoAdminLogon    /t REG_SZ /d "1"          /f >nul
reg add "%WINLOGON%" /v DefaultUserName   /t REG_SZ /d "cliente"    /f >nul
reg add "%WINLOGON%" /v DefaultPassword   /t REG_SZ /d "!SENHA_CLIENTE!" /f >nul
reg add "%WINLOGON%" /v DefaultDomainName /t REG_SZ /d "."          /f >nul
echo       Autologin configurado.

:: ---- 3. Gravar agente.cfg ----
echo [3/5] Salvando configuracao do agente...
(
    echo SERVIDOR=ws://!SERVIDOR!
    echo ESTACAO=!ESTACAO!
) > "%AGENTE_DIR%agente.cfg"
echo       agente.cfg salvo em %AGENTE_DIR%

:: ---- 4. Criar tarefa agendada ----
echo [4/5] Criando tarefa agendada...
set TASK_NAME=MatheCafe-Agente

:: Remover tarefa anterior se existir
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

schtasks /create /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON%\" \"%AGENTE_PY%\"" ^
    /sc onlogon /ru SYSTEM ^
    /rl HIGHEST ^
    /delay 0000:05 ^
    /f >nul

if %errorlevel% neq 0 (
    echo ERRO: Nao foi possivel criar a tarefa agendada.
    pause
    exit /b 1
)
echo       Tarefa "%TASK_NAME%" criada (dispara no login, roda como SYSTEM).

:: ---- 5. Registrar estacao no servidor ----
echo [5/5] Registrando estacao "%ESTACAO%" no servidor...

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
echo   - Reinicie o PC para ativar o autologin
echo   - O agente vai subir automaticamente apos o login
echo   - Para desinstalar: desinstalar.bat (a criar)
echo.
pause
