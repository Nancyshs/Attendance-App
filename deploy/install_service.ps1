<#
  Installs the app as a Windows service using NSSM (https://nssm.cc).
  Run from an elevated PowerShell:   .\deploy\install_service.ps1 -Nssm C:\tools\nssm.exe
  Extra arguments are passed to run_server.ps1, e.g.  -Port 8000 -Workers 4
#>
param(
    [string]$Nssm = "nssm.exe",
    [string]$ServiceName = "AttendanceApp",
    [int]$Port = 8000,
    [int]$Workers = 4,
    [string]$CertFile = "",
    [string]$KeyFile = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$ps = (Get-Command powershell.exe).Source

$scriptArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\run_server.ps1`" -Port $Port -Workers $Workers"
if ($CertFile -and $KeyFile) { $scriptArgs += " -CertFile `"$CertFile`" -KeyFile `"$KeyFile`"" }

& $Nssm install $ServiceName $ps $scriptArgs
& $Nssm set $ServiceName AppDirectory $root
& $Nssm set $ServiceName DisplayName "Attendance & Feedback"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStdout (Join-Path $logs "service.out.log")
& $Nssm set $ServiceName AppStderr (Join-Path $logs "service.err.log")
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 10485760
& $Nssm set $ServiceName AppExit Default Restart
& $Nssm set $ServiceName AppRestartDelay 3000
# make sure MySQL is up before we start
& $Nssm set $ServiceName DependOnService MySQL80

New-NetFirewallRule -DisplayName "Attendance App ($Port)" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -ErrorAction SilentlyContinue | Out-Null
Start-Service $ServiceName
Write-Host "Service '$ServiceName' installed and started on port $Port."
