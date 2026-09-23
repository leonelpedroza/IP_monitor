<#
.SYNOPSIS
    Reproducible Windows 11 x64 build of IP Monitor.

.DESCRIPTION
    Creates/uses .venv, installs dependencies, runs lint + tests, builds the
    PyInstaller distribution and packs dist\IPMonitor-<version>-Windows-x64.zip.

.PARAMETER OneFile   Build a single-file IPMonitor.exe in addition to the one-folder build.
.PARAMETER SkipTests Skip ruff and pytest (not recommended for releases).
.PARAMETER Clean     Delete build\ and dist\ first.
.PARAMETER Python    Python launcher/interpreter to create the venv with (default: "py -3.12").

.EXAMPLE
    .\build.ps1
    .\build.ps1 -OneFile -Clean
#>
[CmdletBinding()]
param(
    [switch]$OneFile,
    [switch]$SkipTests,
    [switch]$Clean,
    [string]$Python = "py -3.12"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    Write-Host ">> $Exe $($Arguments -join ' ')" -ForegroundColor Cyan
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE: $Exe $Arguments" }
}

if ($Clean) {
    foreach ($d in @("build", "dist")) { if (Test-Path $d) { Remove-Item $d -Recurse -Force } }
}

# ---- virtual environment ---------------------------------------------------
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment with '$Python'..." -ForegroundColor Yellow
    $parts = $Python -split " "
    Invoke-Checked $parts[0] ($parts[1..($parts.Length-1)] + @("-m", "venv", ".venv"))
}
$pyVersion = & $venvPython -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
Write-Host "Using Python $pyVersion from .venv" -ForegroundColor Green
$minor = [int]($pyVersion.Split(".")[1])
if ($minor -lt 10) { throw "Python 3.10 or newer is required (found $pyVersion)." }
if ($minor -ge 14) { Write-Warning "Python 3.14 detected: supported for running from source, but the packaging baseline is 3.12/3.13. Ensure pyinstaller>=6.16." }

Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
Invoke-Checked $venvPython @("-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt")

$version = & $venvPython -c "import sys; sys.path.insert(0,'src'); from ip_monitor.version import __version__; print(__version__)"
Write-Host "IP Monitor version $version" -ForegroundColor Green

# ---- quality gates ---------------------------------------------------------
if (-not $SkipTests) {
    Invoke-Checked $venvPython @("-m", "ruff", "check", "src", "tests")
    Invoke-Checked $venvPython @("-m", "pytest", "-q")
}

# ---- PyInstaller -----------------------------------------------------------
$env:IPMONITOR_ONEFILE = "0"
Invoke-Checked $venvPython @("-m", "PyInstaller", "packaging\IPMonitor.spec", "--noconfirm", "--clean", "--distpath", "dist", "--workpath", "build\pyinstaller")

$distDir = Join-Path $PSScriptRoot "dist\IPMonitor"
Copy-Item "packaging\README-dist.txt" (Join-Path $distDir "README.txt") -Force
Copy-Item "LICENSE" $distDir -Force
Set-Content -Path (Join-Path $distDir "VERSION") -Value $version -Encoding ascii
New-Item -ItemType Directory -Force -Path (Join-Path $distDir "docs") | Out-Null
Copy-Item "docs\USAGE.md", "docs\TROUBLESHOOTING.md", "CHANGELOG.md" (Join-Path $distDir "docs") -Force

# Third-party licence notices bundled with the executable.
$tpDir = Join-Path $distDir "third_party_licenses"
New-Item -ItemType Directory -Force -Path $tpDir | Out-Null
$site = & $venvPython -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
foreach ($pkg in @("ping3", "matplotlib")) {
    Get-ChildItem -Path $site -Directory -Filter "$pkg*.dist-info" | ForEach-Object {
        Get-ChildItem $_.FullName -Recurse -File | Where-Object { $_.Name -match "LICEN[CS]E" } | ForEach-Object {
            Copy-Item $_.FullName (Join-Path $tpDir ("$pkg-" + $_.Name)) -Force
        }
    }
}
if (Test-Path (Join-Path $distDir "_internal\python*.dll")) { Write-Host "Bundled Python runtime present." }

# ---- ZIP -------------------------------------------------------------------
$zip = Join-Path $PSScriptRoot "dist\IPMonitor-$version-Windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $distDir -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created $zip" -ForegroundColor Green

# ---- optional single-file build -------------------------------------------
if ($OneFile) {
    $env:IPMONITOR_ONEFILE = "1"
    Invoke-Checked $venvPython @("-m", "PyInstaller", "packaging\IPMonitor.spec", "--noconfirm", "--clean", "--distpath", "dist\onefile", "--workpath", "build\pyinstaller-onefile")
    $env:IPMONITOR_ONEFILE = "0"
    $oneZip = Join-Path $PSScriptRoot "dist\IPMonitor-$version-Windows-x64-onefile.zip"
    if (Test-Path $oneZip) { Remove-Item $oneZip -Force }
    Compress-Archive -Path "dist\onefile\IPMonitor.exe", "packaging\README-dist.txt", "LICENSE" -DestinationPath $oneZip
    Write-Host "Created $oneZip" -ForegroundColor Green
}

# ---- smoke test of the frozen executable -----------------------------------
$exe = Join-Path $distDir "IPMonitor.exe"
Invoke-Checked $exe @("--version")
Write-Host "Build complete." -ForegroundColor Green
