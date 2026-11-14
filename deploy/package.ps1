<#
  Builds the pages and packs a folder you can copy to a new Windows server.
  The server does not need Node.js. It does need Python 3.12+ and MySQL 8.

      .\deploy\package.ps1
#>
param(
    [string]$Output = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Output) {
    $Output = Join-Path (Split-Path $root -Parent) "Attendance_App_Server.zip"
}

Write-Host "Building the pages..."
Push-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "The page build failed." }
Pop-Location
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    throw "frontend\dist\index.html was not produced."
}

$stage = Join-Path $env:TEMP ("Attendance_App_package_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
    $backendOut = Join-Path $stage "backend"
    New-Item -ItemType Directory -Force -Path $backendOut | Out-Null
    & robocopy (Join-Path $root "backend") $backendOut /E /NFL /NDL /NJH /NJS /nc /ns /np `
        /XD .venv __pycache__ .pytest_cache data tests `
        /XF *.pyc | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Could not copy the backend (robocopy $LASTEXITCODE)." }

    New-Item -ItemType Directory -Force -Path (Join-Path $stage "frontend") | Out-Null
    Copy-Item (Join-Path $root "frontend\dist") (Join-Path $stage "frontend\dist") -Recurse
    Copy-Item (Join-Path $root "deploy") (Join-Path $stage "deploy") -Recurse
    foreach ($name in @(".env.example", "DEPLOY.md", "README.md")) {
        $src = Join-Path $root $name
        if (Test-Path $src) { Copy-Item $src (Join-Path $stage $name) }
    }
    Copy-Item (Join-Path $PSScriptRoot "اقرأني.txt") (Join-Path $stage "اقرأني.txt")

    if (Test-Path $Output) { Remove-Item $Output -Force }
    $items = @(Get-ChildItem -Force $stage | ForEach-Object { $_.FullName })
    Compress-Archive -Path $items -DestinationPath $Output
    $mb = [math]::Round((Get-Item $Output).Length / 1MB, 1)
    Write-Host "Package: $Output ($mb MB)"
}
finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
