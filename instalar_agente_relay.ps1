#requires -version 5.1
<#
    instalar_agente_relay.ps1
    Prepara el Agente en modo RELE para que arranque solo al iniciar sesion,
    en segundo plano y sin ventana. NO necesita administrador.

    Debe estar en la misma carpeta que agente.py, agente_relay.py y remoto.py.
#>

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

foreach ($f in @("agente.py", "agente_relay.py", "remoto.py")) {
    if (-not (Test-Path (Join-Path $dir $f))) {
        Write-Host "ERROR: falta $f en esta carpeta." -ForegroundColor Red
        exit 1
    }
}

# --- Localizar Python y pythonw (sin ventana) ---
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) {
    Write-Host "No se encontro Python en el PATH. Instala Python 3.10+ (marca 'Add to PATH')." -ForegroundColor Red
    exit 1
}
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }   # si no hay pythonw, usa python

Write-Host "== Instalando dependencia Pillow (para el visor de pantalla) ==" -ForegroundColor Cyan
& $py -m pip install --upgrade pillow

# --- Generar config.ini (secciones [agente] y [relay]) si no existe ---
Write-Host "== Generando config.ini ==" -ForegroundColor Cyan
Push-Location $dir
& $py -c "import agente, agente_relay; agente.cargar_config(); agente_relay.cargar_config_relay()"
Pop-Location

# --- Crear acceso directo en el arranque del usuario ---
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "ControlRemoto-AgenteRelay.lnk"
$ws = New-Object -ComObject WScript.Shell
$acceso = $ws.CreateShortcut($lnk)
$acceso.TargetPath = $pyw
$acceso.Arguments = '"' + (Join-Path $dir "agente_relay.py") + '"'
$acceso.WorkingDirectory = $dir
$acceso.WindowStyle = 7   # minimizado
$acceso.Description = "Agente de Control Remoto (modo rele)"
$acceso.Save()

Write-Host ""
Write-Host "== Listo ==" -ForegroundColor Green
Write-Host "1) Edita config.ini y pon tu clave [agente] y el rele [relay] (host/puerto/sala)."
Write-Host "   Archivo: $(Join-Path $dir 'config.ini')"
Write-Host "2) El agente arrancara solo en cada inicio de sesion (acceso directo en:"
Write-Host "   $startup )."
Write-Host "Para arrancarlo ahora sin reiniciar sesion:" -ForegroundColor Green
Write-Host "   Start-Process -WindowStyle Hidden '$pyw' '`"$(Join-Path $dir 'agente_relay.py')`"'"
