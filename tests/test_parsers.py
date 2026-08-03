import unittest

from app.core.parsers import (
    parse_black_segments,
    parse_decode_errors,
    parse_freeze_segments,
    parse_silence_segments,
    total_segment_duration,
)


class ParserTests(unittest.TestCase):
    def test_black_segments(self) -> None:
        log = "[blackdetect] black_start:1 black_end:3.5 black_duration:2.5"
        segments = parse_black_segments(log)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start, 1.0)
        self.assertEqual(segments[0].duration, 2.5)

    def test_silence_open_at_end(self) -> None:
        log = "\n".join(
            [
                "[silencedetect] silence_start: 2",
                "[silencedetect] silence_end: 4.5 | silence_duration: 2.5",
                "[silencedetect] silence_start: 8",
            ]
        )
        segments = parse_silence_segments(log, 10.0)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[1].duration, 2.0)

    def test_freeze_duration_before_end_on_same_line(self) -> None:
        log = "\n".join(
            [
                "[freezedetect] freeze_start: 3",
                "[freezedetect] freeze_duration: 4.2 freeze_end: 7.2",
            ]
        )
        segments = parse_freeze_segments(log, 8.0)
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].duration, 4.2)

    def test_overlapping_segment_duration_is_not_double_counted(self) -> None:
        segments = parse_black_segments(
            "black_start:1 black_end:5 black_duration:4\n"
            "black_start:4 black_end:7 black_duration:3"
        )
        self.assertEqual(total_segment_duration(segments, 10.0), 6.0)

    def test_decode_errors_are_deduplicated(self) -> None:
        line = "[h264] error while decoding MB 1 2"
        self.assertEqual(parse_decode_errors(f"{line}\n{line}"), [line])


if __name__ == "__main__":
    unittest.main()
