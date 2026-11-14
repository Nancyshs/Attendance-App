# Builds Attendance_Setup.exe. Run on the development machine, not on the server.
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$here = $PSScriptRoot
$root = Split-Path -Parent $here
$cache = Join-Path $here "cache"
$stage = Join-Path $here "staging"
$tmp = Join-Path $here "tmp"
New-Item -ItemType Directory -Force -Path $cache, $tmp | Out-Null
$env:TEMP = $tmp
$env:TMP = $tmp

function Get-File([string]$Url, [string]$Dest, [int64]$MinBytes) {
    if ((Test-Path $Dest) -and ((Get-Item $Dest).Length -ge $MinBytes)) {
        Write-Host "have $Dest"
        return
    }
    Write-Host "download $Url"
    & curl.exe -L --fail --retry 3 --retry-delay 2 -o $Dest $Url
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Dest) -or (Get-Item $Dest).Length -lt $MinBytes) {
        throw "Download failed: $Url"
    }
}

Write-Host "Downloading components..."
Get-File "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip" (Join-Path $cache "python-embed.zip") 8000000
Get-File "https://bootstrap.pypa.io/get-pip.py" (Join-Path $cache "get-pip.py") 100000
Get-File "https://aka.ms/vs/17/release/vc_redist.x64.exe" (Join-Path $cache "vc_redist.x64.exe") 1000000
Get-File "https://nssm.cc/release/nssm-2.24.zip" (Join-Path $cache "nssm.zip") 100000

$mariaUrls = @(
    "https://archive.mariadb.org/mariadb-11.4.5/winx64-packages/mariadb-11.4.5-winx64.zip",
    "https://archive.mariadb.org/mariadb-11.4.4/winx64-packages/mariadb-11.4.4-winx64.zip",
    "https://archive.mariadb.org/mariadb-10.11.11/winx64-packages/mariadb-10.11.11-winx64.zip"
)
$mariaZip = Join-Path $cache "mariadb.zip"
if (-not ((Test-Path $mariaZip) -and (Get-Item $mariaZip).Length -gt 50000000)) {
    $ok = $false
    foreach ($url in $mariaUrls) {
        Write-Host "download $url"
        & curl.exe -L --fail --retry 2 -o $mariaZip $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $mariaZip) -and (Get-Item $mariaZip).Length -gt 50000000) { $ok = $true; break }
        Remove-Item $mariaZip -Force -ErrorAction SilentlyContinue
    }
    if (-not $ok) { throw "Could not download MariaDB." }
}

