from __future__ import annotations

import queue
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.analyzer import AnalysisCancelled, VideoAnalyzer
from app.core.models import AnalysisResult


FINAL_STATES = {"completed", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def create_batch_metadata(file_count: int) -> tuple[str, str, str, int]:
    created_at = _now()
    display_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    return uuid.uuid4().hex, f"{display_time} · {file_count} 个文件", created_at, file_count


@dataclass(slots=True)
class WebJob:
    id: str
    filename: str
    source_path: Path
    size_bytes: int
    status: str = "queued"
    progress: int = 0
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result: AnalysisResult | None = None
    group: str | None = None
    batch_id: str = ""
    batch_name: str = ""
    batch_created_at: str = ""
    batch_file_count: int = 1
    cleanup_source: bool = field(default=True, repr=False)
    cleanup_root: Path | None = field(default=None, repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_public(self, include_log: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "group": self.group,
            "batch_id": self.batch_id,
            "batch_name": self.batch_name,
            "batch_created_at": self.batch_created_at,
            "batch_file_count": self.batch_file_count,
            "result": self.result.to_dict() if self.result else None,
        }
        if include_log:
            payload["raw_log"] = self.result.raw_log if self.result else ""
        return payload


class JobManager:
    def __init__(self, analyzer: VideoAnalyzer, upload_root: Path) -> None:
        self.analyzer = analyzer
        self.upload_root = upload_root
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, WebJob] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="video-analysis-worker", daemon=True)
        self._closed = False
        self._worker.start()

    def add(
        self,
        filename: str,
        source_path: Path,
        size_bytes: int,
        cleanup_source: bool = True,
        cleanup_root: Path | None = None,
        group: str | None = None,
        batch_id: str | None = None,
        batch_name: str | None = None,
        batch_created_at: str | None = None,
        batch_file_count: int | None = None,
    ) -> WebJob:
        return self.add_many([
            (filename, source_path, size_bytes, cleanup_source, cleanup_root, group),
        ], batch_id, batch_name, batch_created_at, batch_file_count)[0]

    def add_many(
        self,
        entries: list[tuple[str, Path, int, bool, Path | None, str | None]],
        batch_id: str | None = None,
        batch_name: str | None = None,
        batch_created_at: str | None = None,
        batch_file_count: int | None = None,
    ) -> list[WebJob]:
        if not entries:
            return []
        if batch_id is None or batch_name is None or batch_created_at is None:
            batch_id, batch_name, batch_created_at, batch_file_count = create_batch_metadata(len(entries))
        batch_file_count = batch_file_count if batch_file_count is not None else len(entries)
        jobs = [
            WebJob(
                id=uuid.uuid4().hex,
                filename=filename,
                source_path=source_path,
                size_bytes=size_bytes,
                cleanup_source=cleanup_source,
                cleanup_root=cleanup_root,
                group=group,
                batch_id=batch_id,
                batch_name=batch_name,
                batch_created_at=batch_created_at,
                batch_file_count=batch_file_count,
            )
            for filename, source_path, size_bytes, cleanup_source, cleanup_root, group in entries
        ]
        with self._lock:
            for job in jobs:
                self._jobs[job.id] = job
        for job in jobs:
            self._queue.put(job.id)
        return jobs

    def list(self) -> list[WebJob]:
        with self._lock:
            return list(reversed(self._jobs.values()))

    def get(self, job_id: str) -> WebJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> WebJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in FINAL_STATES:
                return job
            job.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.completed_at = _now()
                self._remove_source(job)
            return job

    def cancel_all(self) -> None:
        with self._lock:
            job_ids = [
                job.id for job in self._jobs.values()
                if job.status not in FINAL_STATES
            ]
        for job_id in job_ids:
            self.cancel(job_id)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in FINAL_STATES:
                return False
            self._remove_source(job)
            del self._jobs[job_id]
            return True

    def clear_finished(self) -> int:
        with self._lock:
            job_ids = [job.id for job in self._jobs.values() if job.status in FINAL_STATES]
        return sum(1 for job_id in job_ids if self.delete(job_id))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel_all()
        self._queue.put(None)
        self._worker.join(timeout=10)
        shutil.rmtree(self.upload_root, ignore_errors=True)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            with self._lock:
                job = self._jobs.get(job_id)
                if not job or job.status != "queued":
                    continue
                job.status = "analyzing"
                job.started_at = _now()
                job.progress = max(job.progress, 1)
            try:
                result = self.analyzer.analyze(
                    job.source_path,
                    progress=lambda value, current=job: self._set_progress(current, value),
                    cancel_event=job.cancel_event,
                )
                result.metadata.path = job.filename
                with self._lock:
                    job.result = result
                    job.progress = 100
                    job.status = "completed"
                    job.completed_at = _now()
            except AnalysisCancelled:
                with self._lock:
                    job.status = "cancelled"
                    job.completed_at = _now()
            except Exception as exc:
                with self._lock:
                    job.status = "failed"
                    job.error = str(exc)
                    job.completed_at = _now()
            finally:
                self._remove_source(job)

    def _set_progress(self, job: WebJob, value: float) -> None:
        with self._lock:
            if job.status == "analyzing":
                job.progress = max(job.progress, min(99, round(value * 100)))

    def _remove_source(self, job: WebJob) -> None:
        if not job.cleanup_source:
            return
        if job.cleanup_root is not None:
            with self._lock:
                group_jobs = [
                    item for item in self._jobs.values()
                    if item.cleanup_root == job.cleanup_root
                ]
                all_finished = group_jobs and all(item.status in FINAL_STATES for item in group_jobs)
            if all_finished:
                shutil.rmtree(job.cleanup_root, ignore_errors=True)
            return
        try:
            job.source_path.unlink(missing_ok=True)
            job.source_path.parent.rmdir()
        except OSError:
            pass
