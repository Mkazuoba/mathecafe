@echo off
:: MatheCafe - Remover agente do boot
set "TASK_NAME=MatheCafe_Agente"
schtasks /delete /tn "%TASK_NAME%" /f
if errorlevel 1 (
    echo Tarefa nao encontrada ou erro ao remover.
) else (
    echo Agente removido do inicio automatico.
)
pause
