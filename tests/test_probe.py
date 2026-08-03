import unittest
from pathlib import Path

from app.core.probe import parse_probe_data


class ProbeTests(unittest.TestCase):
    def test_parse_video_and_audio(self) -> None:
        data = {
            "format": {
                "format_long_name": "QuickTime / MOV",
                "duration": "12.5",
                "size": "1000000",
                "bit_rate": "2000000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "codec_long_name": "H.264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "bit_rate": "1800000",
                    "pix_fmt": "yuv420p",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "bit_rate": "128000",
                },
            ],
        }
        result = parse_probe_data(Path("sample.mp4"), data)
        self.assertTrue(result.has_video)
        self.assertTrue(result.has_audio)
        self.assertEqual(result.width, 1920)
        self.assertAlmostEqual(result.frame_rate, 29.970, places=2)
        self.assertEqual(result.audio_bitrate_kbps, 128)

    def test_missing_streams(self) -> None:
        result = parse_probe_data(Path("empty.bin"), {"format": {}})
        self.assertFalse(result.has_video)
        self.assertFalse(result.has_audio)


if __name__ == "__main__":
    unittest.main()
