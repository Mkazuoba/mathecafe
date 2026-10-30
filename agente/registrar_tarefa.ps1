# MatheCafe - registra a tarefa que abre o agente no logon do usuario "cliente".
# Chamado pelo instalar.bat (como Administrador):
#   powershell -ExecutionPolicy Bypass -File registrar_tarefa.ps1 -Pasta C:\MatheCafe
#
# Por que assim (e nao schtasks /ru SYSTEM):
# - SYSTEM roda na sessao 0, sem area de trabalho: a janela do agente nunca aparece.
# - Com senha gravada (/rp) a tarefa vira "executar estando conectado ou nao" e
#   tambem roda sem janela. LogonType Interactive roda dentro da sessao do cliente.
# - O schtasks nao permite tirar o limite padrao de 3 dias de execucao.
param(
    [Parameter(Mandatory = $true)][string]$Pasta,
    [string]$Usuario = "cliente"
)
$ErrorActionPreference = "Stop"

$nome  = "MatheCafe-Agente"
$conta = "$env:COMPUTERNAME\$Usuario"

# Tarefas de versoes anteriores (a "_Agente" rodava como SYSTEM no boot e abria
# um segundo agente invisivel com o mesmo nome de estacao)
foreach ($antiga in @($nome, "MatheCafe_Agente")) {
    Unregister-ScheduledTask -TaskName $antiga -Confirm:$false -ErrorAction SilentlyContinue
}

$acao = New-ScheduledTaskAction `
    -Execute (Join-Path $Pasta "venv\Scripts\pythonw.exe") `
    -Argument ('"' + (Join-Path $Pasta "agente.py") + '"') `
    -WorkingDirectory $Pasta

$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $conta
# Sem atraso: o cliente nao pode usar o PC antes da janela do agente

$principal = New-ScheduledTaskPrincipal -UserId $conta -LogonType Interactive -RunLevel Limited

# Sem limite de tempo; reabre se o agente cair com erro (fechar pela manutencao sai com 0)
$config = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho `
    -Principal $principal -Settings $config | Out-Null

Write-Output "Tarefa $nome registrada para $conta"
