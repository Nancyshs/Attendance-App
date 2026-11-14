# Runs once at the end of the installer. Prepares the database, the admin account, and the service.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $root "runtime\python\python.exe"
$mysqlBin = Join-Path $root "runtime\mysql\bin"
$mysqld = Join-Path $mysqlBin "mysqld.exe"
if (-not (Test-Path $mysqld)) { $mysqld = Join-Path $mysqlBin "mariadbd.exe" }
$mysql = Join-Path $mysqlBin "mysql.exe"
$nssm = Join-Path $root "runtime\nssm\nssm.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "install.log"

function Note([string]$Text) {
    $line = "{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $Text
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Fail([string]$Text) {
    Note $Text
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($Text, "Attendance") | Out-Null
    exit 1
}

function New-Password([int]$Length = 16) {
    $chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789".ToCharArray()
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Test-PortFree([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Invoke-Logged([string]$FilePath, [string]$ArgumentLine, [string]$InputFile) {
    # A batch file keeps quotes intact. cmd /c itself strips quotes and breaks paths that contain spaces.
    $batch = Join-Path $env:TEMP ("attendance-" + [guid]::NewGuid().ToString("N") + ".cmd")
    $stdin = ""
    if ($InputFile) { $stdin = " < `"$InputFile`"" }
    $content = "@echo off`r`n`"$FilePath`" $ArgumentLine$stdin >> `"$log`" 2>&1`r`nexit /b %ERRORLEVEL%`r`n"
    [System.IO.File]::WriteAllText($batch, $content, [System.Text.Encoding]::ASCII)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = "cmd.exe"
    $info.Arguments = "/c `"$batch`""
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($info)
    $proc.WaitForExit()
    $code = $proc.ExitCode
    Remove-Item $batch -Force -ErrorAction SilentlyContinue
    return $code
}

try {
    Note "start $root"
    if (-not (Test-Path $python)) { Fail "Python runtime is missing from the installation folder." }
    if (-not (Test-Path $mysqld)) { Fail "Database runtime is missing from the installation folder." }

    $vc = Join-Path $root "runtime\vc_redist.x64.exe"
    $vcKey = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
    if (-not $vcKey) { $vcKey = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue }
    if ($vcKey -and $vcKey.Installed -eq 1) {
        Note "visual c++ runtime already installed"
    } elseif (Test-Path $vc) {
        Note "visual c++ runtime"
        Start-Process -FilePath $vc -ArgumentList "/install", "/quiet", "/norestart" -Wait
    }

    $dbPort = 3306
    $ini = Join-Path $root "runtime\mysql\my.ini"
    $existing = Get-Content $ini -ErrorAction SilentlyContinue | Where-Object { $_ -like "port=*" } | Select-Object -First 1
    if ($existing -match "port=(\d+)") { $dbPort = [int]$Matches[1] }
    if (-not (Test-Path $ini)) {
        while (-not (Test-PortFree $dbPort) -and $dbPort -lt 3320) { $dbPort++ }
        if (-not (Test-PortFree $dbPort)) { Fail "Could not find a free port for the database." }
        $base = ($root + "\runtime\mysql") -replace "\\", "/"
        $plugin = ($root + "\runtime\mysql\lib\plugin") -replace "\\", "/"
        @"
[mysqld]
basedir="$base"
datadir="$base/data"
port=$dbPort
bind-address=127.0.0.1
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
max_connections=200
plugin-dir="$plugin"
[client]
port=$dbPort
"@ | Set-Content -Path $ini -Encoding ascii
        Note "database port $dbPort"
    }

    $dataDir = Join-Path $root "runtime\mysql\data"
    $needsInit = -not (Test-Path (Join-Path $dataDir "mysql"))
    if ($needsInit) {
        Note "initialize empty database"
        $dbSvc = Get-Service AttendanceDB -ErrorAction SilentlyContinue
        if ($dbSvc -and $dbSvc.Status -ne "Stopped") { Stop-Service AttendanceDB -Force -ErrorAction SilentlyContinue }
        if (Test-Path $dataDir) { Remove-Item $dataDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
        # MariaDB on Windows rejects mysqld --initialize-insecure. mariadb-install-db creates the system tables and leaves root with an empty password.
        $installDb = Join-Path $mysqlBin "mariadb-install-db.exe"
        if (-not (Test-Path $installDb)) { $installDb = Join-Path $mysqlBin "mysql_install_db.exe" }
        if (-not (Test-Path $installDb)) { Fail "Database setup program is missing from the installation folder." }
        Note "mariadb-install-db"
        $code = Invoke-Logged $installDb "--datadir=`"$dataDir`" --port=$dbPort --config=`"$ini`""
        if ($code -ne 0 -or -not (Test-Path (Join-Path $dataDir "mysql"))) {
            if (Test-Path $dataDir) { Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue }
            Fail "Database initialization failed. See logs\install.log"
        }
    }

    $svc = Get-Service AttendanceDB -ErrorAction SilentlyContinue
    if (-not $svc) {
        Note "install database service"
        $code = Invoke-Logged $mysqld "--defaults-file=`"$ini`" --install AttendanceDB"
        if ($code -ne 0) { Fail "Could not install the database service." }
    }
    if ((Get-Service AttendanceDB).Status -ne "Running") {
        Start-Service AttendanceDB
    }

    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        & $mysql --protocol=tcp -h 127.0.0.1 -P $dbPort -u root -e "SELECT 1" 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { Fail "The database service did not start. See logs\install.log" }

    $envFile = Join-Path $root ".env"
    $passFile = Join-Path $root "LOGIN.txt"
    $fresh = -not (Test-Path $envFile)
    if (-not $fresh) { Note "already installed, keeping the database and passwords" }
    if ($fresh) {
        $dbPass = New-Password 18
        $adminPass = New-Password 12
        $secret = New-Password 36
        $sql = @"
CREATE DATABASE IF NOT EXISTS attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'attendance'@'localhost' IDENTIFIED BY '$dbPass';
CREATE USER IF NOT EXISTS 'attendance'@'127.0.0.1' IDENTIFIED BY '$dbPass';
ALTER USER 'attendance'@'localhost' IDENTIFIED BY '$dbPass';
ALTER USER 'attendance'@'127.0.0.1' IDENTIFIED BY '$dbPass';
GRANT ALL PRIVILEGES ON attendance.* TO 'attendance'@'localhost';
GRANT ALL PRIVILEGES ON attendance.* TO 'attendance'@'127.0.0.1';
FLUSH PRIVILEGES;
"@
        $sqlFile = Join-Path $env:TEMP "attendance-init.sql"
        Set-Content -Path $sqlFile -Value $sql -Encoding ascii
        $code = Invoke-Logged $mysql "--protocol=tcp -h 127.0.0.1 -P $dbPort -u root" $sqlFile
        if ($code -ne 0) { Fail "Could not create the attendance database." }
        @"
ENVIRONMENT=production
SECRET_KEY=$secret
DATABASE_URL=mysql+pymysql://attendance:${dbPass}@127.0.0.1:${dbPort}/attendance?charset=utf8mb4
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
TIMEZONE=Africa/Cairo
PUBLIC_URL=http://localhost:8000
TRUST_PROXY=false
"@ | Set-Content -Path $envFile -Encoding ascii

        $appPort = 8000
        while (-not (Test-PortFree $appPort) -and $appPort -lt 8020) { $appPort++ }
        Set-Content -Path (Join-Path $root "app-port.txt") -Value $appPort -Encoding ascii

        $ip = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
            Select-Object -ExpandProperty IPAddress) | Select-Object -First 1
        if (-not $ip) { $ip = "localhost" }
        @"
تم تثبيت برنامج الحضور والتقييم

على هذا الجهاز افتحي:
http://localhost:$appPort

من أي جهاز آخر على الشبكة افتحي:
http://${ip}:$appPort

اسم المستخدم: admin
كلمة السر: $adminPass

احتفظي بهذه الورقة. بعد الدخول يمكن تغيير كلمة السر من داخل البرنامج.
"@ | Set-Content -Path $passFile -Encoding utf8
    }

    Note "migrate"
    Push-Location $backend
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        if ($fresh) { Remove-Item $envFile -Force }
        Fail "Could not create the tables."
    }
    if ($fresh) {
        Note "admin"
        & $python -m scripts.seed --username admin --password $adminPass
        if ($LASTEXITCODE -ne 0) { Pop-Location; Remove-Item $envFile -Force; Fail "Could not create the admin account." }
    }
    Pop-Location

    $appPort = 8000
    $portFile = Join-Path $root "app-port.txt"
    if (Test-Path $portFile) { $appPort = [int](Get-Content $portFile -Raw).Trim() }

    if (-not (Get-Service AttendanceApp -ErrorAction SilentlyContinue)) {
        Note "install app service"
        & $nssm install AttendanceApp powershell.exe
        & $nssm set AttendanceApp AppParameters "-NoProfile -ExecutionPolicy Bypass -File `"$root\deploy\run_embedded.ps1`""
        & $nssm set AttendanceApp AppDirectory $backend
        & $nssm set AttendanceApp DisplayName "Attendance"
        & $nssm set AttendanceApp Start SERVICE_AUTO_START
        & $nssm set AttendanceApp DependOnService AttendanceDB
        & $nssm set AttendanceApp AppStdout (Join-Path $logDir "service.out.log")
        & $nssm set AttendanceApp AppStderr (Join-Path $logDir "service.err.log")
        & $nssm set AttendanceApp AppRotateFiles 1
        & $nssm set AttendanceApp AppRotateBytes 10485760
        & $nssm set AttendanceApp AppExit Default Restart
        & $nssm set AttendanceApp AppRestartDelay 4000
        & $nssm set AttendanceApp AppEnvironmentExtra "SURVEY_BIND_PORT=$appPort"
    }
    $appSvc = Get-Service AttendanceApp
    if ($appSvc.Status -eq "Running") { Restart-Service AttendanceApp -Force }
    else { Start-Service AttendanceApp }

    New-NetFirewallRule -DisplayName "Attendance ($appPort)" -Direction Inbound -Protocol TCP -LocalPort $appPort -Action Allow -ErrorAction SilentlyContinue | Out-Null

    $shell = New-Object -ComObject WScript.Shell
    foreach ($desk in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("CommonDesktopDirectory"))) {
        if (-not $desk) { continue }
        $lnk = $shell.CreateShortcut((Join-Path $desk "الحضور والتقييم.lnk"))
        $lnk.TargetPath = "cmd.exe"
        $lnk.Arguments = "/c start http://localhost:$appPort"
        $lnk.WindowStyle = 7
        $lnk.Description = "Attendance"
        $lnk.Save()
    }

    $up = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$appPort/api/health/ready" -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $up = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $up) { Fail "The program did not start. See logs\service.err.log" }
    Note "ready on $appPort"
    if ($fresh -and (Test-Path $passFile)) {
        Start-Process notepad.exe $passFile
        Start-Process "http://localhost:$appPort"
    }
    exit 0
}
catch {
    Fail $_.Exception.Message
}
