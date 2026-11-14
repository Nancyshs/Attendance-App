<#
  First run on a new Windows server, after Python 3.12+ and MySQL 8 are installed.
  From the package folder, in an elevated PowerShell:

      .\deploy\setup_server.ps1 -RootPassword "the MySQL root password"

  Creates the database, the app user, .env, the Python environment, the tables,
  and the admin account. Passwords are written to setup-passwords.txt.
#>
param(
    [string]$RootPassword = "",
    [string]$DbPassword = "",
    [string]$AdminPassword = "",
    [string]$AdminUser = "admin",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
Set-Location $root

function New-Token([int]$Bytes = 18) {
    $bytes = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "A").Replace("/", "B")
}

function Find-Python {
    $commands = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $commands += @{ Exe = "py"; Args = @("-3") } }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { $commands += @{ Exe = $python.Source; Args = @() } }
    foreach ($cmd in $commands) {
        $exe = & $cmd.Exe @($cmd.Args + @("-c", "import sys; print(sys.executable if sys.version_info >= (3, 12) else '')"))
        if ($exe) { return "$exe".Trim() }
    }
    throw "Python 3.12 or newer is not installed. Install it from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH', then run this script again."
}

function Find-MySql {
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 8.1\bin\mysql.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    throw "MySQL is not installed. Install MySQL Server 8 (Server only) and remember the root password, then run this script again."
}

if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    throw "frontend\dist is missing. This package should already contain the built pages."
}

$python = Find-Python
$mysql = Find-MySql
Write-Host "Python: $python"
Write-Host "MySQL:  $mysql"

if (-not $RootPassword) {
    $secure = Read-Host "MySQL root password" -AsSecureString
    $RootPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
if (-not $DbPassword) { $DbPassword = New-Token 18 }
if (-not $AdminPassword) { $AdminPassword = New-Token 12 }
$secret = New-Token 36

$sql = @"
CREATE DATABASE IF NOT EXISTS attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'attendance'@'localhost' IDENTIFIED BY '$DbPassword';
ALTER USER 'attendance'@'localhost' IDENTIFIED BY '$DbPassword';
GRANT ALL PRIVILEGES ON attendance.* TO 'attendance'@'localhost';
FLUSH PRIVILEGES;
"@
Write-Host "Creating the attendance database..."
& $mysql --user=root "--password=$RootPassword" --execute=$sql
if ($LASTEXITCODE -ne 0) { throw "MySQL rejected the root password or could not create the database." }

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
    @"
ENVIRONMENT=production
SECRET_KEY=$secret
DATABASE_URL=mysql+pymysql://attendance:${DbPassword}@127.0.0.1:3306/attendance?charset=utf8mb4
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
TIMEZONE=Africa/Cairo
PUBLIC_URL=http://localhost:8000
TRUST_PROXY=false
"@ | Set-Content -Path $envFile -Encoding ascii
    Write-Host "Wrote .env"
} else {
    Write-Host ".env already exists; left it unchanged."
}

$notes = Join-Path $root "setup-passwords.txt"
@"
Attendance app passwords. Keep this file, then move it off the server desktop.

Admin username: $AdminUser
Admin password: $AdminPassword

MySQL user: attendance
MySQL password: $DbPassword
Database: attendance

Open the program at http://THIS-SERVER:8000
The survey QR uses this computer's own address automatically.
"@ | Set-Content -Path $notes -Encoding utf8

$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating the Python environment..."
    & $python -m venv (Join-Path $backend ".venv")
}
Write-Host "Installing Python packages (this can take a few minutes)..."
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r (Join-Path $backend "requirements.txt")

New-Item -ItemType Directory -Force -Path (Join-Path $backend "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null

Write-Host "Creating tables..."
Push-Location $backend
& $venvPy -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Database migration failed." }
Write-Host "Creating the admin account..."
& $venvPy -m scripts.seed --username $AdminUser --password $AdminPassword
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Could not create the admin account." }
Pop-Location

New-NetFirewallRule -DisplayName "Attendance App ($Port)" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -ErrorAction SilentlyContinue | Out-Null

Write-Host ""
Write-Host "Ready. Passwords are in setup-passwords.txt"
Write-Host "Start it now with:  .\deploy\run_server.ps1 -Port $Port"
Write-Host "To start it automatically after reboot, install NSSM and run:"
Write-Host "  .\deploy\install_service.ps1 -Nssm C:\tools\nssm.exe -Port $Port"
