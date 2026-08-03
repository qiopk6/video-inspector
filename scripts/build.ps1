param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Ffmpeg = Join-Path $ProjectRoot "tools\ffmpeg\ffmpeg.exe"
$Ffprobe = Join-Path $ProjectRoot "tools\ffmpeg\ffprobe.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found: $Python"
}
if (-not (Test-Path -LiteralPath $Ffmpeg) -or -not (Test-Path -LiteralPath $Ffprobe)) {
    throw "Missing tools\ffmpeg\ffmpeg.exe or ffprobe.exe"
}

Push-Location $ProjectRoot
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Automated tests failed" }

    & $Python -m PyInstaller --noconfirm --clean VideoInspector.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    Write-Host "Build completed: $ProjectRoot\dist\VideoInspector\VideoInspector.exe"
}
finally {
    Pop-Location
}
