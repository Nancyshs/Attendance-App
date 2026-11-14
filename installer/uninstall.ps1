$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$nssm = Join-Path $root "runtime\nssm\nssm.exe"
$mysqld = Join-Path $root "runtime\mysql\bin\mysqld.exe"
if (Test-Path $nssm) {
    & $nssm stop AttendanceApp
    & $nssm remove AttendanceApp confirm
}
Stop-Service AttendanceDB -Force -ErrorAction SilentlyContinue
if (Test-Path $mysqld) { & $mysqld --remove AttendanceDB }
Get-NetFirewallRule -DisplayName "Attendance*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
$desk = [Environment]::GetFolderPath("CommonDesktopDirectory")
Remove-Item (Join-Path $desk "الحضور والتقييم.lnk") -Force -ErrorAction SilentlyContinue
$desk = [Environment]::GetFolderPath("Desktop")
Remove-Item (Join-Path $desk "الحضور والتقييم.lnk") -Force -ErrorAction SilentlyContinue
