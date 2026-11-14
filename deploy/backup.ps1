<#
  Nightly backup: MySQL dump (+ photos folder) with retention.
  Schedule it (elevated PowerShell):
    schtasks /Create /TN "AttendanceBackup" /SC DAILY /ST 23:30 /RU SYSTEM ^
      /TR "powershell -NoProfile -ExecutionPolicy Bypass -File E:\path\to\deploy\backup.ps1"
  Credentials are read from a MySQL option file so no password appears on the command line:
    C:\ProgramData\attendance\backup.cnf   ->   [client]\nuser=attendance\npassword=...
#>
param(
    [string]$MysqlDump = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
    [string]$Database = "attendance",
    [string]$Cnf = "C:\ProgramData\attendance\backup.cnf",
    [string]$BackupDir = "",
    [int]$KeepDays = 30
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $BackupDir) { $BackupDir = Join-Path $root "backups" }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$sql = Join-Path $BackupDir "attendance_$stamp.sql"

& $MysqlDump "--defaults-extra-file=$Cnf" --single-transaction --routines --default-character-set=utf8mb4 --result-file=$sql $Database
if ($LASTEXITCODE -ne 0) { throw "mysqldump failed with exit code $LASTEXITCODE" }

$photos = Join-Path $root "backend\data"
if (Test-Path $photos) {
    Compress-Archive -Path $sql, $photos -DestinationPath "$sql.zip" -Force
} else {
    Compress-Archive -Path $sql -DestinationPath "$sql.zip" -Force
}
Remove-Item $sql
Get-ChildItem $BackupDir -Filter "attendance_*.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item -Force
Write-Host "Backup written: $sql.zip"
