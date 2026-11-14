# Connects the installed program to the MySQL already on this PC, then installs the Python packages.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$PasswordFile,
    [string]$AdminPasswordFile = ""
)

$ErrorActionPreference = "Stop"
$LogPath = Join-Path $AppDir "installer\setup.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

function Write-Log([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Encode-Url([string]$Value) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in [Text.Encoding]::UTF8.GetBytes($Value)) {
        $ch = [char]$b
        if ($ch -match '[A-Za-z0-9\-_.~]') { [void]$sb.Append($ch) }
        else { [void]$sb.AppendFormat('%{0:X2}', [int]$b) }
    }
    return $sb.ToString()
}

function Test-PythonExe([string]$Exe) {
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) { return $false }
    if ($Exe -match "WindowsApps") { return $false }
    & $Exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    return $LASTEXITCODE -eq 0
}

function Find-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and (Test-PythonExe $cmd.Source)) { return $cmd.Source }
    $candidates = @()
    foreach ($root in @("HKLM:\SOFTWARE\Python\PythonCore", "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore", "HKCU:\SOFTWARE\Python\PythonCore")) {
        Get-ChildItem $root -ErrorAction SilentlyContinue | ForEach-Object {
            $install = Get-ItemProperty (Join-Path $_.PSPath "InstallPath") -ErrorAction SilentlyContinue
            if ($install -and $install."(default)") { $candidates += (Join-Path $install."(default)" "python.exe") }
        }
    }
    $candidates += Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
    $candidates += Get-ChildItem "$env:LocalAppData\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
    foreach ($exe in $candidates) {
        if (Test-PythonExe $exe) { return $exe }
    }
    return $null
}

