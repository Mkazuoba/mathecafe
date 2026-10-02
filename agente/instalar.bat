@echo off
rem Prepara o agente do MatheCafe nesta estacao: cria o ambiente Python
rem (pasta venv) e instala as dependencias. Rode uma vez, com dois cliques.
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado.
    echo Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
    echo e marque "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

echo Criando o ambiente Python...
py -3 -m venv venv || goto erro
echo Instalando as dependencias...
venv\Scripts\python -m pip install --upgrade pip -q
venv\Scripts\python -m pip install -r requirements.txt -q || goto erro

echo.
echo Pronto. Para abrir o agente, use iniciar.bat
pause
exit /b 0

:erro
echo.
echo A instalacao falhou. Confira a conexao com a internet e tente de novo.
pause
exit /b 1
