@echo off
rem MatheCafe - reinicia o servidor SEM administrador e sem entrar no painel.
rem Clique duas vezes. Deixa o arquivo reiniciar.pedido nesta pasta; o servidor
rem aberto pela tarefa MatheCafe-Servidor (iniciar_servidor.bat) percebe em ate
rem 2 s, sai, e a tarefa o sobe de novo com o codigo atual. Quem estiver usando
rem os computadores continua a sessao.
cd /d "%~dp0"
if "%PORTA%"=="" set "PORTA=8000"
echo pedido> reiniciar.pedido
echo Pedido de reinicio enviado. Esperando o servidor atender...
for /l %%i in (1,1,15) do (
    if not exist reiniciar.pedido goto atendeu
    ping -n 2 127.0.0.1 >nul
)
del reiniciar.pedido >nul 2>&1
echo.
echo O servidor nao atendeu em 15 s.
echo Ele foi aberto pela tarefa MatheCafe-Servidor? Se foi aberto num terminal,
echo reinicie por la. Detalhes em logs\servidor.log.
pause
exit /b 1

:atendeu
echo O servidor esta reiniciando...
rem espera ele sair e voltar (o .bat da tarefa sobe de novo em 3 s)
ping -n 4 127.0.0.1 >nul
for /l %%i in (1,1,30) do (
    curl -s -f -o nul http://127.0.0.1:%PORTA%/health && goto voltou
    ping -n 2 127.0.0.1 >nul
)
echo.
echo O servidor ainda nao voltou depois de 30 s. Veja logs\servidor.log.
pause
exit /b 1

:voltou
echo.
echo Servidor no ar de novo.
ping -n 4 127.0.0.1 >nul
exit /b 0