function Find-Mysql {
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") { return $cmd.Source }
    $roots = @("C:\Program Files\MySQL", "C:\Program Files\MariaDB*")
    foreach ($root in $roots) {
        $hit = Get-ChildItem -Path $root -Recurse -Filter "mysql.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\bin\\mysql.exe$' } |
            Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Start-DatabaseService {
    $services = @(Get-Service -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match 'mysql|mariadb' -or $_.DisplayName -match 'MySQL|MariaDB'
    })
    foreach ($svc in $services) {
        if ($svc.Status -ne "Running") {
            Write-Log "Starting $($svc.Name)"
            Start-Service -Name $svc.Name -ErrorAction SilentlyContinue
        }
    }
}

function Test-PortOpen([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function New-ClientFile([string]$Password) {
    $path = Join-Path $env:TEMP ("attendance-mysql-" + [guid]::NewGuid().ToString("N") + ".cnf")
    $escaped = $Password.Replace('\', '\\').Replace('"', '\"')
    $text = "[client]`r`nuser=root`r`npassword=`"$escaped`"`r`nconnect-timeout=15`r`n"
    [System.IO.File]::WriteAllText($path, $text, [System.Text.Encoding]::Default)
    return $path
}

function Invoke-Mysql([string]$Mysql, [string]$Cnf, [string]$MysqlArgs, [string]$Sql) {
    $batch = Join-Path $env:TEMP ("attendance-sql-" + [guid]::NewGuid().ToString("N") + ".sql")
    [System.IO.File]::WriteAllText($batch, $Sql, [System.Text.Encoding]::Default)
    $cmd = Join-Path $env:TEMP ("attendance-sql-" + [guid]::NewGuid().ToString("N") + ".cmd")
    $line = "@echo off`r`n`"$Mysql`" --defaults-extra-file=`"$Cnf`" $MysqlArgs < `"$batch`"`r`nexit /b %ERRORLEVEL%`r`n"
    [System.IO.File]::WriteAllText($cmd, $line, [System.Text.Encoding]::ASCII)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = "cmd.exe"
    $info.Arguments = "/c `"$cmd`""
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($info)
    $proc.WaitForExit()
    $code = $proc.ExitCode
    Remove-Item $batch, $cmd -Force -ErrorAction SilentlyContinue
    return $code
}

try {
    $password = [System.IO.File]::ReadAllText($PasswordFile, [System.Text.Encoding]::Default).Trim()
    Remove-Item -LiteralPath $PasswordFile -Force -ErrorAction SilentlyContinue
    if ($password -match "[\r\n]") { Write-Log "MySQL password contains a line break."; exit 1 }

    $adminPassword = ""
    if ($AdminPasswordFile -and (Test-Path -LiteralPath $AdminPasswordFile)) {
        $adminPassword = [System.IO.File]::ReadAllText($AdminPasswordFile, [System.Text.Encoding]::Default).Trim()
        Remove-Item -LiteralPath $AdminPasswordFile -Force -ErrorAction SilentlyContinue
    }
    if ([string]::IsNullOrWhiteSpace($adminPassword) -or $adminPassword -match "[\r\n]") {
        Write-Log "Admin password is empty."
        exit 1
    }

    Write-Log "Looking for MySQL."
    Start-DatabaseService
    $ready = $false
    foreach ($i in 1..20) {
        if (Test-PortOpen 3306) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        Write-Log "MySQL is not listening on port 3306. Start the MySQL service, then run setup again."
        exit 1
    }

    $mysql = Find-Mysql
    if (-not $mysql) {
        Write-Log "mysql.exe was not found. Install MySQL, then run setup again."
        exit 1
    }
    Write-Log "MySQL client: $mysql"

    $cnf = New-ClientFile $password
    $tcp = "--protocol=tcp -h 127.0.0.1 -P 3306 --batch"
    $code = Invoke-Mysql $mysql $cnf $tcp "SELECT 1;"
    if ($code -ne 0) {
        Write-Log "TCP login failed. Trying the local MySQL pipe."
        $pipe = Invoke-Mysql $mysql $cnf "-h localhost --batch" "SELECT 1;"
        if ($pipe -ne 0) {
            Remove-Item $cnf -Force -ErrorAction SilentlyContinue
            Write-Log "Could not sign in to MySQL as root. The password is wrong, or MySQL is not running."
            exit 1
        }
        $sqlPassword = $password.Replace("'", "''")
        $grant = @"
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '$sqlPassword';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '$sqlPassword';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;
"@
        $grantCode = Invoke-Mysql $mysql $cnf "-h localhost --batch" $grant
        if ($grantCode -ne 0) {
            Remove-Item $cnf -Force -ErrorAction SilentlyContinue
            Write-Log "MySQL accepted the password locally, but the program still cannot connect."
            exit 1
        }
        $code = Invoke-Mysql $mysql $cnf $tcp "SELECT 1;"
        if ($code -ne 0) {
            Remove-Item $cnf -Force -ErrorAction SilentlyContinue
            Write-Log "MySQL root cannot be used from 127.0.0.1."
            exit 1
        }
    }

    $created = Invoke-Mysql $mysql $cnf $tcp "CREATE DATABASE IF NOT EXISTS attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    Remove-Item $cnf -Force -ErrorAction SilentlyContinue
    if ($created -ne 0) {
        Write-Log "Could not create the attendance database."
        exit 1
    }
    Write-Log "Database attendance is ready."

    $python = Find-Python
    if (-not $python) {
        Write-Log "Python 3.11 or newer was not found. Install Python, then run setup again."
        exit 1
    }
    Write-Log "Python: $python"

    Write-Log "Granting users permission to write program data."
    & icacls.exe $AppDir /grant "*S-1-5-32-545:(OI)(CI)M" /C /Q | Out-Null

    $backend = Join-Path $AppDir "backend"
    $bytes = New-Object byte[] 36
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "A").Replace("/", "B")
    $dbUrl = "mysql+pymysql://root:$(Encode-Url $password)@127.0.0.1:3306/attendance?charset=utf8mb4"
    $port = 8000
    while ((Test-PortOpen $port) -and $port -lt 8020) { $port++ }
    if (Test-PortOpen $port) { Write-Log "No free port between 8000 and 8020."; exit 1 }

    @"
ENVIRONMENT=production
SECRET_KEY=$secret
DATABASE_URL=$dbUrl
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
TIMEZONE=Africa/Cairo
PUBLIC_URL=http://localhost:$port
SURVEY_BIND_PORT=$port
TRUST_PROXY=false
"@ | Set-Content -LiteralPath (Join-Path $backend ".env") -Encoding ascii
    Set-Content -LiteralPath (Join-Path $AppDir "app-port.txt") -Value $port -Encoding ascii

    $venvPy = Join-Path $backend ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-Log "Creating the Python environment."
        & $python -m venv (Join-Path $backend ".venv")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) {
            Write-Log "Could not create the Python environment."
            exit 1
        }
    }

    $wheels = Join-Path $AppDir "wheels"
    Write-Log "Installing Python packages."
    & $venvPy -m pip install --disable-pip-version-check --no-index --find-links $wheels -r (Join-Path $backend "requirements-server.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Offline install failed. Trying the internet."
        & $venvPy -m pip install --disable-pip-version-check -r (Join-Path $backend "requirements-server.txt")
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Python packages failed to install."
            exit 1
        }
    }

    Write-Log "Creating tables."
    Push-Location $backend
    & $venvPy -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Log "Could not create the tables."; exit 1 }
    Write-Log "Creating the admin account."
    & $venvPy -m scripts.seed --username admin --password $adminPassword
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Log "Could not create the admin account."; exit 1 }
    Pop-Location

    New-NetFirewallRule -DisplayName "Attendance ($port)" -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -ErrorAction SilentlyContinue | Out-Null

    $ip = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -ExpandProperty IPAddress) | Select-Object -First 1
    if (-not $ip) { $ip = "localhost" }
    $note = Join-Path $AppDir "LOGIN.txt"
    @"
تم تثبيت برنامج الحضور والتقييم

على هذا الجهاز افتحي:
http://localhost:$port

من أي جهاز آخر على الشبكة افتحي:
http://${ip}:$port

اسم المستخدم: admin
كلمة السر: $adminPassword

احتفظي بهذه الورقة. بعد الدخول يمكن تغيير كلمة السر من داخل البرنامج.
"@ | Set-Content -LiteralPath $note -Encoding utf8

    Write-Log "Starting the program on port $port."
    Start-Process -FilePath $venvPy -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$port") -WorkingDirectory $backend -WindowStyle Minimized
    $up = $false
    foreach ($i in 1..30) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/health/ready" -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $up = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $up) {
        Write-Log "The program did not answer yet. Open the desktop shortcut and leave its window open."
        exit 1
    }
    Start-Process notepad.exe $note
    Start-Process "http://localhost:$port"
    Write-Log "Ready on port $port."
    exit 0
} catch {
    Write-Log $_.Exception.Message
    exit 1
}
