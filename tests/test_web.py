import json
import tempfile
import subprocess
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None  # type: ignore[assignment]

from app.core.ffmpeg_locator import locate_ffmpeg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "samples" / "normal.mp4"


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

    def test_upload_analyze_report_and_delete(self) -> None:
        with SAMPLE.open("rb") as handle:
            response = self.client.post("/api/jobs", files=[("files", (SAMPLE.name, handle, "video/mp4"))])
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
        self.assertEqual(job["result"]["status"], "pass")
        self.assertEqual(job["progress"], 100)

        report = self.client.get(f"/api/jobs/{job_id}/report?format=json")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["score"], 100)
        self.assertEqual(self.client.delete(f"/api/jobs/{job_id}").status_code, 204)
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
        self.assertEqual(response.json()["jobs"][0]["filename"], "1080P/index.m3u8")
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


if __name__ == "__main__":
    unittest.main()
