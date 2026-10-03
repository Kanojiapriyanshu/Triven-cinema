import unittest

from app.main import app


class StorageExposureTests(unittest.TestCase):
    def test_only_generated_media_is_mounted(self):
        mount_paths = [getattr(route, "path", None) for route in app.routes]
        self.assertIn("/media/generated", mount_paths)
        self.assertNotIn("/media", mount_paths)


if __name__ == "__main__":
    unittest.main()
