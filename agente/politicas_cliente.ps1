# MatheCafe - desliga para o usuario "cliente" o que o agente nao consegue
# bloquear sozinho: as opcoes da tela do Ctrl+Alt+Del (Gerenciador de Tarefas,
# Bloquear, Alterar senha). O "cliente" nao pode gravar essas politicas no
# proprio perfil, entao o instalar.bat (como Administrador) grava por ele.
#
#   set MC_SENHA=<senha do cliente>   (so usada se o perfil ainda nao existir)
#   powershell -ExecutionPolicy Bypass -File politicas_cliente.ps1
param([string]$Usuario = "cliente")
$ErrorActionPreference = "Stop"

$sid = (Get-LocalUser -Name $Usuario).SID.Value
$perfil = "Registry::HKEY_USERS\$sid"
$lista = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid"
$abrimos = $false

if (-not (Test-Path $perfil)) {
    if (-not (Test-Path $lista)) {
        # O cliente nunca entrou no Windows: cria o perfil abrindo um processo como ele
        if (-not $env:MC_SENHA) { throw "senha do cliente nao informada (MC_SENHA)" }
        $senha = ConvertTo-SecureString $env:MC_SENHA -AsPlainText -Force
        $cred = New-Object System.Management.Automation.PSCredential ("$env:COMPUTERNAME\$Usuario", $senha)
        Start-Process cmd.exe -ArgumentList "/c exit" -Credential $cred -LoadUserProfile -WindowStyle Hidden -Wait
    }
    $dat = Join-Path (Get-ItemProperty $lista).ProfileImagePath "NTUSER.DAT"
    # Logo depois de criado, o perfil pode seguir carregado por alguns segundos
    for ($i = 0; $i -lt 15 -and -not (Test-Path $perfil); $i++) {
        cmd /c "reg load `"HKU\$sid`" `"$dat`" >nul 2>&1"
        if ($LASTEXITCODE -eq 0) { $abrimos = $true } else { Start-Sleep -Seconds 1 }
    }
    if (-not (Test-Path $perfil)) { throw "nao foi possivel abrir o perfil de $Usuario ($dat)" }
}

try {
    $chave = "$perfil\Software\Microsoft\Windows\CurrentVersion\Policies\System"
    if (-not (Test-Path $chave)) { New-Item $chave -Force | Out-Null }
    foreach ($nome in "DisableTaskMgr", "DisableLockWorkstation", "DisableChangePassword") {
        New-ItemProperty $chave -Name $nome -Value 1 -PropertyType DWord -Force | Out-Null
    }
    Write-Output "Politicas gravadas no perfil de $Usuario"
} finally {
    if ($abrimos) {
        [gc]::Collect()
        cmd /c "reg unload `"HKU\$sid`" >nul 2>&1"
    }
}
