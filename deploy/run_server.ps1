<#
  Starts the Attendance app (API + built frontend) with uvicorn.
  Usage:  .\deploy\run_server.ps1 [-Port 8000] [-Workers 4] [-BindHost 0.0.0.0]
          [-CertFile C:\certs\site.crt -KeyFile C:\certs\site.key]   # optional direct HTTPS
#>
param(
    [int]$Port = 8000,
    [int]$Workers = 4,
    [string]$BindHost = "0.0.0.0",
    [string]$CertFile = "",
    [string]$KeyFile = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Virtualenv not found at $py - follow DEPLOY.md step 3." }

Set-Location $backend
# The survey QR reads these. The address itself is detected from this machine, so PUBLIC_URL stays empty.
$env:ENVIRONMENT = "production"
$env:SURVEY_BIND_PORT = "$Port"
$env:SURVEY_HTTPS = $(if ($CertFile -and $KeyFile) { "true" } else { "false" })
$uargs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", $Port,
           "--workers", $Workers, "--no-server-header", "--timeout-keep-alive", "30")
if ($CertFile -and $KeyFile) { $uargs += @("--ssl-certfile", $CertFile, "--ssl-keyfile", $KeyFile) }
& $py @uargs
