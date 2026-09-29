@echo off
rem Abre o agente do MatheCafe como Administrador (necessario para o
rem bloqueio de programas).
rem
rem Uso:  iniciar.bat ws://IP_DO_SERVIDOR:8000 PC-01
rem Sem parametros, pergunta o servidor e o nome da estacao.
cd /d "%~dp0"

if not exist venv\Scripts\pythonw.exe (
    echo Rode primeiro o instalar.bat
    pause
    exit /b 1
)

set "SERVIDOR=%~1"
set "ESTACAO=%~2"
if "%SERVIDOR%"=="" set /p "SERVIDOR=Endereco do servidor (ex: ws://192.168.0.10:8000): "
if "%ESTACAO%"=="" set /p "ESTACAO=Nome desta estacao, igual ao cadastrado no Mapa (ex: PC-01): "

powershell -NoProfile -Command "Start-Process -FilePath '%~dp0venv\Scripts\pythonw.exe' -ArgumentList '\"%~dp0agente.py\" --servidor %SERVIDOR% --estacao %ESTACAO%' -WorkingDirectory '%~dp0' -Verb RunAs"
