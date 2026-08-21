import json
import shutil
import tempfile
import subprocess
import threading
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None  # type: ignore[assignment]

from app.core.ffmpeg_locator import locate_ffmpeg
from app.web.jobs import JobManager, WebJob
from app.web.lifecycle import LocalLifecycle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "samples" / "normal.mp4"


class JobManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = JobManager(object(), self.root)

    def tearDown(self) -> None:
        self.manager.close()
        self.temp.cleanup()

    def test_add_creates_batch_metadata(self) -> None:
        job = self.manager.add("video.mp4", self.root / "video.mp4", 1, cleanup_source=False)

        self.assertTrue(job.batch_id)
        self.assertIn("1 个文件", job.batch_name)
        self.assertTrue(job.batch_created_at)
        self.assertEqual(job.batch_file_count, 1)

    def test_clear_finished_keeps_active_jobs(self) -> None:
        finished = WebJob(
            id="finished",
            filename="finished.mp4",
            source_path=self.root / "finished.mp4",
            size_bytes=1,
            status="completed",
            cleanup_source=False,
        )
        active = WebJob(
            id="active",
            filename="active.mp4",
            source_path=self.root / "active.mp4",
            size_bytes=1,
            status="analyzing",
            cleanup_source=False,
        )
        with self.manager._lock:
            self.manager._jobs = {finished.id: finished, active.id: active}

        self.assertEqual(self.manager.clear_finished(), 1)
        self.assertIsNone(self.manager.get(finished.id))
        self.assertIsNotNone(self.manager.get(active.id))

    def test_cancel_all_cancels_queued_and_signals_running_jobs(self) -> None:
        queued = WebJob(
            id="queued",
            filename="queued.mp4",
            source_path=self.root / "queued.mp4",
            size_bytes=1,
            status="queued",
            cleanup_source=False,
        )
        running = WebJob(
            id="running",
            filename="running.mp4",
            source_path=self.root / "running.mp4",
            size_bytes=1,
            status="analyzing",
            cleanup_source=False,
        )
        finished = WebJob(
            id="finished",
            filename="finished.mp4",
            source_path=self.root / "finished.mp4",
            size_bytes=1,
            status="completed",
            cleanup_source=False,
        )
        with self.manager._lock:
            self.manager._jobs = {
                queued.id: queued,
                running.id: running,
                finished.id: finished,
            }

        self.manager.cancel_all()

        self.assertEqual(queued.status, "cancelled")
        self.assertTrue(queued.cancel_event.is_set())
        self.assertEqual(running.status, "analyzing")
        self.assertTrue(running.cancel_event.is_set())
        self.assertEqual(finished.status, "completed")
        self.assertFalse(finished.cancel_event.is_set())


class _LifecycleManager:
    def __init__(self) -> None:
        self.cancelled = threading.Event()

    def cancel_all(self) -> None:
        self.cancelled.set()


class _LifecycleServer:
    should_exit = False


class LocalLifecycleTests(unittest.TestCase):
    def test_exits_when_browser_never_connects(self) -> None:
        lifecycle = LocalLifecycle(startup_timeout=0.05, heartbeat_timeout=1)
        manager = _LifecycleManager()
        server = _LifecycleServer()
        lifecycle.attach_server(server)
        lifecycle.start(manager)
        try:
            self.assertTrue(manager.cancelled.wait(0.5))
            self.assertTrue(server.should_exit)
        finally:
            lifecycle.stop()

    def test_exits_after_heartbeat_stops(self) -> None:
        lifecycle = LocalLifecycle(startup_timeout=1, heartbeat_timeout=0.05)
        manager = _LifecycleManager()
        server = _LifecycleServer()
        lifecycle.attach_server(server)
        lifecycle.start(manager)
        lifecycle.record_heartbeat()
        try:
            self.assertTrue(manager.cancelled.wait(0.6))
            self.assertTrue(server.should_exit)
        finally:
            lifecycle.stop()


