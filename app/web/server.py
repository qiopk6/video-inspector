from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import AsyncIterator
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.analyzer import VideoAnalyzer
from app.core.config import load_rules
from app.core.ffmpeg_locator import FFmpegTools, locate_ffmpeg
from app.core.report import export_html
from app.web.jobs import FINAL_STATES, JobManager, create_batch_metadata
from app.web.lifecycle import LocalLifecycle


VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".m4v",
    ".mts", ".m2ts", ".ts", ".mpg", ".mpeg", ".3gp", ".vob", ".mxf",
}
CHUNK_SIZE = 1024 * 1024
HLS_EXTENSIONS = {".m3u8", ".m3u"}


class LocalHlsRequest(BaseModel):
    path: str


@dataclass(frozen=True, slots=True)
class LocalHlsSource:
    playlist: Path
    segments: tuple[Path, ...]
    size_bytes: int


@dataclass(frozen=True, slots=True)
class HlsPlaylistTask:
    source: LocalHlsSource
    filename: str
    group: str | None


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _resolve_hls_playlist(playlist: Path) -> LocalHlsSource:
    try:
        content = playlist.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="M3U8 文件不是有效的 UTF-8 文本") from exc
    lines = [line.strip() for line in content.splitlines()]
    if not lines or lines[0] != "#EXTM3U":
        raise HTTPException(status_code=400, detail="不是有效的 M3U8 播放列表")
    if "#EXT-X-STREAM-INF" in content:
        raise HTTPException(status_code=409, detail="这是多清晰度主播放列表，请指定具体清晰度目录")
    if "#EXT-X-ENDLIST" not in content:
        raise HTTPException(status_code=409, detail="当前只支持已结束的 VOD 播放列表，暂不支持直播 M3U8")
    if "#EXT-X-KEY" in content:
        raise HTTPException(status_code=415, detail="暂不支持加密 HLS 播放列表")
    if "#EXT-X-MAP" in content:
        raise HTTPException(status_code=415, detail="暂不支持包含独立初始化分片的 HLS 播放列表")

    segment_paths: list[Path] = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        parsed = urlsplit(line)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise HTTPException(status_code=415, detail="暂不支持引用远程或带查询参数的 HLS 分片")
        segment_path = (playlist.parent / line).resolve()
        if not _is_within(segment_path, playlist.parent):
            raise HTTPException(status_code=400, detail="M3U8 分片路径不能指向播放列表目录之外")
        if not segment_path.is_file():
            raise HTTPException(status_code=422, detail=f"找不到 HLS 分片：{line}")
        segment_paths.append(segment_path)

    if not segment_paths:
        raise HTTPException(status_code=400, detail="M3U8 中没有可检测的媒体分片")
    unique_segments = tuple(dict.fromkeys(segment_paths))
    total_size = playlist.stat().st_size + sum(item.stat().st_size for item in unique_segments)
    return LocalHlsSource(playlist=playlist, segments=unique_segments, size_bytes=total_size)


def _resolve_local_hls(path_text: str) -> LocalHlsSource:
    if not path_text.strip():
        raise HTTPException(status_code=400, detail="请输入本地 HLS 目录或 index.m3u8 路径")

    candidate = Path(path_text.strip()).expanduser()
    if not candidate.is_absolute():
        raise HTTPException(status_code=400, detail="HLS 路径必须是本机绝对路径")
    try:
        candidate = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="找不到指定的 HLS 路径") from exc

    if candidate.is_file() and candidate.suffix.lower() in HLS_EXTENSIONS:
        return _resolve_hls_playlist(candidate)
    if not candidate.is_dir():
        raise HTTPException(status_code=400, detail="路径必须是 HLS 目录或 .m3u8 文件")

    playlists = [
        item for item in candidate.rglob("*")
        if item.is_file() and item.suffix.lower() in HLS_EXTENSIONS
        and "#EXT-X-STREAM-INF" not in item.read_text(encoding="utf-8-sig")
    ]
    if len(playlists) != 1:
        raise HTTPException(status_code=409, detail="目录中发现多个媒体播放列表，请使用 HLS 文件夹上传或直接指定一个 m3u8 文件")
    return _resolve_hls_playlist(playlists[0])


