#requires -version 5.1
<#
    instalar_agente_nube.ps1
    Deja el Agente en modo NUBE arrancando solo al iniciar sesion, sin ventana.
    NO necesita administrador y NO instala nada con pip (solo usa Python).

    Debe estar en la misma carpeta que agente.py, agente_nube.py y nube.py.
#>

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

foreach ($f in @("agente.py", "agente_nube.py", "nube.py")) {
    if (-not (Test-Path (Join-Path $dir $f))) {
        Write-Host "ERROR: falta $f en esta carpeta." -ForegroundColor Red
        exit 1
    }
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) {
    Write-Host "No se encontro Python. Usa AgenteNube.exe (GitHub Actions) o instala Python 3.10+." -ForegroundColor Red
    exit 1
}
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }

# --- Pedir sala y clave y guardarlas en config.ini ---
$sala = Read-Host "Sala (la misma que pondras en la consola)"
$clave = Read-Host "Clave (minimo 8 caracteres, la misma que en la consola)"
Push-Location $dir
& $py agente_nube.py --configurar $sala $clave
$codigo = $LASTEXITCODE
Pop-Location
if ($codigo -ne 0) {
    Write-Host "Sala o clave no validas. Vuelve a ejecutar el instalador." -ForegroundColor Red
    exit 1
}

# --- Acceso directo en el arranque del usuario ---
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "ControlRemoto-AgenteNube.lnk"
$ws = New-Object -ComObject WScript.Shell
$acceso = $ws.CreateShortcut($lnk)
$acceso.TargetPath = $pyw
$acceso.Arguments = '"' + (Join-Path $dir "agente_nube.py") + '" --oculto'
$acceso.WorkingDirectory = $dir
$acceso.WindowStyle = 7
$acceso.Description = "Agente de Control Remoto (modo nube)"
$acceso.Save()

Write-Host ""
Write-Host "== Listo ==" -ForegroundColor Green
Write-Host "El agente arrancara solo en cada inicio de sesion ($lnk)."
Write-Host "Para arrancarlo ahora mismo:"
Write-Host "   Start-Process '$pyw' '`"$(Join-Path $dir 'agente_nube.py')`" --oculto'"
Write-Host "En el otro PC abre consola_nube.py (o ConsolaNube.exe) con la misma sala y clave."
