<#
.SYNOPSIS
    Fast dev loop for The Watcher — no build/install needed.

.DESCRIPTION
    QML/PySide6 are gone (F3): the UI is Tauri + React. With no arguments,
    this starts the Python backend as a --sidecar (using the in-repo venv,
    for the quickest iteration loop) and hands off to `npm run tauri -- dev`,
    killing the backend when Tauri exits. Pass --daemon/--sidecar to instead
    run the backend directly with no UI (same as before).

.USAGE
    cd project
    .\run_dev.ps1                # backend (--sidecar) + Tauri dev shell
    .\run_dev.ps1 --daemon        # headless Operator daemon only, no UI
    .\run_dev.ps1 --sidecar       # headless IT/Supervisor sidecar only, no UI
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
# The venv lives OUTSIDE the repo (%LOCALAPPDATA%), same convention as
# run.ps1/setup_env.ps1 — it contains machine-specific absolute paths/binaries
# and must not be synced between PCs (or, previously, looked for inside the
# repo where setup_env.ps1 never actually creates it).
$VenvPython = Join-Path $env:LOCALAPPDATA "The Watcher\venv\Scripts\python.exe"
$MainPy     = Join-Path $ScriptDir "app\main.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Dev venv not found at $VenvPython. Run: .\setup_env.ps1 (from the repo root)."
}

if (-not (Test-Path $MainPy)) {
    Write-Error "Cannot find app\main.py in $ScriptDir"
}

# Run from the project root so relative imports resolve correctly
Set-Location $ScriptDir

if ($args.Count -gt 0) {
    Write-Host "=== The Watcher (dev mode, headless) ===" -ForegroundColor Cyan
    Write-Host "Python : $VenvPython" -ForegroundColor Gray
    Write-Host "Entry  : $MainPy $($args -join ' ')" -ForegroundColor Gray
    & $VenvPython $MainPy @args
    exit $LASTEXITCODE
}

Write-Host "=== The Watcher (dev mode): backend --sidecar + Tauri dev shell ===" -ForegroundColor Cyan
# Build artefacts must live outside OneDrive (TD: sync-lock permissions).
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\the-watcher\target"

$backend = Start-Process $VenvPython -ArgumentList $MainPy, "--sidecar" -PassThru -NoNewWindow
Write-Host "  Python backend PID: $($backend.Id)" -ForegroundColor DarkGray
Start-Sleep -Seconds 1

try {
    Set-Location (Split-Path -Parent $ScriptDir)
    npm run tauri -- dev
} finally {
    Write-Host "Stopping Python backend..." -ForegroundColor Yellow
    if (-not $backend.HasExited) {
        $backend.Kill()
    }
}
