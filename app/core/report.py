from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .models import AnalysisResult, Severity


STATUS_TEXT = {
    Severity.PASS: "通过",
    Severity.WARNING: "警告",
    Severity.FAILURE: "不通过",
    Severity.INFO: "信息",
}


def export_json(results: list[AnalysisResult], destination: Path) -> Path:
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "result_count": len(results),
        "results": [result.to_dict() for result in results],
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def _time(value: float) -> str:
    minutes, seconds = divmod(max(0.0, value), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def export_html(results: list[AnalysisResult], destination: Path) -> Path:
    rows: list[str] = []
    detail_sections: list[str] = []
    for index, result in enumerate(results, start=1):
        metadata = result.metadata
        rows.append(
            "<tr>"
            f"<td>{index}</td><td>{html.escape(metadata.filename)}</td>"
            f"<td><span class='status {result.status.value}'>{STATUS_TEXT[result.status]}</span></td>"
            f"<td>{result.score}</td><td>{_time(metadata.duration)}</td>"
            f"<td>{metadata.width}x{metadata.height}</td><td>{metadata.frame_rate:.2f}</td>"
            "</tr>"
        )
        finding_rows = []
        for finding in result.findings:
            segments = ""
            if finding.segments:
                segments = "<br><small>" + "；".join(
                    f"{_time(segment.start)} - {_time(segment.end)} ({segment.duration:.2f}s)"
                    for segment in finding.segments
                ) + "</small>"
            finding_rows.append(
                "<tr>"
                f"<td><span class='status {finding.severity.value}'>{STATUS_TEXT[finding.severity]}</span></td>"
                f"<td>{html.escape(finding.title)}</td>"
                f"<td>{html.escape(finding.message)}{segments}</td>"
                "</tr>"
            )
        detail_sections.append(
            f"<section><h2>{index}. {html.escape(metadata.filename)}</h2>"
            f"<p class='path'>{html.escape(metadata.path)}</p>"
            "<div class='facts'>"
            f"<span>格式 <b>{html.escape(metadata.format_name)}</b></span>"
            f"<span>视频 <b>{html.escape(metadata.video_codec or '无')}</b></span>"
            f"<span>音频 <b>{html.escape(metadata.audio_codec or '无')}</b></span>"
            f"<span>耗时 <b>{result.elapsed_seconds:.2f}s</b></span>"
            "</div>"
            "<table><thead><tr><th>级别</th><th>检测项</th><th>结果</th></tr></thead>"
            f"<tbody>{''.join(finding_rows)}</tbody></table></section>"
        )

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Inspector 检测报告</title>
<style>
body {{ margin: 0; color: #202124; background: #f5f6f7; font: 14px/1.55 "Segoe UI", "Microsoft YaHei", sans-serif; }}
header {{ background: #202124; color: white; padding: 28px max(24px, calc((100% - 1120px)/2)); }}
header h1 {{ margin: 0 0 4px; font-size: 25px; letter-spacing: 0; }}
header p {{ margin: 0; color: #d6d8da; }}
main {{ max-width: 1120px; margin: 24px auto 48px; padding: 0 24px; }}
section {{ margin: 0 0 20px; padding: 20px; background: white; border: 1px solid #dfe1e3; border-radius: 6px; }}
h2 {{ margin: 0 0 4px; font-size: 18px; letter-spacing: 0; }}
.path {{ margin: 0 0 16px; color: #676b70; overflow-wrap: anywhere; }}
.facts {{ display: flex; flex-wrap: wrap; gap: 10px 24px; margin: 0 0 16px; color: #5f6368; }}
table {{ width: 100%; border-collapse: collapse; background: white; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e4e6e8; vertical-align: top; }}
th {{ color: #555b61; background: #f1f3f4; font-weight: 600; }}
.summary {{ margin-bottom: 24px; border: 1px solid #dfe1e3; }}
.status {{ display: inline-block; min-width: 48px; text-align: center; font-weight: 600; }}
.status.pass {{ color: #14733b; }} .status.warning {{ color: #9a5b00; }}
.status.failure {{ color: #b3261e; }} .status.info {{ color: #4f555b; }}
small {{ color: #5f6368; }}
@media (max-width: 720px) {{ main {{ padding: 0 10px; }} section {{ padding: 12px; overflow-x: auto; }} }}
</style>
</head>
<body>
<header><h1>Video Inspector 检测报告</h1><p>生成时间：{html.escape(datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'))} · 文件数：{len(results)}</p></header>
<main>
<table class="summary"><thead><tr><th>#</th><th>文件</th><th>结论</th><th>评分</th><th>时长</th><th>分辨率</th><th>帧率</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
{''.join(detail_sections)}
</main>
</body>
</html>"""
    destination.write_text(document, encoding="utf-8")
    return destination
