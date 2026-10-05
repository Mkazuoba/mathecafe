@echo off
rem MatheCafe - Inicia o agente como Administrador
rem Na primeira vez, o proprio agente pergunta o servidor e o nome da estacao
rem e salva em agente.cfg. Nas proximas, ja carrega automatico.
cd /d "%~dp0"

if not exist venv\Scripts\pythonw.exe (
    echo Rode primeiro o instalar.bat
    pause
    exit /b 1
)

rem Aceita parametros opcionais para substituir o cfg
set "SERVIDOR=%~1"
set "ESTACAO=%~2"

rem Normaliza protocolo se passado como argumento
if not "%SERVIDOR%"=="" (
    set "SERVIDOR=%SERVIDOR: =%"
    set "SERVIDOR=%SERVIDOR:https://=wss://%"
    set "SERVIDOR=%SERVIDOR:http://=ws://%"
)

rem Monta argumentos extras apenas se fornecidos
set "ARGS="
if not "%SERVIDOR%"=="" set "ARGS=--servidor %SERVIDOR%"
if not "%ESTACAO%"=="" set "ARGS=%ARGS% --estacao %ESTACAO%"

if exist agente.cfg (
    echo Usando configuracao salva em agente.cfg
) else (
    echo Primeira execucao - o agente ira pedir o servidor e o nome da estacao.
)

powershell -NoProfile -Command "Start-Process -FilePath '%~dp0venv\Scripts\pythonw.exe' -ArgumentList '\"%~dp0agente.py\" %ARGS%' -WorkingDirectory '%~dp0' -Verb RunAs"
