# bench_full_run.ps1 - Track R2 M0 full-scale baseline run (legacy then auto)
# Launched detached via Start-Process so it survives the launching shell exiting.
Set-Location "C:\Users\hcruz.SIG\OneDrive - SIG Systems, Inc\Desktop\The Watcher\The Watcher"
New-Item -ItemType Directory -Force -Path "project\tools\bench_out" | Out-Null
"STARTED $(Get-Date -Format o)" | Out-File "project\tools\bench_out\full_run.status" -Encoding utf8

& powershell -ExecutionPolicy Bypass -File "project\tools\bench_recording.ps1" `
    -Pipeline legacy -Monitors 3 -DurationS 1200 -Crashes 3 -Stall -Churn 200 `
    -SegmentDuration 300 -HardKillTest *> "project\tools\bench_out\full_legacy.log"
"LEGACY_DONE $(Get-Date -Format o)" | Out-File "project\tools\bench_out\full_run.status" -Append -Encoding utf8

& powershell -ExecutionPolicy Bypass -File "project\tools\bench_recording.ps1" `
    -Pipeline auto -Monitors 3 -DurationS 1200 -Crashes 3 -Stall -Churn 200 `
    -SegmentDuration 300 -HardKillTest *> "project\tools\bench_out\full_auto.log"
"AUTO_DONE $(Get-Date -Format o)" | Out-File "project\tools\bench_out\full_run.status" -Append -Encoding utf8

"ALL_DONE $(Get-Date -Format o)" | Out-File "project\tools\bench_out\full_run.status" -Append -Encoding utf8
