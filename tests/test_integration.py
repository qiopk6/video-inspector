import unittest
from pathlib import Path

from app.core.analyzer import VideoAnalyzer
from app.core.config import load_rules
from app.core.ffmpeg_locator import locate_ffmpeg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = PROJECT_ROOT / "samples"


@unittest.skipUnless((SAMPLE_DIR / "normal.mp4").is_file(), "integration samples not generated")
class FFmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = VideoAnalyzer(locate_ffmpeg(), load_rules())

    def test_normal_video_has_no_primary_detection(self) -> None:
        result = self.analyzer.analyze(SAMPLE_DIR / "normal.mp4")
        codes = {finding.code for finding in result.findings}
        self.assertIn("BLACK_SCREEN_OK", codes)
        self.assertIn("SILENCE_OK", codes)
        self.assertIn("FREEZE_FRAME_OK", codes)
        self.assertIn("DECODE_OK", codes)

    def test_black_and_silence_video(self) -> None:
        result = self.analyzer.analyze(SAMPLE_DIR / "black_and_silence.mp4")
        codes = {finding.code for finding in result.findings}
        self.assertIn("BLACK_SCREEN", codes)
        self.assertIn("SILENCE", codes)

    def test_freeze_and_low_quality_video(self) -> None:
        result = self.analyzer.analyze(SAMPLE_DIR / "freeze_low_quality.mp4")
        codes = {finding.code for finding in result.findings}
        self.assertIn("FREEZE_FRAME", codes)
        self.assertIn("LOW_RESOLUTION", codes)
        self.assertIn("LOW_FRAME_RATE", codes)


if __name__ == "__main__":
    unittest.main()
