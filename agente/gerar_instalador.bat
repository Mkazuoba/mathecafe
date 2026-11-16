@echo off
rem MatheCafe - gera o MatheCafe-Instalador.exe (instalador com tela, 10.11).
rem Roda neste computador (nao nas estacoes). Precisa de um Python 3.11+ com
rem Tkinter e de internet na primeira vez (baixa o PyInstaller).
rem
rem Leva dentro do .exe: o agente.py LIBERADO (server\agente_dist), os scripts
rem desta pasta e o servidor.txt. Gere de novo quando mudar algum deles ou o
rem instalador.py. Resultado: agente\dist\MatheCafe-Instalador.exe
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY set "PY=python"

if not exist "build\venv\Scripts\python.exe" (
    echo Criando o ambiente de build em agente\build\venv...
    %PY% -m venv build\venv || goto erro
)
build\venv\Scripts\python.exe -m pip install -q --upgrade pip pyinstaller || goto erro

set "DADOS="
for %%f in (requirements.txt iniciar.bat registrar_tarefa.ps1 registrar_politicas.ps1 politicas_cliente.ps1 desinstalar.bat servidor.txt) do (
    call set "DADOS=%%DADOS%% --add-data ""%~dp0%%f;arquivos"""
)

build\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
    --name MatheCafe-Instalador --distpath dist --workpath build\pyinstaller --specpath build ^
    --add-data "%~dp0..\server\agente_dist\agente.py;arquivos" %DADOS% instalador.py || goto erro

echo.
echo Pronto: %~dp0dist\MatheCafe-Instalador.exe
echo Leve so esse arquivo (e, se o servidor mudou de IP, um servidor.txt ao lado).
pause
exit /b 0

:erro
echo.
echo ERRO ao gerar o instalador. Veja as mensagens acima.
pause
exit /b 1
