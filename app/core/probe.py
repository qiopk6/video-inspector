from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from .models import MediaMetadata


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _frame_rate(value: Any) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    try:
        return float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return 0.0


def parse_probe_data(path: Path, data: dict[str, Any]) -> MediaMetadata:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    media_format = data.get("format", {})

    result = MediaMetadata.empty(path)
    result.format_name = str(media_format.get("format_long_name") or media_format.get("format_name") or "")
    result.duration = _number(media_format.get("duration"))
    result.size_bytes = _integer(media_format.get("size"))
    result.overall_bitrate_kbps = round(_number(media_format.get("bit_rate")) / 1000)

    if video:
        result.has_video = True
        result.video_codec = str(video.get("codec_long_name") or video.get("codec_name") or "")
        result.width = _integer(video.get("width"))
        result.height = _integer(video.get("height"))
        result.frame_rate = _frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
        result.video_bitrate_kbps = round(_number(video.get("bit_rate")) / 1000)
        result.pixel_format = str(video.get("pix_fmt") or "")

    if audio:
        result.has_audio = True
        result.audio_codec = str(audio.get("codec_long_name") or audio.get("codec_name") or "")
        result.audio_sample_rate = _integer(audio.get("sample_rate"))
        result.audio_channels = _integer(audio.get("channels"))
        result.audio_bitrate_kbps = round(_number(audio.get("bit_rate")) / 1000)
    return result


def probe_media(ffprobe: Path, path: Path, timeout: int = 60) -> MediaMetadata:
    command = [
        str(ffprobe), "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or "FFprobe 无法读取该文件"
        raise RuntimeError(message)
    return parse_probe_data(path, json.loads(completed.stdout))
