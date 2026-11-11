@echo off
setlocal EnableDelayedExpansion
:: ============================================================
::  MatheCafe - Desinstalador (deixa o PC como antes do instalar.bat)
::  Execute como Administrador.
::
::  Remove: a tarefa do agente, o autologin, o usuario "cliente" com o perfil
::  dele (e as politicas que ficam nele: Gerenciador de Tarefas, downloads do
::  Chrome/Edge), o Python do agente (desinstala se foi instalado pelo
::  instalar.bat) e a pasta C:\MatheCafe inteira (agente, venv, agente.cfg).
::
::  NAO mexe no servidor: a estacao continua no painel. Para reinstalar este
::  PC com o mesmo nome, exclua a estacao no Mapa (Modo configuracao) antes, ou
::  use "Substitui a X" em Novas estacoes quando ele aparecer de novo.
:: ============================================================

set DESTINO=C:\MatheCafe

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este arquivo como Administrador
    echo ^(clique com o botao direito ^> Executar como administrador^).
    pause
    exit /b 1
)

:: Rodando de dentro de C:\MatheCafe: a pasta sera apagada, entao continua de
:: uma copia na pasta temporaria
if /i "%~dp0"=="%DESTINO%\" (
    copy /y "%~f0" "%TEMP%\mathecafe_desinstalar.bat" >nul
    "%TEMP%\mathecafe_desinstalar.bat"
)

echo.
echo ============================================================
echo   MatheCafe - Desinstalar tudo
echo ============================================================
echo.
echo Isto vai APAGAR deste computador:
echo   - o usuario Windows "cliente" e tudo o que esta no perfil dele
echo   - a pasta %DESTINO% ^(agente, Python do agente, configuracao^)
echo   - o inicio automatico do agente e o autologin
echo A estacao continua cadastrada no painel do servidor.
echo.
set CONFIRMA=
set /p CONFIRMA="Digite SIM para continuar: "
if /i not "!CONFIRMA!"=="SIM" (
    echo Cancelado. Nada foi alterado.
    pause
    exit /b 0
)
echo.

:: ---- 1. Fechar o agente e a sessao do cliente ----
echo [1/6] Fechando o agente e a sessao do "cliente"...
schtasks /end /tn "MatheCafe-Agente" >nul 2>&1
powershell -NoProfile -Command "Get-Process | Where-Object { $_.Path -like '%DESTINO%\*' } | Stop-Process -Force" >nul 2>&1
:: o perfil so sai com o cliente deslogado
powershell -NoProfile -Command "foreach ($l in (query user 2>$null)) { if ($l -match '^\s*>?cliente\s+(?:\S+\s+)?(\d+)\s') { logoff $Matches[1] } }" >nul 2>&1
taskkill /f /fi "USERNAME eq cliente" >nul 2>&1

:: ---- 2. Tarefa agendada ----
echo [2/6] Removendo a tarefa agendada...
schtasks /delete /tn "MatheCafe-Agente" /f >nul 2>&1
schtasks /delete /tn "MatheCafe_Agente" /f >nul 2>&1
schtasks /delete /tn "MatheCafe-Politicas" /f >nul 2>&1

:: ---- 3. Autologin ----
echo [3/6] Desligando o autologin...
set WINLOGON=HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon
reg add "%WINLOGON%" /v AutoAdminLogon /t REG_SZ /d "0" /f >nul
reg delete "%WINLOGON%" /v DefaultPassword /f >nul 2>&1
for /f "tokens=2,*" %%a in ('reg query "%WINLOGON%" /v DefaultUserName 2^>nul ^| findstr REG_SZ') do (
    if /i "%%b"=="cliente" reg delete "%WINLOGON%" /v DefaultUserName /f >nul 2>&1
)

:: ---- 4. Python do agente ----
:: So desinstala o Python registrado na pasta do agente (o instalar.bat o
:: instala em %DESTINO%\python); um Python que a maquina ja tinha nao e tocado
echo [4/6] Removendo o Python do agente...
if exist "%DESTINO%\python\python.exe" (
    powershell -NoProfile -Command "$alvo = '%DESTINO%\python'.TrimEnd('\'); $nosso = Get-ChildItem 'HKLM:\SOFTWARE\Python\PythonCore' -ErrorAction SilentlyContinue | Where-Object { ((Get-ItemProperty ($_.PSPath + '\InstallPath') -ErrorAction SilentlyContinue).'(default)' -replace '\\$','') -ieq $alvo }; if ($nosso) { $ver = (Get-Item ($alvo + '\python.exe')).VersionInfo.ProductVersion; $chaves = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'; $pacote = Get-ItemProperty $chaves -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like ('Python ' + $ver + ' (64-bit)') -and $_.QuietUninstallString } | Select-Object -First 1; if ($pacote) { Write-Output ('      Desinstalando Python ' + $ver + '...'); Start-Process cmd.exe -ArgumentList ('/c ' + $pacote.QuietUninstallString) -Wait -WindowStyle Hidden } }"
)

:: ---- 5. Usuario cliente e o perfil dele ----
echo [5/6] Apagando o usuario "cliente" e o perfil dele...
:: o perfil pelo SID (pasta C:\Users\cliente e a chave do registro); as
:: politicas do cliente estao no perfil e somem junto
powershell -NoProfile -Command "$u = Get-LocalUser -Name cliente -ErrorAction SilentlyContinue; if ($u) { Get-CimInstance Win32_UserProfile | Where-Object { $_.SID -eq $u.SID.Value } | Remove-CimInstance -ErrorAction SilentlyContinue }" >nul 2>&1
net user cliente /delete >nul 2>&1
if exist "C:\Users\cliente" (
    rmdir /s /q "C:\Users\cliente" >nul 2>&1
)
if exist "C:\Users\cliente" echo       AVISO: C:\Users\cliente ficou ^(reinicie o PC e rode de novo para apagar^).

:: ---- 6. Pasta do agente ----
echo [6/6] Apagando %DESTINO%...
if exist "%DESTINO%" rmdir /s /q "%DESTINO%" >nul 2>&1
if exist "%DESTINO%" (
    echo       AVISO: %DESTINO% nao saiu inteira ^(arquivo em uso^). Reinicie o PC e apague a mao.
)

echo.
echo ============================================================
echo   Desinstalado.
echo ============================================================
echo Reinicie o PC. Para instalar de novo, rode o instalar.bat.
echo Lembre: a estacao continua no painel ^(Mapa^).
pause
:: a copia na pasta temporaria se apaga ao sair
if /i "%~dp0"=="%TEMP%\" (goto) 2>nul & del "%~f0"
exit /b 0
