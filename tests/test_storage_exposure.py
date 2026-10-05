import unittest

from app.main import app


class StorageExposureTests(unittest.TestCase):
    def test_generated_media_uses_protected_route_not_static_storage_mount(self):
        paths = [getattr(route, "path", None) for route in app.routes]
        self.assertIn("/media/generated/{filename}", paths)
        self.assertNotIn("/media/generated", paths)
        self.assertNotIn("/media", paths)


if __name__ == "__main__":
    unittest.main()
