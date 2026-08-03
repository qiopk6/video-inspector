from __future__ import annotations

import re

from .models import TimeSegment


BLACK_RE = re.compile(
    r"black_start:(?P<start>-?[\d.]+)\s+black_end:(?P<end>-?[\d.]+)\s+black_duration:(?P<duration>[\d.]+)"
)
SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<value>-?[\d.]+)")
SILENCE_END_RE = re.compile(
    r"silence_end:\s*(?P<end>-?[\d.]+)\s*\|\s*silence_duration:\s*(?P<duration>[\d.]+)"
)
FREEZE_START_RE = re.compile(r"freeze_start:\s*(?P<value>-?[\d.]+)")
FREEZE_END_RE = re.compile(r"freeze_end:\s*(?P<value>-?[\d.]+)")
FREEZE_DURATION_RE = re.compile(r"freeze_duration:\s*(?P<value>[\d.]+)")


def parse_black_segments(log: str) -> list[TimeSegment]:
    return [
        TimeSegment(
            start=max(0.0, float(match.group("start"))),
            end=max(0.0, float(match.group("end"))),
            duration=float(match.group("duration")),
        )
        for match in BLACK_RE.finditer(log)
    ]


def parse_silence_segments(log: str, media_duration: float) -> list[TimeSegment]:
    segments: list[TimeSegment] = []
    pending_start: float | None = None
    for line in log.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            pending_start = max(0.0, float(start_match.group("value")))

        end_match = SILENCE_END_RE.search(line)
        if end_match:
            end = max(0.0, float(end_match.group("end")))
            duration = float(end_match.group("duration"))
            start = pending_start if pending_start is not None else max(0.0, end - duration)
            segments.append(TimeSegment(start=start, end=end, duration=duration))
            pending_start = None

    if pending_start is not None and media_duration > pending_start:
        segments.append(
            TimeSegment(
                start=pending_start,
                end=media_duration,
                duration=media_duration - pending_start,
            )
        )
    return segments


def parse_freeze_segments(log: str, media_duration: float) -> list[TimeSegment]:
    segments: list[TimeSegment] = []
    pending_start: float | None = None
    pending_duration: float | None = None
    for line in log.splitlines():
        start_match = FREEZE_START_RE.search(line)
        if start_match:
            pending_start = max(0.0, float(start_match.group("value")))
            pending_duration = None

        duration_match = FREEZE_DURATION_RE.search(line)
        if duration_match:
            pending_duration = float(duration_match.group("value"))

        end_match = FREEZE_END_RE.search(line)
        if end_match and pending_start is not None:
            end = max(0.0, float(end_match.group("value")))
            duration = pending_duration if pending_duration is not None else max(0.0, end - pending_start)
            segments.append(TimeSegment(start=pending_start, end=end, duration=duration))
            pending_start = None
            pending_duration = None

    if pending_start is not None and media_duration > pending_start:
        duration = pending_duration if pending_duration is not None else media_duration - pending_start
        segments.append(TimeSegment(start=pending_start, end=media_duration, duration=duration))
    return segments


DECODE_ERROR_MARKERS = (
    "error while decoding",
    "invalid data found",
    "corrupt decoded frame",
    "decode_slice_header error",
    "missing picture in access unit",
    "could not find ref with poc",
    "concealing ",
)


def parse_decode_errors(log: str) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for line in log.splitlines():
        cleaned = line.strip()
        lowered = cleaned.lower()
        if cleaned and any(marker in lowered for marker in DECODE_ERROR_MARKERS) and cleaned not in seen:
            matches.append(cleaned)
            seen.add(cleaned)
    return matches


def total_segment_duration(segments: list[TimeSegment], media_duration: float) -> float:
    if not segments or media_duration <= 0:
        return sum(max(0.0, item.duration) for item in segments)
    ranges = sorted(
        (max(0.0, item.start), min(media_duration, item.end))
        for item in segments
        if item.end > item.start
    )
    if not ranges:
        return 0.0
    total = 0.0
    start, end = ranges[0]
    for next_start, next_end in ranges[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start
