import unittest

from app.services.youtube_service import _resume_offset


class YouTubeResumableTests(unittest.TestCase):
    def test_range_header_returns_next_byte(self):
        self.assertEqual(_resume_offset("bytes=0-8388607"), 8388608)

    def test_missing_or_invalid_range_starts_at_zero(self):
        self.assertEqual(_resume_offset(None), 0)
        self.assertEqual(_resume_offset("invalid"), 0)


if __name__ == "__main__":
    unittest.main()
