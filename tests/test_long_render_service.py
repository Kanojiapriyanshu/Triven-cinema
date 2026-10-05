import unittest

from app.services.long_render_service import split_duration


class LongRenderServiceTests(unittest.TestCase):
    def test_thirty_seconds_uses_three_ten_second_chunks(self):
        self.assertEqual(split_duration(30, 10), [10.0, 10.0, 10.0])

    def test_fifteen_seconds_uses_ten_plus_five(self):
        self.assertEqual(split_duration(15, 10), [10.0, 5.0])

    def test_short_clip_stays_single_chunk(self):
        self.assertEqual(split_duration(5, 10), [5.0])


if __name__ == "__main__":
    unittest.main()
