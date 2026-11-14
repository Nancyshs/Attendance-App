# Started by the Windows service. Not for double-click use.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $root "runtime\python\python.exe"
$env:ENVIRONMENT = "production"
$env:SURVEY_BIND_PORT = if ($env:SURVEY_BIND_PORT) { $env:SURVEY_BIND_PORT } else { "8000" }
$env:SURVEY_HTTPS = "false"
Set-Location $backend
& $python -m uvicorn app.main:app --host 0.0.0.0 --port $env:SURVEY_BIND_PORT --workers 1 --no-server-header --timeout-keep-alive 30
exit $LASTEXITCODE
