@echo off
rem MatheCafe - sobe o servidor (chamado pela tarefa MatheCafe-Servidor ou a mao).
rem A saida vai para logs\servidor.log, ao lado deste arquivo.
rem Se o servidor terminar (botao Reiniciar servidor do painel, ou queda), sobe
rem de novo em 3 s. Para parar de vez: schtasks /end /tn MatheCafe-Servidor
rem (como administrador) ou fechar esta janela.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo Crie o venv antes: python -m venv venv  e  venv\Scripts\pip install -r requirements.txt
    exit /b 1
)
if "%PORTA%"=="" set "PORTA=8000"
if not exist logs mkdir logs
rem LOG muda o arquivo (padrao logs\servidor.log; util para testar outra copia)
if "%LOG%"=="" set "LOG=logs\servidor.log"
rem Sem isto, um print com acento derruba o servidor num console cp1252
set "PYTHONUTF8=1"
rem Cada print vai direto para o log (sem buffer)
set "PYTHONUNBUFFERED=1"
rem Diz ao servidor que alguem o sobe de novo: libera o botao Reiniciar servidor
set "MATHECAFE_SUPERVISIONADO=1"
:subir
echo.>> "%LOG%"
echo ==== %DATE% %TIME% - subindo na porta %PORTA% ====>> "%LOG%"
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port %PORTA% --no-access-log >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% - servidor terminou (codigo %ERRORLEVEL%), subindo de novo em 3 s ====>> "%LOG%"
rem pausa de 3 s com ping: o comando de espera do Windows nao funciona sem console
ping -n 4 127.0.0.1 >nul
goto subir
