param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Pnpm = "C:\Users\62322\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Ffmpeg = Join-Path $ProjectRoot "tools\ffmpeg\ffmpeg.exe"
$Ffprobe = Join-Path $ProjectRoot "tools\ffmpeg\ffprobe.exe"

if (-not (Test-Path -LiteralPath $Python)) { throw "Python environment not found: $Python" }
if (-not (Test-Path -LiteralPath $Pnpm)) { throw "pnpm not found: $Pnpm" }
if (-not (Test-Path -LiteralPath $Ffmpeg) -or -not (Test-Path -LiteralPath $Ffprobe)) {
    throw "Missing tools\ffmpeg\ffmpeg.exe or ffprobe.exe"
}

Push-Location $ProjectRoot
try {
    Push-Location "web"
    try {
        & $Pnpm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    }
    finally {
        Pop-Location
    }

    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Automated tests failed" }

    & $Python -m PyInstaller --noconfirm --clean VideoInspectorWeb.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller web build failed" }

    Write-Host "Build completed: $ProjectRoot\dist\VideoInspectorWeb\VideoInspectorWeb.exe"
}
finally {
    Pop-Location
}
