# The Watcher launcher — DEV MODE
# Siempre arranca desde cero: borra user_config y requests para que
# aparezca el wizard de selección de rol en cada ejecución.
#
# Usage:
#   .\run.ps1                 # QML UI (default)
#   .\run.ps1 -Mode daemon    # headless Operator daemon (no Qt), ADR-0010
#   .\run.ps1 -Mode sidecar   # headless IT/Supervisor sidecar (stdin shutdown)
param(
    [ValidateSet("qml", "daemon", "sidecar")]
    [string]$Mode = "qml"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# El venv vive FUERA de OneDrive (en %LOCALAPPDATA%) para no sincronizarse entre PCs.
$venvDir = Join-Path $env:LOCALAPPDATA "The Watcher\venv"

if (-not (Test-Path "$venvDir\Scripts\Activate.ps1")) {
    $setup = Join-Path $scriptDir "..\setup_env.ps1"
    if (Test-Path $setup) {
        Write-Host "Entorno virtual no encontrado -> ejecutando setup_env.ps1..." -ForegroundColor Yellow
        & powershell -ExecutionPolicy Bypass -File $setup
    }
    if (-not (Test-Path "$venvDir\Scripts\Activate.ps1")) {
        Write-Error "No se pudo preparar el entorno virtual. Ejecuta setup_env.ps1 manualmente."
        exit 1
    }
}

& "$venvDir\Scripts\Activate.ps1"

# ── Reset de estado: forzar flujo de instalación/rol ─────────────────────────
$configDir = "$env:LOCALAPPDATA\The Watcher"
$userConfig = "$configDir\user_config.json"
$requestsDir = "$configDir\requests"

if (Test-Path $userConfig) {
    Remove-Item -Force $userConfig
    Write-Host "[reset] user_config.json eliminado → el wizard de rol aparecerá al iniciar."
}

if (Test-Path $requestsDir) {
    Remove-Item -Recurse -Force $requestsDir
    Write-Host "[reset] Carpeta requests/ eliminada."
}

Write-Host "[reset] Listo. Arrancando desde la seleccion de rol..." -ForegroundColor Cyan

# ── Qt Quick Controls style ───────────────────────────────────────────────────
# Force the "Basic" style so custom `background` properties on TextField,
# ComboBox, etc. are respected.  The default native Windows style ignores them
# and emits QML warnings.
$env:QT_QUICK_CONTROLS_STYLE = "Basic"

# ── Qt plugin paths ───────────────────────────────────────────────────────────
$pyside6PluginsPath = & "$venvDir\Scripts\python.exe" -c `
    "import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent / 'plugins')" `
    2>$null
if ($pyside6PluginsPath) {
    $env:QT_PLUGIN_PATH = $pyside6PluginsPath
    Write-Host "Qt plugin path: $env:QT_PLUGIN_PATH"
}

$pyside6QmlPath = & "$venvDir\Scripts\python.exe" -c `
    "import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent / 'qml')" `
    2>$null
if ($pyside6QmlPath) {
    $env:QML2_IMPORT_PATH = $pyside6QmlPath
    Write-Host "QML import path: $env:QML2_IMPORT_PATH"
}

# ── Launch by mode (ADR-0010) ─────────────────────────────────────────────────
# QML is the default; daemon/sidecar run headless over the same IPC contract.
switch ($Mode) {
    "daemon"  { Write-Host "Launching headless DAEMON (Operator topology)..." -ForegroundColor Cyan
                python -m app.main --daemon }
    "sidecar" { Write-Host "Launching headless SIDECAR (IT/Supervisor topology)..." -ForegroundColor Cyan
                python -m app.main --sidecar }
    default   { python -m app.main }
}
