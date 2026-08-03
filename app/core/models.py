from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAILURE = "failure"
    INFO = "info"


@dataclass(slots=True)
class TimeSegment:
    start: float
    end: float
    duration: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(slots=True)
class Finding:
    code: str
    title: str
    severity: Severity
    message: str
    segments: list[TimeSegment] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        return result


@dataclass(slots=True)
class MediaMetadata:
    path: str
    filename: str
    format_name: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    overall_bitrate_kbps: int = 0
    video_codec: str = ""
    width: int = 0
    height: int = 0
    frame_rate: float = 0.0
    video_bitrate_kbps: int = 0
    pixel_format: str = ""
    audio_codec: str = ""
    audio_sample_rate: int = 0
    audio_channels: int = 0
    audio_bitrate_kbps: int = 0
    has_video: bool = False
    has_audio: bool = False

    @classmethod
    def empty(cls, path: Path) -> "MediaMetadata":
        return cls(path=str(path), filename=path.name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnalysisResult:
    metadata: MediaMetadata
    status: Severity
    score: int
    findings: list[Finding] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    analyzed_at: str = ""
    tool_version: str = ""
    raw_log: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "status": self.status.value,
            "score": self.score,
            "findings": [item.to_dict() for item in self.findings],
            "elapsed_seconds": self.elapsed_seconds,
            "analyzed_at": self.analyzed_at,
            "tool_version": self.tool_version,
        }
