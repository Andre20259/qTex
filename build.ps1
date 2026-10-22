# Builds QTeX for Windows.
#   dist\QTeX\QTeX.exe                 - the app (runs without Python installed)
#   installer\QTeX-<ver>-portable.zip  - the same folder zipped, no install needed
#   installer\QTeX-Setup-<ver>.exe     - Windows installer (if Inno Setup 6 is installed)
#
# Usage: double-click build.bat, or in PowerShell:  .\build.ps1   [-NoInstaller]

param([switch]$NoInstaller)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# ---- version (from APP_VERSION in texeditor.py)
$match = Select-String -LiteralPath "texeditor.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
$version = if ($match) { $match.Matches[0].Groups[1].Value } else { "1.0.0" }
Write-Host "QTeX $version"

# ---- find Python
$py = $null
foreach ($cand in @(@("py", "-3"), @("python"))) {
    try {
        $exe = $cand[0]; $rest = @($cand | Select-Object -Skip 1)
        $v = & $exe @rest -c "import sys; print(sys.version_info >= (3, 9))" 2>$null
        if ($v -eq "True") { $py = $cand; break }
    } catch { }
}
if (-not $py) { throw "Python 3.9+ not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')." }

# ---- isolated build environment (keeps your normal Python untouched)
$venv = Join-Path $PSScriptRoot ".venv-build"
$vpy  = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $vpy)) {
    Step "Creating build environment (.venv-build)"
    $exe = $py[0]; $rest = @($py | Select-Object -Skip 1)
    & $exe @rest -m venv "$venv"
    if ($LASTEXITCODE) { throw "Could not create the virtual environment." }
}
Step "Installing build requirements"
& $vpy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $vpy -m pip install -r requirements-build.txt --quiet --disable-pip-version-check
if ($LASTEXITCODE) { throw "pip install failed." }

# ---- PyInstaller
Step "Building QTeX.exe with PyInstaller"
& $vpy -m PyInstaller --noconfirm --clean qtex.spec
if ($LASTEXITCODE) { throw "PyInstaller failed." }
$app = Join-Path $PSScriptRoot "dist\QTeX\QTeX.exe"
if (-not (Test-Path -LiteralPath $app)) { throw "Build finished but $app is missing." }

# ---- license files next to QTeX.exe (go into both the zip and the installer)
Copy-Item -LiteralPath "LICENSE" -Destination "dist\QTeX\LICENSE.txt" -Force
Copy-Item -LiteralPath "THIRD-PARTY-NOTICES.md" -Destination "dist\QTeX\THIRD-PARTY-NOTICES.md" -Force

# ---- portable zip
New-Item -ItemType Directory -Force -Path "installer" | Out-Null
$zip = Join-Path $PSScriptRoot "installer\QTeX-$version-portable.zip"
Step "Creating portable zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path "dist\QTeX" -DestinationPath $zip

# ---- installer (Inno Setup)
$setup = $null
if (-not $NoInstaller) {
    $iscc = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $iscc = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    }
    if ($iscc) {
        Step "Building installer with Inno Setup"
        & $iscc "/DMyAppVersion=$version" "installer.iss"
        if ($LASTEXITCODE) { throw "Inno Setup failed." }
        $setup = Join-Path $PSScriptRoot "installer\QTeX-Setup-$version.exe"
    } else {
        Write-Host "`nInno Setup 6 not found, so no installer was made." -ForegroundColor Yellow
        Write-Host "Install it with:  winget install JRSoftware.InnoSetup   then run this script again." -ForegroundColor Yellow
    }
}

Write-Host "`nDone." -ForegroundColor Green
Write-Host "  App:        $app"
Write-Host "  Portable:   $zip"
if ($setup) { Write-Host "  Installer:  $setup" }
