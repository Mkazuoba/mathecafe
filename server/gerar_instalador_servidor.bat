@echo off
rem MatheCafe - gera o MatheCafe-Servidor-Instalador.exe (instalador do servidor com tela).
rem Roda neste computador. Precisa de um Python 3.11+ com Tkinter e de internet
rem na primeira vez (baixa o PyInstaller). Usa o mesmo ambiente de build do
rem instalador das estacoes (agente\build\venv) e as pecas de tela dele
rem (agente\instalador.py, por --paths).
rem
rem Leva dentro do .exe o servidor DESTA pasta: app (com o painel ja buildado em
rem app\static), agente_dist e os scripts. Gere de novo depois de liberar uma
rem versao. Resultado: server\dist\MatheCafe-Servidor-Instalador.exe
cd /d "%~dp0"
set "BUILD=%~dp0..\agente\build"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY set "PY=python"

if not exist "%BUILD%\venv\Scripts\python.exe" (
    echo Criando o ambiente de build em agente\build\venv...
    %PY% -m venv "%BUILD%\venv" || goto erro
)
"%BUILD%\venv\Scripts\python.exe" -m pip install -q --upgrade pip pyinstaller || goto erro

rem os arquivos do servidor, sem caches
set "TMPSRV=%BUILD%\servidor"
if exist "%TMPSRV%" rmdir /s /q "%TMPSRV%"
mkdir "%TMPSRV%"
robocopy app "%TMPSRV%\app" /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP >nul
robocopy agente_dist "%TMPSRV%\agente_dist" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
for %%f in (main.py requirements.txt iniciar_servidor.bat reiniciar_servidor.bat registrar_servidor.ps1 .env.example importar_vscyber.py importar_historico.py importar_infantil.py) do (
    copy /y "%%f" "%TMPSRV%\" >nul || goto erro
)

"%BUILD%\venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
    --name MatheCafe-Servidor-Instalador --distpath dist --workpath "%BUILD%\pyinstaller-servidor" ^
    --specpath "%BUILD%" --paths "%~dp0..\agente" ^
    --add-data "%TMPSRV%;servidor" instalador_servidor.py || goto erro

echo.
echo Pronto: %~dp0dist\MatheCafe-Servidor-Instalador.exe
pause
exit /b 0

:erro
echo.
echo ERRO ao gerar o instalador do servidor. Veja as mensagens acima.
pause
exit /b 1
