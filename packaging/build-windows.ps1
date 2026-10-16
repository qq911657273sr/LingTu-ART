$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

foreach ($tool in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool was not found on PATH. Install FFmpeg before building the desktop app."
    }
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    py -3.12 -m venv (Join-Path $root '.venv')
}
if (-not (Test-Path $python)) {
    throw 'Python 3.12 was not found. Install Python 3.12 and retry.'
}

Push-Location (Join-Path $root 'web')
try {
    npm ci
    npm run build
} finally {
    Pop-Location
}

& $python -m pip install -r (Join-Path $root 'requirements-desktop.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing Python build dependencies failed.' }

& $python -m PyInstaller (Join-Path $root 'artspace-desktop.spec') --noconfirm --clean `
    --workpath (Join-Path $root 'build\pyinstaller') --distpath (Join-Path $root 'build')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $defaultIscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    if (Test-Path $defaultIscc) { $iscc = Get-Item $defaultIscc }
}
if (-not $iscc) {
    $userIscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
    if (Test-Path $userIscc) { $iscc = Get-Item $userIscc }
}
if (-not $iscc) { throw 'Inno Setup 6 was not found. Install it and retry.' }

$compilerPath = if ($iscc.Source) { $iscc.Source } else { $iscc.FullName }
& $compilerPath (Join-Path $root 'packaging\installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Creating the Windows installer failed.' }

Write-Host "Installer created in $(Join-Path $root 'output\installer')."
