# Builds E:\backend\Attendance_Setup.exe from the Python and MySQL already on the target PC.
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$here = $PSScriptRoot
$root = Split-Path (Split-Path $here -Parent) -Parent
$stage = Join-Path $here "staging"
$inno = "E:\tools\InnoSetup\ISCC.exe"

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
Copy-Item (Join-Path $here "..\requirements-server.txt") (Join-Path $stage "backend\requirements-server.txt")
New-Item -ItemType Directory -Force -Path (Join-Path $stage "frontend") | Out-Null
Copy-Item (Join-Path $root "frontend\dist") (Join-Path $stage "frontend\dist") -Recurse
New-Item -ItemType Directory -Force -Path (Join-Path $stage "installer") | Out-Null
Copy-Item (Join-Path $here "configure.ps1") (Join-Path $stage "installer\configure.ps1")
Copy-Item (Join-Path $here "Run.bat") (Join-Path $stage "Run.bat")

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python was not found, so the package libraries cannot be prepared." }
    $py = $cmd.Source
}
$wheels = Join-Path $stage "wheels"
New-Item -ItemType Directory -Force -Path $wheels | Out-Null
Write-Host "Downloading Python packages..."
$req = Join-Path $stage "backend\requirements-server.txt"
$downloaded = $false
foreach ($ver in @("3.11", "3.12", "3.13", "3.14")) {
    Write-Host "Python $ver"
    & $py -m pip download --disable-pip-version-check -r $req -d $wheels --python-version $ver --platform win_amd64 --implementation cp --only-binary=:all:
    if ($LASTEXITCODE -eq 0) { $downloaded = $true } else { Write-Host "Python $ver wheels are incomplete." }
}
if (-not $downloaded) { throw "Could not download the Python packages." }

$utf8bom = New-Object System.Text.UTF8Encoding $true
foreach ($name in @("installer\configure.ps1", "Run.bat")) {
    $path = Join-Path $stage $name
    $text = [IO.File]::ReadAllText($path)
    [IO.File]::WriteAllText($path, $text, $utf8bom)
}

if (-not (Test-Path $inno)) { throw "Inno Setup compiler was not found at $inno" }
Write-Host "Compiling the installer..."
& $inno (Join-Path $here "attendance.iss")
if ($LASTEXITCODE -ne 0) { throw "Installer compile failed." }
Write-Host "Done: E:\backend\Attendance_Setup.exe"
