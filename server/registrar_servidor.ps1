# MatheCafe - faz o servidor subir sozinho quando o Windows liga.
# Rode como Administrador, de dentro da pasta server:
#   powershell -ExecutionPolicy Bypass -File registrar_servidor.ps1
#
# - Tarefa "MatheCafe-Servidor" na inicializacao do Windows, como SYSTEM: o
#   servidor nao precisa de area de trabalho e sobe sem ninguem fazer login.
#   (O agente das estacoes e o contrario: precisa da sessao do cliente.)
# - Sem limite de tempo e reabrindo a cada minuto se cair.
# - Libera a porta no Firewall do Windows para as estacoes (redes privadas e
#   de dominio).
param(
    [int]$Porta = 8000,
    [switch]$Remover
)
$ErrorActionPreference = "Stop"

$nome  = "MatheCafe-Servidor"
$regra = "MatheCafe Servidor (TCP $Porta)"
$pasta = $PSScriptRoot

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Rode como Administrador (botao direito no PowerShell -> Executar como administrador)." }

Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName "MatheCafe Servidor*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if ($Remover) {
    Write-Output "Tarefa $nome e regra do firewall removidas."
    return
}

if (-not (Test-Path (Join-Path $pasta "venv\Scripts\python.exe"))) {
    throw "Nao achei $pasta\venv. Instale antes: python -m venv venv; venv\Scripts\pip install -r requirements.txt"
}

$acao = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument ('/c set "PORTA=' + $Porta + '" && "' + (Join-Path $pasta "iniciar_servidor.bat") + '"') `
    -WorkingDirectory $pasta
$gatilho   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$config = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho `
    -Principal $principal -Settings $config | Out-Null

New-NetFirewallRule -DisplayName $regra -Direction Inbound -Protocol TCP -LocalPort $Porta `
    -Action Allow -Profile Private, Domain | Out-Null

Start-ScheduledTask -TaskName $nome
Write-Output "Tarefa $nome registrada e iniciada (porta $Porta). Log: $pasta\logs\servidor.log"
Write-Output "Teste: http://127.0.0.1:$Porta/health"
