#requires -version 5.1
<#
    instalar_servicio.ps1
    Instala el Agente Remoto como SERVICIO de Windows (arranque automatico,
    segundo plano). Debe estar en la misma carpeta que agente.py y
    agente_servicio.py. Clic derecho > "Ejecutar con PowerShell".
#>

$ErrorActionPreference = "Stop"

# --- Auto-elevacion a Administrador ---
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$dir = $PSScriptRoot
$svc = Join-Path $dir "agente_servicio.py"

if (-not (Test-Path (Join-Path $dir "agente.py"))) {
    Write-Host "ERROR: pon este script en la MISMA carpeta que agente.py." -ForegroundColor Red
    exit 1
}

# --- Localizar Python ---
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) {
    Write-Host "No se encontro Python en el PATH." -ForegroundColor Red
    Write-Host "Instala Python 3.10+ desde https://www.python.org y marca 'Add Python to PATH'." -ForegroundColor Red
    exit 1
}

Write-Host "== Instalando dependencia pywin32 ==" -ForegroundColor Cyan
& $py -m pip install --upgrade pywin32

# Registro de DLLs de pywin32 (necesario para que arranquen servicios en Python)
$post = Join-Path (Split-Path $py) "Scripts\pywin32_postinstall.py"
if (Test-Path $post) { & $py $post -install | Out-Null }

# --- Abrir el puerto del agente en el firewall (lee el puerto de config.ini) ---
$puerto = 50505
$ini = Join-Path $dir "config.ini"
if (Test-Path $ini) {
    $m = Select-String -Path $ini -Pattern '^\s*puerto\s*=\s*(\d+)' | Select-Object -First 1
    if ($m) { $puerto = [int]$m.Matches[0].Groups[1].Value }
}
if (-not (Get-NetFirewallRule -DisplayName "Control Remoto PC (Agente)" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "Control Remoto PC (Agente)" -Direction Inbound `
        -Action Allow -Protocol TCP -LocalPort $puerto -Profile Private | Out-Null
    Write-Host "Regla de firewall creada para el puerto $puerto (perfil Privado)." -ForegroundColor Cyan
}

# --- Registrar e iniciar el servicio ---
Write-Host "== Registrando el servicio (arranque automatico) ==" -ForegroundColor Cyan
& $py "$svc" --startup auto install
& $py "$svc" start

Write-Host ""
Write-Host "== Estado del servicio ==" -ForegroundColor Green
sc.exe query ControlRemotoPC
Write-Host ""
Write-Host "Listo. Miralo en services.msc  ->  'Control Remoto PC - Agente'." -ForegroundColor Green
Write-Host "Logs: C:\ProgramData\ControlRemotoPC\logs\agente.log" -ForegroundColor Green
Write-Host "Reinicia el PC para comprobar que arranca solo." -ForegroundColor Green
