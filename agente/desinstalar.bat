@echo off
:: MatheCafe - Remove o inicio automatico do agente e o autologin.
:: O usuario "cliente" e a pasta C:\MatheCafe sao mantidos (apague a mao se quiser).
:: Execute como Administrador.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este arquivo como Administrador.
    pause
    exit /b 1
)

schtasks /delete /tn "MatheCafe-Agente" /f >nul 2>&1
schtasks /delete /tn "MatheCafe_Agente" /f >nul 2>&1
echo Tarefa agendada removida.

set WINLOGON=HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon
reg add "%WINLOGON%" /v AutoAdminLogon /t REG_SZ /d "0" /f >nul
reg delete "%WINLOGON%" /v DefaultPassword /f >nul 2>&1
echo Autologin desligado.

echo.
echo Pronto. O agente nao abre mais sozinho.
pause