$inno = "E:\tools\InnoSetup\ISCC.exe"
if (-not (Test-Path $inno)) {
    $innoSetup = Join-Path $cache "innosetup-6.5.0.exe"
    Get-File "https://github.com/jrsoftware/issrc/releases/download/is-6_5_0/innosetup-6.5.0.exe" $innoSetup 1000000
    $extractorZip = Join-Path $cache "innoextract.zip"
    Get-File "https://github.com/UserUnknownFactor/innoextract_win/releases/download/670/innoextract670.zip" $extractorZip 100000
    $extractorDir = Join-Path $cache "innoextract"
    if (-not (Test-Path (Join-Path $extractorDir "innoextract.exe"))) {
        if (Test-Path $extractorDir) { Remove-Item $extractorDir -Recurse -Force }
        Expand-Archive $extractorZip -DestinationPath $extractorDir
    }
    $extractor = Get-ChildItem $extractorDir -Recurse -Filter "innoextract.exe" | Select-Object -First 1
    if (-not $extractor) { throw "innoextract was not found." }
    Write-Host "Unpacking the installer compiler..."
    $innoDir = "E:\tools\InnoSetup"
    if (Test-Path $innoDir) { Remove-Item $innoDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $innoDir | Out-Null
    & $extractor.FullName -e --output-dir $innoDir $innoSetup
    if ($LASTEXITCODE -ne 0) { throw "Could not unpack Inno Setup." }
    $iscc = Get-ChildItem $innoDir -Recurse -Filter "ISCC.exe" | Select-Object -First 1
    if (-not $iscc) { throw "The installer compiler was not found inside Inno Setup." }
    if ($iscc.DirectoryName -ne $innoDir) {
        Copy-Item (Join-Path $iscc.DirectoryName "*") $innoDir -Recurse -Force
    }
    if (-not (Test-Path $inno)) { throw "Inno Setup compiler is missing." }
}

Write-Host "Preparing Python..."
$pyDir = Join-Path $cache "python"
if (-not (Test-Path (Join-Path $pyDir "python.exe"))) {
    if (Test-Path $pyDir) { Remove-Item $pyDir -Recurse -Force }
    Expand-Archive (Join-Path $cache "python-embed.zip") -DestinationPath $pyDir
}
$pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
$zipName = (Get-Content $pth.FullName | Select-Object -First 1).Trim()
@"
$zipName
.
Lib\site-packages
import site
"@ | Set-Content -Path $pth.FullName -Encoding ascii
$py = Join-Path $pyDir "python.exe"
if (-not (Test-Path (Join-Path $pyDir "Lib\site-packages\fastapi"))) {
    & $py (Join-Path $cache "get-pip.py") --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
    & $py -m pip install --disable-pip-version-check -r (Join-Path $here "requirements-server.txt")
    if ($LASTEXITCODE -ne 0) { throw "Python packages failed to install." }
}
$site = Join-Path $pyDir "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $site | Out-Null
Set-Content -Path (Join-Path $site "attendance_backend.pth") -Value "../../../../backend" -Encoding ascii

Write-Host "Preparing the database program..."
$myDir = Join-Path $cache "mysql"
if (-not (Test-Path (Join-Path $myDir "bin\mysql.exe")) -and -not (Test-Path (Join-Path $myDir "bin\mariadb.exe"))) {
    if (Test-Path $myDir) { Remove-Item $myDir -Recurse -Force }
    $expand = Join-Path $cache "mysql-expand"
    if (Test-Path $expand) { Remove-Item $expand -Recurse -Force }
    Expand-Archive $mariaZip -DestinationPath $expand
    $inner = Get-ChildItem $expand -Directory | Select-Object -First 1
    Move-Item $inner.FullName $myDir
    Remove-Item $expand -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Building the pages..."
Push-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Page build failed." }
Pop-Location

Write-Host "Staging..."
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
& robocopy (Join-Path $root "backend") (Join-Path $stage "backend") /E /NFL /NDL /NJH /NJS /nc /ns /np `
    /XD .venv __pycache__ .pytest_cache data tests /XF *.pyc .env | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Could not copy the backend." }
New-Item -ItemType Directory -Force -Path (Join-Path $stage "frontend") | Out-Null
Copy-Item (Join-Path $root "frontend\dist") (Join-Path $stage "frontend\dist") -Recurse
New-Item -ItemType Directory -Force -Path (Join-Path $stage "deploy") | Out-Null
Copy-Item (Join-Path $here "first_run.ps1") (Join-Path $stage "deploy\first_run.ps1")
Copy-Item (Join-Path $here "run_embedded.ps1") (Join-Path $stage "deploy\run_embedded.ps1")
Copy-Item (Join-Path $here "uninstall.ps1") (Join-Path $stage "deploy\uninstall.ps1")
New-Item -ItemType Directory -Force -Path (Join-Path $stage "runtime") | Out-Null
Copy-Item $pyDir (Join-Path $stage "runtime\python") -Recurse
Copy-Item $myDir (Join-Path $stage "runtime\mysql") -Recurse
$shippedData = Join-Path $stage "runtime\mysql\data"
if (Test-Path $shippedData) { Remove-Item $shippedData -Recurse -Force }
$nssmExpand = Join-Path $cache "nssm-expand"
if (Test-Path $nssmExpand) { Remove-Item $nssmExpand -Recurse -Force }
Expand-Archive (Join-Path $cache "nssm.zip") -DestinationPath $nssmExpand
New-Item -ItemType Directory -Force -Path (Join-Path $stage "runtime\nssm") | Out-Null
Copy-Item (Join-Path $nssmExpand "nssm-2.24\win64\nssm.exe") (Join-Path $stage "runtime\nssm\nssm.exe")
Copy-Item (Join-Path $cache "vc_redist.x64.exe") (Join-Path $stage "runtime\vc_redist.x64.exe")

Write-Host "Checking that Python can load the program..."
Push-Location (Join-Path $stage "backend")
$env:SECRET_KEY = "build-check-only-not-a-real-secret-key"
$env:DATABASE_URL = "mysql+pymysql://attendance:build@127.0.0.1:9/attendance?charset=utf8mb4"
& (Join-Path $stage "runtime\python\python.exe") -c "import app.main; print('import-ok')"
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "The bundled Python cannot import the program." }
Pop-Location

# PowerShell 5 needs a BOM to read Arabic text in these scripts.
$utf8bom = New-Object System.Text.UTF8Encoding $true
foreach ($name in @("first_run.ps1", "run_embedded.ps1", "uninstall.ps1")) {
    $path = Join-Path $stage "deploy\$name"
    $text = [IO.File]::ReadAllText($path)
    [IO.File]::WriteAllText($path, $text, $utf8bom)
}

Write-Host "Compiling the installer..."
& $inno (Join-Path $here "attendance.iss")
if ($LASTEXITCODE -ne 0) { throw "Installer compile failed." }
Write-Host "Done: E:\backend\Attendance_Setup.exe"
