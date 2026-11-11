# MatheCafe - registra a tarefa que grava as politicas do "cliente" a cada logon
# dele (Ctrl+Alt+Del sem Gerenciador de Tarefas, Bloquear e Alterar senha;
# downloads do Chrome/Edge presos em Downloads). Chamado pelo instalar.bat (como
# Administrador):
#   powershell -ExecutionPolicy Bypass -File registrar_politicas.ps1 -Pasta C:\MatheCafe
#
# Por que: o instalar.bat grava as politicas na hora, mas numa maquina nova o
# perfil do cliente ainda nao existe e isso pode falhar (aconteceu em 11/11: o
# Ctrl+Alt+Del deixava trocar a senha). A tarefa roda como SYSTEM no logon do
# cliente, com o perfil dele ja carregado, e grava de novo toda vez (se alguem
# mexer, volta no proximo logon).
param(
    [Parameter(Mandatory = $true)][string]$Pasta,
    [string]$Usuario = "cliente"
)
$ErrorActionPreference = "Stop"

$nome  = "MatheCafe-Politicas"
$conta = "$env:COMPUTERNAME\$Usuario"
$script = Join-Path $Pasta "politicas_cliente.ps1"

Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction SilentlyContinue

$acao = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $script + '" -Usuario ' + $Usuario) `
    -WorkingDirectory $Pasta

$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $conta

# SYSTEM: o cliente nao pode gravar as proprias politicas
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$config = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho `
    -Principal $principal -Settings $config | Out-Null

Write-Output "Tarefa $nome registrada (grava as politicas a cada logon de $conta)"
