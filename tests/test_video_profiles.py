import unittest

from app.services.video_profiles import source_render_dimensions
from app.services.video_combiner import delivery_dimensions


class VideoProfileTests(unittest.TestCase):
    def test_source_profiles(self):
        self.assertEqual(source_render_dimensions("16:9"), (1024, 576))
        self.assertEqual(source_render_dimensions("9:16"), (576, 1024))
        self.assertEqual(source_render_dimensions("1:1"), (512, 512))

    def test_delivery_profiles(self):
        self.assertEqual(delivery_dimensions("16:9"), (1920, 1080))
        self.assertEqual(delivery_dimensions("9:16"), (1080, 1920))
        self.assertEqual(delivery_dimensions("1:1"), (1080, 1080))


if __name__ == "__main__":
    unittest.main()