def _discover_hls_tasks(root: Path) -> list[HlsPlaylistTask]:
    candidates = sorted(
        item for item in root.rglob("*")
        if item.is_file() and item.suffix.lower() in HLS_EXTENSIONS
    )
    tasks: list[HlsPlaylistTask] = []
    for playlist in candidates:
        content = playlist.read_text(encoding="utf-8-sig")
        if "#EXT-X-STREAM-INF" in content:
            continue
        source = _resolve_hls_playlist(playlist)
        relative = playlist.relative_to(root)
        parts = relative.parts
        resolution = playlist.parent.name
        group = resolution.upper() if resolution.lower().endswith("p") else None
        filename = "/".join(parts)
        tasks.append(HlsPlaylistTask(source=source, filename=filename, group=group))

    if not tasks:
        raise HTTPException(status_code=400, detail="HLS 文件夹中没有可检测的媒体播放列表")

    def sort_key(task: HlsPlaylistTask) -> tuple[int, str, str]:
        resolution = task.group or ""
        digits = "".join(character for character in resolution if character.isdigit())
        return (int(digits) if digits else 99999, task.filename.lower(), task.filename)

    return sorted(tasks, key=sort_key)


def _static_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "web_static"
    return Path(__file__).resolve().parents[2] / "web" / "dist"


def _safe_filename(filename: str) -> str:
    leaf = Path(filename).name.strip()
    cleaned = re.sub(r"[^\w.()\[\] -]", "_", leaf, flags=re.UNICODE)
    return cleaned[:180] or "video"


def _safe_hls_relative_path(path_text: str) -> Path:
    normalized = path_text.strip().replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or ":" in candidate.parts[0]
    ):
        raise HTTPException(status_code=400, detail=f"HLS 文件路径无效：{path_text}")
    return Path(*candidate.parts)


