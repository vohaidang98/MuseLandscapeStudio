param(
    [string]$Python = 'py',
    [string]$InnoCompiler = ''
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
Push-Location $project
try {
    if (!(Test-Path '.venv-build\Scripts\python.exe')) {
        if ($Python -eq 'py') { & $Python -3.12 -m venv .venv-build }
        else { & $Python -m venv .venv-build }
        if ($LASTEXITCODE) { throw 'Cannot create Python 3.12 build environment' }
    }
    $buildPython = Join-Path $project '.venv-build\Scripts\python.exe'
    $env:PIP_CONFIG_FILE = 'NUL'
    & $buildPython -m pip install --no-cache-dir setuptools wheel
    if ($LASTEXITCODE) { throw 'Cannot install wheel tooling' }
    & $buildPython -m pip install --no-cache-dir --no-build-isolation -r windows/requirements-build.lock
    if ($LASTEXITCODE) { throw 'Cannot install build dependencies' }
    Push-Location dashboard
    try {
        & npm.cmd ci --ignore-scripts --no-audit --no-fund --cache ../windows/npm-cache
        if ($LASTEXITCODE) { throw 'npm ci failed' }
        & node node_modules/typescript/bin/tsc -b
        if ($LASTEXITCODE) { throw 'TypeScript check failed' }
        & node node_modules/vite/bin/vite.js build --configLoader native
        if ($LASTEXITCODE) { throw 'Dashboard build failed' }
    } finally { Pop-Location }
    if (!(Test-Path windows/bin/ffmpeg.exe) -or !(Test-Path windows/bin/ffprobe.exe)) {
        throw 'Missing vendored FFmpeg. Restore windows/bin and windows/ffmpeg-notices from this project.'
    }
    $env:PYTHONPATH = $project
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $project 'windows/pyinstaller-cache'
    & $buildPython -m PyInstaller --noconfirm windows/FrameWeaver.spec
    if ($LASTEXITCODE) { throw 'PyInstaller build failed' }
    if (!$InnoCompiler) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($command) { $InnoCompiler = $command.Source }
        else { throw 'Pass -InnoCompiler with the full path to Inno Setup 6 ISCC.exe' }
    }
    & $InnoCompiler windows/installer.iss
    if ($LASTEXITCODE) { throw 'Installer compilation failed' }
    Get-FileHash release/Muse-Landscape-Studio-1.3.2-Windows-x64-Setup.exe -Algorithm SHA256
} finally { Pop-Location }




