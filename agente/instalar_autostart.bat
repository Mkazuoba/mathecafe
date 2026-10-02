@echo off
:: MatheCafe - Instalar agente no boot como Administrador
:: Execute este script como Administrador

setlocal

set "AGENTE_DIR=%~dp0"
set "AGENTE_PY=%AGENTE_DIR%agente.py"
set "PYTHON_EXE=python"
set "TASK_NAME=MatheCafe_Agente"

:: Verifica se o Python existe
where python >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado no PATH.
    echo Instale o Python e certifique-se que esta no PATH.
    pause & exit /b 1
)

:: Remove a tarefa se ja existir
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Cria tarefa agendada para rodar ao iniciar o Windows com privilegio mais alto
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "cmd /c cd /d \"%AGENTE_DIR%\" && python agente.py" ^
  /sc ONSTART ^
  /delay 0001:00 ^
  /rl HIGHEST ^
  /ru SYSTEM ^
  /f

if errorlevel 1 (
    echo.
    echo Falha ao criar tarefa com SYSTEM. Tentando com usuario atual...
    schtasks /create ^
      /tn "%TASK_NAME%" ^
      /tr "cmd /c cd /d \"%AGENTE_DIR%\" && python agente.py" ^
      /sc ONSTART ^
      /delay 0001:00 ^
      /rl HIGHEST ^
      /f
)

if errorlevel 1 (
    echo ERRO: Nao foi possivel criar a tarefa agendada.
    echo Execute este script como Administrador.
    pause & exit /b 1
)

echo.
echo Agente configurado para iniciar automaticamente no boot!
echo Nome da tarefa: %TASK_NAME%
echo.
echo Para remover: execute desinstalar_autostart.bat
pause
