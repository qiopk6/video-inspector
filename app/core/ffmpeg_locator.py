from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FFmpegTools:
    ffmpeg: Path
    ffprobe: Path


def _candidate_directories(configured: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if configured:
        candidates.append(configured)

    env_dir = os.environ.get("VIDEO_INSPECTOR_FFMPEG_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [executable_dir / "tools" / "ffmpeg", executable_dir / "_internal" / "tools" / "ffmpeg"]
        )
    else:
        project_root = Path(__file__).resolve().parents[2]
        candidates.append(project_root / "tools" / "ffmpeg")
    return candidates


def locate_ffmpeg(configured: Path | None = None) -> FFmpegTools:
    for directory in _candidate_directories(configured):
        ffmpeg = directory / "ffmpeg.exe"
        ffprobe = directory / "ffprobe.exe"
        if ffmpeg.is_file() and ffprobe.is_file():
            return FFmpegTools(ffmpeg=ffmpeg, ffprobe=ffprobe)

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if ffmpeg_path and ffprobe_path:
        return FFmpegTools(ffmpeg=Path(ffmpeg_path), ffprobe=Path(ffprobe_path))

    raise FileNotFoundError(
        "未找到 ffmpeg.exe 和 ffprobe.exe。请将它们放入 tools\\ffmpeg，"
        "或设置 VIDEO_INSPECTOR_FFMPEG_DIR。"
    )
