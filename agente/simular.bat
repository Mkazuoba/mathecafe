@echo off
rem MatheCafe - simulador da tela do cliente (so para desenvolver o visual).
rem Abre o agente numa janela comum, ligado ao servidor de TESTE (127.0.0.1:8011),
rem sem bloquear teclas, sem esconder a barra, sem fechar programas e sem desligar
rem o PC. Outro servidor:  simular.bat --servidor ws://IP:PORTA
cd /d "%~dp0"
set "PY=venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" simular.py %*
