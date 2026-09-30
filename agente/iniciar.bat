@echo off
rem Abre o agente do MatheCafe como Administrador (necessario para o
rem bloqueio de programas).
rem
rem Uso:  iniciar.bat ws://IP_DO_SERVIDOR:8000 PC-01 [teste]
rem Com "teste" no fim, o agente nao fecha nenhum programa (PC de testes).
rem Sem parametros, pergunta o servidor e o nome da estacao.
cd /d "%~dp0"

if not exist venv\Scripts\pythonw.exe (
    echo Rode primeiro o instalar.bat
    pause
    exit /b 1
)

set "SERVIDOR=%~1"
set "ESTACAO=%~2"
set "EXTRA="
if /i "%~3"=="teste" set "EXTRA= --teste"
if "%SERVIDOR%"=="" set /p "SERVIDOR=Endereco do servidor (ex: ws://192.168.0.10:8000): "
if "%ESTACAO%"=="" set /p "ESTACAO=Nome desta estacao, igual ao cadastrado no Mapa (ex: PC-01): "

rem Aceita o endereco digitado de varios jeitos: 10.0.0.5:8000, http://..., ws://...
set "SERVIDOR=%SERVIDOR: =%"
set "SERVIDOR=%SERVIDOR:https://=wss://%"
set "SERVIDOR=%SERVIDOR:http://=ws://%"
if /i not "%SERVIDOR:~0,2%"=="ws" set "SERVIDOR=ws://%SERVIDOR%"
echo Abrindo o agente: servidor %SERVIDOR%, estacao %ESTACAO%
if exist agente_erro.log echo Se algo falhar, veja agente_erro.log nesta pasta.

powershell -NoProfile -Command "Start-Process -FilePath '%~dp0venv\Scripts\pythonw.exe' -ArgumentList '\"%~dp0agente.py\" --servidor %SERVIDOR% --estacao %ESTACAO%%EXTRA%' -WorkingDirectory '%~dp0' -Verb RunAs"
