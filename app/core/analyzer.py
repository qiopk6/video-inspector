from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .ffmpeg_locator import FFmpegTools
from .models import AnalysisResult, Finding, MediaMetadata, Severity, TimeSegment
from .parsers import (
    parse_black_segments,
    parse_decode_errors,
    parse_freeze_segments,
    parse_silence_segments,
    total_segment_duration,
)
from .probe import CREATE_NO_WINDOW, probe_media


ProgressCallback = Callable[[float], None]


class AnalysisCancelled(RuntimeError):
    pass


def _severity_for_ratio(ratio: float, warning: float, failure: float) -> Severity:
    if ratio >= failure:
        return Severity.FAILURE
    if ratio >= warning:
        return Severity.WARNING
    return Severity.PASS


def _format_ratio(value: float) -> str:
    return f"{value * 100:.1f}%"


class VideoAnalyzer:
    def __init__(self, tools: FFmpegTools, rules: dict[str, Any]) -> None:
        self.tools = tools
        self.rules = rules

    def analyze(
        self,
        path: Path,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AnalysisResult:
        started = time.monotonic()
        metadata = probe_media(self.tools.ffprobe, path)
        if progress:
            progress(0.03)

        findings: list[Finding] = []
        if not metadata.has_video:
            findings.append(
                Finding("NO_VIDEO", "无视频轨", Severity.FAILURE, "文件中未发现可检测的视频轨。")
            )
            return self._finish(metadata, findings, started, "")

        log, return_code = self._run_detection(metadata, progress, cancel_event)
        findings.extend(self._quality_findings(metadata))
        findings.extend(self._black_findings(log, metadata.duration))
        if metadata.has_audio:
            findings.extend(self._silence_findings(log, metadata.duration))
        else:
            findings.append(
                Finding("NO_AUDIO", "无音频轨", Severity.INFO, "文件中未发现音频轨，已跳过静音检测。")
            )
        findings.extend(self._freeze_findings(log, metadata.duration))

        decode_errors = parse_decode_errors(log)
        if return_code != 0 or decode_errors:
            message = f"发现 {len(decode_errors)} 类解码异常。" if decode_errors else "FFmpeg 解码检测异常退出。"
            findings.append(
                Finding(
                    "DECODE_ERROR",
                    "解码异常",
                    Severity.FAILURE,
                    message,
                    details={"return_code": return_code, "samples": decode_errors[:20]},
                )
            )
        else:
            findings.append(Finding("DECODE_OK", "解码完整性", Severity.PASS, "未发现解码错误。"))

        return self._finish(metadata, findings, started, log)

    def _run_detection(
        self,
        metadata: MediaMetadata,
        progress: ProgressCallback | None,
        cancel_event: threading.Event | None,
    ) -> tuple[str, int]:
        black = self.rules["black"]
        freeze = self.rules["freeze"]
        command = [str(self.tools.ffmpeg), "-hide_banner", "-nostdin", "-v", "info", "-i", metadata.path]
        command.extend(
            [
                "-map", "0:v:0",
                "-vf",
                (
                    f"blackdetect=d={black['minimum_duration_seconds']}:pix_th={black['pixel_threshold']},"
                    f"freezedetect=n={freeze['noise_threshold_db']}dB:d={freeze['minimum_duration_seconds']}"
                ),
            ]
        )
        if metadata.has_audio:
            silence = self.rules["silence"]
            command.extend(
                [
                    "-map", "0:a:0",
                    "-af",
                    f"silencedetect=noise={silence['noise_threshold_db']}dB:d={silence['minimum_duration_seconds']}",
                ]
            )
        command.extend(["-f", "null", "-", "-progress", "pipe:1", "-nostats"])

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        stderr_lines: list[str] = []

        def read_stderr() -> None:
            assert process.stderr is not None
            stderr_lines.extend(process.stderr.readlines())

        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        assert process.stdout is not None
        try:
            for line in process.stdout:
                if cancel_event and cancel_event.is_set():
                    process.terminate()
                    raise AnalysisCancelled("检测已取消")
                key, separator, value = line.strip().partition("=")
                if separator and key in {"out_time_us", "out_time_ms"} and metadata.duration > 0:
                    try:
                        # Current FFmpeg reports both values in microseconds despite the legacy key name.
                        fraction = min(1.0, max(0.0, float(value) / 1_000_000 / metadata.duration))
                        if progress:
                            progress(0.03 + fraction * 0.97)
                    except ValueError:
                        pass
            return_code = process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            stderr_thread.join(timeout=5)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        if progress:
            progress(1.0)
        return "".join(stderr_lines), return_code

    def _quality_findings(self, metadata: MediaMetadata) -> list[Finding]:
        quality = self.rules["quality"]
        findings: list[Finding] = []
        if metadata.width < quality["minimum_width"] or metadata.height < quality["minimum_height"]:
            findings.append(
                Finding(
                    "LOW_RESOLUTION", "分辨率偏低", Severity.WARNING,
                    f"当前 {metadata.width}x{metadata.height}，规则要求不低于 "
                    f"{quality['minimum_width']}x{quality['minimum_height']}。",
                )
            )
        else:
            findings.append(
                Finding("RESOLUTION_OK", "分辨率", Severity.PASS, f"{metadata.width}x{metadata.height}")
            )

        if metadata.frame_rate and metadata.frame_rate < quality["minimum_frame_rate"]:
            findings.append(
                Finding(
                    "LOW_FRAME_RATE", "帧率偏低", Severity.WARNING,
                    f"当前 {metadata.frame_rate:.2f} fps，低于 {quality['minimum_frame_rate']:.2f} fps。",
                )
            )
        elif metadata.frame_rate:
            findings.append(Finding("FRAME_RATE_OK", "帧率", Severity.PASS, f"{metadata.frame_rate:.2f} fps"))

        if metadata.video_bitrate_kbps and metadata.video_bitrate_kbps < quality["minimum_video_bitrate_kbps"]:
            findings.append(
                Finding(
                    "LOW_VIDEO_BITRATE", "视频码率偏低", Severity.WARNING,
                    f"当前 {metadata.video_bitrate_kbps} kbps，低于 {quality['minimum_video_bitrate_kbps']} kbps。",
                )
            )
        return findings

    def _black_findings(self, log: str, duration: float) -> list[Finding]:
        segments = parse_black_segments(log)
        total = total_segment_duration(segments, duration)
        ratio = total / duration if duration > 0 else 0.0
        rule = self.rules["black"]
        severity = _severity_for_ratio(ratio, rule["warning_total_ratio"], rule["failure_total_ratio"])
        if segments:
            return [
                Finding(
                    "BLACK_SCREEN", "黑屏检测", severity,
                    f"发现 {len(segments)} 段黑屏，共 {total:.2f} 秒，占 {_format_ratio(ratio)}。",
                    segments=segments, details={"total_seconds": total, "ratio": ratio},
                )
            ]
        return [Finding("BLACK_SCREEN_OK", "黑屏检测", Severity.PASS, "未发现达到阈值的黑屏片段。")]

    def _silence_findings(self, log: str, duration: float) -> list[Finding]:
        segments = parse_silence_segments(log, duration)
        total = total_segment_duration(segments, duration)
        ratio = total / duration if duration > 0 else 0.0
        rule = self.rules["silence"]
        severity = _severity_for_ratio(ratio, rule["warning_total_ratio"], rule["failure_total_ratio"])
        if segments:
            return [
                Finding(
                    "SILENCE", "静音检测", severity,
                    f"发现 {len(segments)} 段静音，共 {total:.2f} 秒，占 {_format_ratio(ratio)}。",
                    segments=segments, details={"total_seconds": total, "ratio": ratio},
                )
            ]
        return [Finding("SILENCE_OK", "静音检测", Severity.PASS, "未发现达到阈值的静音片段。")]

    def _freeze_findings(self, log: str, duration: float) -> list[Finding]:
        segments = parse_freeze_segments(log, duration)
        total = total_segment_duration(segments, duration)
        ratio = total / duration if duration > 0 else 0.0
        rule = self.rules["freeze"]
        severity = _severity_for_ratio(ratio, rule["warning_total_ratio"], rule["failure_total_ratio"])
        if segments:
            return [
                Finding(
                    "FREEZE_FRAME", "冻结画面", severity,
                    f"发现 {len(segments)} 段冻结画面，共 {total:.2f} 秒，占 {_format_ratio(ratio)}。",
                    segments=segments, details={"total_seconds": total, "ratio": ratio},
                )
            ]
        return [Finding("FREEZE_FRAME_OK", "冻结画面", Severity.PASS, "未发现达到阈值的冻结片段。")]

    def _finish(
        self,
        metadata: MediaMetadata,
        findings: list[Finding],
        started: float,
        raw_log: str,
    ) -> AnalysisResult:
        deductions = {
            "NO_VIDEO": 100,
            "LOW_RESOLUTION": 15,
            "LOW_FRAME_RATE": 10,
            "LOW_VIDEO_BITRATE": 10,
            "BLACK_SCREEN": 15,
            "SILENCE": 10,
            "FREEZE_FRAME": 10,
            "DECODE_ERROR": 40,
        }
        score = 100
        for finding in findings:
            deduction = deductions.get(finding.code, 0)
            if finding.severity == Severity.FAILURE and finding.code in {"BLACK_SCREEN", "SILENCE", "FREEZE_FRAME"}:
                deduction += 15
            score -= deduction
        score = max(0, score)

        quality = self.rules["quality"]
        if any(item.severity == Severity.FAILURE for item in findings) or score < quality["failure_score"]:
            status = Severity.FAILURE
        elif any(item.severity == Severity.WARNING for item in findings) or score < quality["warning_score"]:
            status = Severity.WARNING
        else:
            status = Severity.PASS
        return AnalysisResult(
            metadata=metadata,
            status=status,
            score=score,
            findings=findings,
            elapsed_seconds=time.monotonic() - started,
            analyzed_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            tool_version="0.2.0",
            raw_log=raw_log,
        )