def create_app(
    tools: FFmpegTools | None = None,
    upload_root: Path | None = None,
    static_root: Path | None = None,
    lifecycle: LocalLifecycle | None = None,
) -> FastAPI:
    resolved_tools = tools or locate_ffmpeg()
    root = upload_root or Path(tempfile.gettempdir()) / "VideoInspectorWeb" / uuid.uuid4().hex
    manager = JobManager(VideoAnalyzer(resolved_tools, load_rules()), root)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if lifecycle is not None:
            lifecycle.start(manager)
        try:
            yield
        finally:
            if lifecycle is not None:
                lifecycle.stop()
            manager.close()

    app = FastAPI(title="Video Inspector", version="0.2.0", lifespan=lifespan)
    app.state.jobs = manager
    app.state.lifecycle = lifecycle

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.2.0"}

    @app.post("/api/session/heartbeat")
    def session_heartbeat() -> dict[str, str]:
        if lifecycle is not None:
            lifecycle.record_heartbeat()
        return {"status": "ok"}

    @app.post("/api/session/exit", status_code=202)
    def exit_application() -> dict[str, str]:
        if lifecycle is None:
            raise HTTPException(status_code=503, detail="本地程序未启用生命周期控制")
        timer = threading.Timer(0.1, lifecycle.request_shutdown, args=("user requested exit",))
        timer.daemon = True
        timer.start()
        return {"status": "shutting_down"}

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, object]:
        jobs = manager.list()
        return {"jobs": [job.to_public() for job in jobs], "count": len(jobs)}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job.to_public()

    @app.get("/api/jobs/{job_id}/log")
    def get_log(job_id: str) -> dict[str, str]:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"log": job.result.raw_log if job.result else ""}

    @app.post("/api/jobs", status_code=201)
    async def create_jobs(files: list[UploadFile] = File(...)) -> dict[str, object]:
        if not files:
            raise HTTPException(status_code=400, detail="请选择视频文件")
        for upload in files:
            if Path(upload.filename or "").suffix.lower() not in VIDEO_EXTENSIONS:
                raise HTTPException(status_code=415, detail=f"不支持的文件类型：{upload.filename}")

        batch_id, batch_name, batch_created_at, batch_file_count = create_batch_metadata(len(files))
        created = []
        for upload in files:
            filename = _safe_filename(upload.filename or "video")
            directory = root / uuid.uuid4().hex
            directory.mkdir(parents=True, exist_ok=False)
            destination = directory / filename
            size = 0
            try:
                with destination.open("wb") as handle:
                    while chunk := await upload.read(CHUNK_SIZE):
                        handle.write(chunk)
                        size += len(chunk)
            except Exception:
                destination.unlink(missing_ok=True)
                directory.rmdir()
                raise
            finally:
                await upload.close()
            created.append(manager.add(
                filename,
                destination,
                size,
                batch_id=batch_id,
                batch_name=batch_name,
                batch_created_at=batch_created_at,
                batch_file_count=batch_file_count,
            ).to_public())
        return {"jobs": created}

    @app.post("/api/hls/upload", status_code=201)
    async def upload_hls_directory(
        files: list[UploadFile] = File(...),
        relative_paths: str = Form(...),
        directory_name: str = Form("HLS"),
    ) -> dict[str, object]:
        if not files:
            raise HTTPException(status_code=400, detail="请选择 HLS 文件夹")
        try:
            raw_paths = json.loads(relative_paths)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="HLS 文件清单格式无效") from exc
        if not isinstance(raw_paths, list) or len(raw_paths) != len(files):
            raise HTTPException(status_code=400, detail="HLS 文件清单与上传文件不匹配")
        if not all(isinstance(item, str) for item in raw_paths):
            raise HTTPException(status_code=400, detail="HLS 文件清单包含无效路径")

        safe_paths = [_safe_hls_relative_path(item) for item in raw_paths]
        if len({str(item).lower() for item in safe_paths}) != len(safe_paths):
            raise HTTPException(status_code=409, detail="HLS 文件夹中存在重名文件")

        directory = root / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        try:
            for upload, relative_path in zip(files, safe_paths, strict=True):
                destination = directory / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with destination.open("wb") as handle:
                        while chunk := await upload.read(CHUNK_SIZE):
                            handle.write(chunk)
                finally:
                    await upload.close()

            tasks = _discover_hls_tasks(directory)
            batch_id, batch_name, batch_created_at, batch_file_count = create_batch_metadata(len(tasks))
            jobs = manager.add_many([
                (task.filename, task.source.playlist, task.source.size_bytes, True, directory, task.group)
                for task in tasks
            ], batch_id, batch_name, batch_created_at, batch_file_count)
            created = [job.to_public() for job in jobs]
            return {"jobs": created}
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    @app.post("/api/hls/jobs", status_code=201)
    def create_hls_job(payload: LocalHlsRequest) -> dict[str, object]:
        source = _resolve_local_hls(payload.path)
        parent_names = [source.playlist.parent.parent.name, source.playlist.parent.name]
        display_name = "/".join([name for name in parent_names if name] + [source.playlist.name])
        job = manager.add(
            display_name,
            source.playlist,
            source.size_bytes,
            cleanup_source=False,
        )
        return {"jobs": [job.to_public()]}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, object]:
        job = manager.cancel(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job.to_public()

    @app.delete("/api/jobs")
    def clear_finished_jobs() -> dict[str, int]:
        deleted = manager.clear_finished()
        return {"deleted": deleted, "remaining": len(manager.list())}

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> None:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        if job.status not in FINAL_STATES:
            raise HTTPException(status_code=409, detail="请先取消正在运行的任务")
        if not manager.delete(job_id):
            raise HTTPException(status_code=409, detail="任务暂时无法删除")

    @app.get("/api/jobs/{job_id}/report")
    def download_report(
        job_id: str,
        format_name: str = Query(alias="format", pattern="^(json|html)$"),
    ):
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        if not job.result:
            raise HTTPException(status_code=409, detail="检测尚未完成")
        stem = Path(job.filename).stem
        if format_name == "json":
            encoded_name = quote(f"{stem}-report.json")
            return JSONResponse(
                content=job.result.to_dict(),
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="{job.id[:8]}-report.json"; '
                        f"filename*=UTF-8''{encoded_name}"
                    )
                },
            )
        report_dir = root / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{job.id}.html"
        export_html([job.result], report_path)
        return FileResponse(report_path, filename=f"{stem}-report.html", media_type="text/html")

    resolved_static = static_root or _static_root()
    if resolved_static.is_dir():
        assets = resolved_static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", response_class=HTMLResponse)
        def spa(path: str):
            candidate = resolved_static / path
            if path and candidate.is_file() and resolved_static in candidate.resolve().parents:
                return FileResponse(candidate)
            index = resolved_static / "index.html"
            return HTMLResponse(index.read_text(encoding="utf-8"))
    else:
        @app.get("/", response_class=HTMLResponse)
        def missing_frontend() -> str:
            return "<h1>Frontend not built</h1><p>Run the Vite build in web/.</p>"
    return app
