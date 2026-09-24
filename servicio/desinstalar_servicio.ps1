#requires -version 5.1
<#
    desinstalar_servicio.ps1
    Detiene y elimina el servicio "Control Remoto PC - Agente" y quita la
    regla de firewall. Clic derecho > "Ejecutar con PowerShell".
#>

$ErrorActionPreference = "SilentlyContinue"

# --- Auto-elevacion a Administrador ---
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$dir = $PSScriptRoot
$svc = Join-Path $dir "agente_servicio.py"

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }

if ($py -and (Test-Path $svc)) {
    & $py "$svc" stop
    & $py "$svc" remove
} else {
    # Fallback si no hay Python disponible
    sc.exe stop   ControlRemotoPC | Out-Null
    sc.exe delete ControlRemotoPC | Out-Null
}

Remove-NetFirewallRule -DisplayName "Control Remoto PC (Agente)" -ErrorAction SilentlyContinue

Write-Host "Servicio 'Control Remoto PC - Agente' eliminado." -ForegroundColor Green
