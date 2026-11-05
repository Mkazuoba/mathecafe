@echo off
rem MatheCafe - sobe o servidor (chamado pela tarefa MatheCafe-Servidor ou a mao).
rem A saida vai para logs\servidor.log, ao lado deste arquivo.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo Crie o venv antes: python -m venv venv  e  venv\Scripts\pip install -r requirements.txt
    exit /b 1
)
if "%PORTA%"=="" set "PORTA=8000"
if not exist logs mkdir logs
rem Sem isto, um print com acento derruba o servidor num console cp1252
set "PYTHONUTF8=1"
rem Cada print vai direto para o log (sem buffer)
set "PYTHONUNBUFFERED=1"
echo.>> logs\servidor.log
echo ==== %DATE% %TIME% - subindo na porta %PORTA% ====>> logs\servidor.log
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port %PORTA% --no-access-log >> logs\servidor.log 2>&1
