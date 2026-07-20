# bench_recording.ps1 - Track R2 M0 bench harness orchestrator
#
# Runs the fixed Track R2 M0 scenario (steady-state + injected crash(es) +
# optional stall + churn xN + optional hard-kill/orphan test) against real
# MonitorWorker instances (bench_scenario.py), captures psutil CPU/RSS
# telemetry via TELEMETRY_CSV, and renders a markdown report
# (bench_report.py).
#
# Uses the SYSTEM Python (NOT the repo .venv - it is broken, see
# TODOS.md / setup_env.ps1) with PYTHONPATH=project, same convention as the
# pytest suite.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File project\tools\bench_recording.ps1
#   powershell -ExecutionPolicy Bypass -File project\tools\bench_recording.ps1 `
#       -Pipeline legacy -Monitors 3 -DurationS 1200 -Crashes 3 -Stall -Churn 200 -HardKillTest
#
# Escenario completo del plan (8 semanas, M0): N monitores, 20 min steady-state,
# 3 crashes, 1 stall, 1 hard-kill, churn x200. Los defaults de abajo son un
# smoke run corto - pasa los parametros de arriba para la corrida a escala real.

param(
    [ValidateSet("legacy", "auto")]
    [string]$Pipeline = "auto",
    [int]$Monitors = 1,
    [double]$DurationS = 60,
    [int]$Crashes = 1,
    [switch]$Stall,
    [int]$Churn = 5,
    [int]$SegmentDuration = 5,
    [switch]$HardKillTest,
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$projectDir = Join-Path $repoRoot "project"

if (-not $OutDir) {
    $OutDir = Join-Path $PSScriptRoot "bench_out"
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $OutDir "$Pipeline-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

# -- Locate system Python 3.13+ (mirrors setup_env.ps1's detection) -----------
function Test-PyVersion($exe) {
    try { $v = & $exe --version 2>&1 } catch { return $false }
    return ($v -match "Python 3\.(1[3-9]|[2-9]\d)")
}
$python = $null
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $cand = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)" 2>$null
    if ($cand -and (Test-PyVersion $cand)) { $python = $cand }
}
if (-not $python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and (Test-PyVersion $cmd.Source)) { $python = $cmd.Source }
}
if (-not $python) {
    Write-Error "No se encontro Python 3.13+ en el sistema. Ver setup_env.ps1."
    exit 1
}
Write-Host "[bench] python: $python"
Write-Host "[bench] run dir: $runDir"

# -- Env for this run ----------------------------------------------------------
$env:PYTHONPATH = $projectDir
$env:CAPTURE_PIPELINE = $Pipeline
$env:TELEMETRY_CSV = Join-Path $runDir "telemetry.csv"
$env:SEGMENT_DIR = Join-Path $runDir "segments"
$env:SEGMENT_DURATION = $SegmentDuration
$resultsJson = Join-Path $runDir "results.json"
$logFile = Join-Path $runDir "scenario.log"

# -- Main scenario: steady-state + crashes + optional stall + churn ----------
$scenarioArgs = @(
    "-m", "tools.bench_scenario", "run",
    "--monitors", $Monitors,
    "--duration-s", $DurationS,
    "--crashes", $Crashes,
    "--churn", $Churn,
    "--segment-duration", $SegmentDuration,
    "--out", $resultsJson
)
if ($Stall) { $scenarioArgs += "--stall" }

Write-Host "[bench] launching scenario: pipeline=$Pipeline monitors=$Monitors duration=${DurationS}s crashes=$Crashes stall=$($Stall.IsPresent) churn=$Churn"
Push-Location $projectDir
try {
    & $python @scenarioArgs | Tee-Object -FilePath $logFile
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[bench] scenario exited with code $LASTEXITCODE - see $logFile"
    }
} finally {
    Pop-Location
}

# -- Optional hard-kill / orphan (Job Object) test ----------------------------
if ($HardKillTest) {
    $hkJson = Join-Path $runDir "hardkill_state.json"
    Write-Host "[bench] hard-kill test: arming child process (self-terminates via os._exit)..."
    Push-Location $projectDir
    try {
        & $python -m tools.bench_scenario hard-kill-test --segment-duration $SegmentDuration --out $hkJson |
            Tee-Object -FilePath (Join-Path $runDir "hardkill.log")
        Start-Sleep -Seconds 3
        Write-Host "[bench] checking for orphaned ffmpeg.exe processes..."
        & $python -m tools.bench_scenario check-orphans --pidfile $hkJson |
            Tee-Object -FilePath (Join-Path $runDir "orphan_check.log")
    } finally {
        Pop-Location
    }
}

# -- Report --------------------------------------------------------------------
$reportMd = Join-Path $runDir "report.md"
Push-Location $projectDir
try {
    & $python -m tools.bench_report --csv $env:TELEMETRY_CSV --scenario $resultsJson --out $reportMd
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "[bench] done. Report: $reportMd"
Get-Content $reportMd
