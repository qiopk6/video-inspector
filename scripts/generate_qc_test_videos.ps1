param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Ffmpeg = Join-Path $ProjectRoot "tools\ffmpeg\ffmpeg.exe"

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $ProjectRoot "samples\qc-test-videos"
}
if (-not (Test-Path -LiteralPath $Ffmpeg)) {
    throw "Missing tools\ffmpeg\ffmpeg.exe"
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$Samples = @(
    @{
        Name = "00_normal_control.mp4"
        Duration = 12
        Filter = "[0:v]null[v];[1:a]anull[a]"
    },
    @{
        Name = "01_black_only.mp4"
        Duration = 12
        Filter = "[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,4,6.6)'[v];[1:a]anull[a]"
    },
    @{
        Name = "02_silence_only.mp4"
        Duration = 12
        Filter = "[0:v]null[v];[1:a]volume=0:enable='between(t,4,6.6)'[a]"
    },
    @{
        Name = "03_freeze_only.mp4"
        Duration = 12
        Filter = "[0:v]split=2[main][reference];[main][reference]freezeframes=first=100:last=199:replace=99[v];[1:a]anull[a]"
    },
    @{
        Name = "04_black_silence.mp4"
        Duration = 12
        Filter = "[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,4,6.6)'[v];[1:a]volume=0:enable='between(t,4,6.6)'[a]"
    },
    @{
        Name = "05_freeze_silence.mp4"
        Duration = 12
        Filter = "[0:v]split=2[main][reference];[main][reference]freezeframes=first=100:last=199:replace=99[v];[1:a]volume=0:enable='between(t,4,8)'[a]"
    },
    @{
        Name = "06_black_freeze.mp4"
        Duration = 12
        Filter = "[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,4,8)'[v];[1:a]anull[a]"
    },
    @{
        Name = "07_black_silence_freeze_overlap.mp4"
        Duration = 12
        Filter = "[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,4,8)'[v];[1:a]volume=0:enable='between(t,4,8)'[a]"
    },
    @{
        Name = "08_sequential_mixed.mp4"
        Duration = 18
        Filter = "[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,2,4.6)',split=2[main][reference];[main][reference]freezeframes=first=250:last=349:replace=249[v];[1:a]volume=0:enable='between(t,6,8.6)'[a]"
    }
)

foreach ($Sample in $Samples) {
    $OutputPath = Join-Path $OutputDirectory $Sample.Name
    $Duration = [int]$Sample.Duration
    $FfmpegArguments = @(
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=25:duration=$Duration",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=$Duration",
        "-filter_complex", $Sample.Filter,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "800k",
        "-maxrate", "1000k", "-bufsize", "1600k", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "1",
        "-movflags", "+faststart", "-t", "$Duration", $OutputPath
    )

    Write-Host "Generating $($Sample.Name)..."
    & $Ffmpeg @FfmpegArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate $($Sample.Name)"
    }
}

Write-Host "Generated $($Samples.Count) test videos in $OutputDirectory"