class _ApiLifecycle:
    def __init__(self) -> None:
        self.heartbeat = threading.Event()
        self.shutdown = threading.Event()

    def start(self, manager: object) -> None:
        pass

    def stop(self) -> None:
        pass

    def record_heartbeat(self) -> None:
        self.heartbeat.set()

    def request_shutdown(self, reason: str) -> bool:
        self.shutdown.set()
        return True


@unittest.skipUnless(TestClient is not None and SAMPLE.is_file(), "web dependencies or sample missing")
class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.web.server import create_app

        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.upload_root = root / "uploads"
        static = root / "static"
        static.mkdir()
        (static / "index.html").write_text("<html><body>test</body></html>", encoding="utf-8")
        self.client_context = TestClient(
            create_app(tools=locate_ffmpeg(), upload_root=self.upload_root, static_root=static)
        )
        self.client = self.client_context.__enter__()

    def _create_hls_fixture(self) -> Path:
        hls_root = Path(self.temp.name) / "hls-source"
        hls_root.mkdir()
        tools = locate_ffmpeg()
        subprocess.run(
            [
                str(tools.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(SAMPLE),
                "-c", "copy", "-f", "hls", "-hls_time", "2",
                "-hls_playlist_type", "vod",
                "-hls_segment_filename", str(hls_root / "segment_%03d.ts"),
                str(hls_root / "index.m3u8"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return hls_root

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temp.cleanup()

    def test_health_and_frontend(self) -> None:
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")
        self.assertIn("test", self.client.get("/").text)

    def test_session_heartbeat_and_exit(self) -> None:
        from app.web.server import create_app

        lifecycle = _ApiLifecycle()
        static = Path(self.temp.name) / "lifecycle-static"
        static.mkdir()
        (static / "index.html").write_text("test", encoding="utf-8")
        with TestClient(create_app(
            tools=locate_ffmpeg(),
            upload_root=Path(self.temp.name) / "lifecycle-uploads",
            static_root=static,
            lifecycle=lifecycle,
        )) as client:
            heartbeat = client.post("/api/session/heartbeat")
            self.assertEqual(heartbeat.status_code, 200)
            self.assertTrue(lifecycle.heartbeat.is_set())

            exit_response = client.post("/api/session/exit")
            self.assertEqual(exit_response.status_code, 202)
            self.assertTrue(lifecycle.shutdown.wait(0.5))

    def test_upload_analyze_report_and_delete(self) -> None:
        with SAMPLE.open("rb") as handle:
            response = self.client.post("/api/jobs", files=[("files", (SAMPLE.name, handle, "video/mp4"))])
        self.assertEqual(response.status_code, 201)
        uploaded_job = response.json()["jobs"][0]
        job_id = uploaded_job["id"]
        self.assertTrue(uploaded_job["batch_id"])
        self.assertIn("1 个文件", uploaded_job["batch_name"])

        deadline = time.monotonic() + 30
        job = None
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["status"], "pass")
        self.assertEqual(job["progress"], 100)

        report = self.client.get(f"/api/jobs/{job_id}/report?format=json")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["score"], 100)
        clear_response = self.client.delete("/api/jobs")
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["deleted"], 1)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").status_code, 404)

    def test_rejects_unsupported_extension(self) -> None:
        response = self.client.post("/api/jobs", files=[("files", ("notes.txt", b"hello", "text/plain"))])
        self.assertEqual(response.status_code, 415)

    def test_hls_directory_analyze_preserves_source(self) -> None:
        hls_root = self._create_hls_fixture()
        playlist = hls_root / "index.m3u8"
        segments = list(hls_root.glob("*.ts"))
        response = self.client.post("/api/hls/jobs", json={"path": str(hls_root)})
        self.assertEqual(response.status_code, 201)
        job_id = response.json()["jobs"][0]["id"]

        deadline = time.monotonic() + 30
        job = None
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")
        self.assertTrue(playlist.is_file())
        self.assertTrue(segments)
        self.assertTrue(all(item.is_file() for item in segments))
        self.assertEqual(self.client.delete(f"/api/jobs/{job_id}").status_code, 204)
        self.assertTrue(playlist.is_file())
        self.assertTrue(all(item.is_file() for item in segments))

    def test_hls_rejects_missing_segment(self) -> None:
        hls_root = Path(self.temp.name) / "broken-hls"
        hls_root.mkdir()
        (hls_root / "index.m3u8").write_text(
            "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:2,\nmissing.ts\n#EXT-X-ENDLIST\n",
            encoding="utf-8",
        )
        response = self.client.post("/api/hls/jobs", json={"path": str(hls_root)})
        self.assertEqual(response.status_code, 422)

    def test_hls_folder_upload_analyzes_and_cleans_temporary_copy(self) -> None:
        hls_root = self._create_hls_fixture()
        source_files = sorted(item for item in hls_root.iterdir() if item.is_file())
        response = self.client.post(
            "/api/hls/upload",
            data={
                "relative_paths": json.dumps([item.name for item in source_files]),
                "directory_name": "1080P",
            },
            files=[
                ("files", (item.name, item.read_bytes(), "application/octet-stream"))
                for item in source_files
            ],
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["jobs"][0]["filename"], "index.m3u8")
        job_id = response.json()["jobs"][0]["id"]

        deadline = time.monotonic() + 30
        job = None
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(list(self.upload_root.iterdir()), [])
        self.assertTrue(all(item.is_file() for item in source_files))

    def test_hls_folder_upload_rejects_path_traversal(self) -> None:
        response = self.client.post(
            "/api/hls/upload",
            data={"relative_paths": json.dumps(["../index.m3u8"]), "directory_name": "HLS"},
            files=[("files", ("index.m3u8", b"#EXTM3U\n", "application/vnd.apple.mpegurl"))],
        )
        self.assertEqual(response.status_code, 400)

    def test_hls_folder_upload_discovers_resolution_groups_and_skips_master(self) -> None:
        source = self._create_hls_fixture()
        hls_root = Path(self.temp.name) / "multi-hls"
        for resolution in ("360P", "720P"):
            destination = hls_root / "ep01" / resolution
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
        (hls_root / "ep01" / "master.m3u8").write_text(
            "#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=360x640\n360P/index.m3u8\n"
            "#EXT-X-STREAM-INF:RESOLUTION=1280x720\n720P/index.m3u8\n",
            encoding="utf-8",
        )

        source_files = sorted(item for item in hls_root.rglob("*") if item.is_file())
        relative_paths = [str(item.relative_to(hls_root)).replace("\\", "/") for item in source_files]
        response = self.client.post(
            "/api/hls/upload",
            data={
                "relative_paths": json.dumps(relative_paths),
                "directory_name": "HLS",
            },
            files=[
                ("files", (item.name, item.read_bytes(), "application/octet-stream"))
                for item in source_files
            ],
        )
        self.assertEqual(response.status_code, 201)
        jobs = response.json()["jobs"]
        self.assertEqual(len(jobs), 2)
        self.assertEqual({job["filename"] for job in jobs}, {"ep01/360P/index.m3u8", "ep01/720P/index.m3u8"})
        self.assertEqual({job["group"] for job in jobs}, {"360P", "720P"})
        self.assertEqual(len({job["batch_id"] for job in jobs}), 1)
        self.assertIn("2 个文件", jobs[0]["batch_name"])

        deadline = time.monotonic() + 60
        final_jobs = {}
        while time.monotonic() < deadline:
            final_jobs = {
                job["id"]: self.client.get(f"/api/jobs/{job['id']}").json()
                for job in jobs
            }
            if all(job["status"] in {"completed", "failed"} for job in final_jobs.values()):
                break
            time.sleep(0.1)
        self.assertEqual(len(final_jobs), 2)
        self.assertTrue(all(job["status"] == "completed" for job in final_jobs.values()))
        self.assertEqual(list(self.upload_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
