import tempfile
import unittest
from pathlib import Path

from app.core.models import AnalysisResult, Finding, MediaMetadata, Severity
from app.core.report import export_html, export_json


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        metadata = MediaMetadata.empty(Path("demo<1>.mp4"))
        metadata.duration = 5.0
        metadata.has_video = True
        metadata.width = 1280
        metadata.height = 720
        self.result = AnalysisResult(
            metadata=metadata,
            status=Severity.PASS,
            score=100,
            findings=[Finding("OK", "完整性", Severity.PASS, "正常")],
        )

    def test_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.json"
            export_json([self.result], output)
            content = output.read_text(encoding="utf-8")
            self.assertIn('"score": 100', content)
            self.assertIn('"status": "pass"', content)

    def test_html_report_escapes_filename(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.html"
            export_html([self.result], output)
            content = output.read_text(encoding="utf-8")
            self.assertIn("demo&lt;1&gt;.mp4", content)
            self.assertNotIn("demo<1>.mp4", content)


if __name__ == "__main__":
    unittest.main()
