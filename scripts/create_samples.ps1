$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Ffmpeg = Join-Path $ProjectRoot "tools\ffmpeg\ffmpeg.exe"
$SampleDir = Join-Path $ProjectRoot "samples"

if (-not (Test-Path -LiteralPath $Ffmpeg)) {
    throw "Missing tools\ffmpeg\ffmpeg.exe"
}
New-Item -ItemType Directory -Force -Path $SampleDir | Out-Null

& $Ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i "testsrc2=size=1280x720:rate=25:duration=6" `
    -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=6" `
    -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p `
    -c:a aac -b:a 128k -shortest (Join-Path $SampleDir "normal.mp4")
if ($LASTEXITCODE -ne 0) { throw "Failed to generate normal.mp4" }

& $Ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i "testsrc2=size=1280x720:rate=25:duration=10" `
    -f lavfi -i "sine=frequency=800:sample_rate=48000:duration=10" `
    -filter_complex "[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,2,5)'[v];[1:a]volume=volume=0:enable='between(t,6,9)'[a]" `
    -map "[v]" -map "[a]" -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p `
    -c:a aac -b:a 128k (Join-Path $SampleDir "black_and_silence.mp4")
if ($LASTEXITCODE -ne 0) { throw "Failed to generate black_and_silence.mp4" }

& $Ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i "testsrc2=size=640x360:rate=15:duration=4" `
    -f lavfi -i "sine=frequency=600:sample_rate=48000:duration=8" `
    -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=4[v]" `
    -map "[v]" -map 1:a:0 -t 8 -c:v libx264 -preset ultrafast -b:v 400k -pix_fmt yuv420p `
    -c:a aac -b:a 96k (Join-Path $SampleDir "freeze_low_quality.mp4")
if ($LASTEXITCODE -ne 0) { throw "Failed to generate freeze_low_quality.mp4" }

Write-Host "Test videos generated: $SampleDir"
