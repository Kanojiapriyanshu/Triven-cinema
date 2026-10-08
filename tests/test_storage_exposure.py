import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.identity_service import sign_workspace_id


class StorageExposureTests(unittest.TestCase):
    def test_generated_media_uses_protected_route_not_static_storage_mount(self):
        paths = [getattr(route, "path", None) for route in app.routes]
        self.assertIn("/media/generated/{filename}", paths)
        self.assertNotIn("/media/generated", paths)
        self.assertNotIn("/media", paths)

    def test_production_media_rejects_workspace_cookie_without_a_login(self):
        with tempfile.TemporaryDirectory() as folder:
            asset = Path(folder) / "private.png"
            asset.write_bytes(b"private")
            client = TestClient(app)
            try:
                with patch.multiple(settings, app_env="production", auth_enabled=True, auto_login_email="", triven_secret_key="x" * 40), \
                        patch("app.main.resolve_generated_asset", return_value=asset), \
                        patch("app.main.workspace_owns_generated_file", return_value=True) as ownership:
                    client.cookies.set("triven_workspace", sign_workspace_id("a" * 32))
                    response = client.get("/media/generated/private.png")
                self.assertEqual(response.status_code, 404)
                ownership.assert_not_called()
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            finally:
                client.close()

    def test_authenticated_owner_can_read_media_but_it_is_never_publicly_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            asset = Path(folder) / "private.png"
            asset.write_bytes(b"private")
            client = TestClient(app)
            try:
                with patch.multiple(settings, app_env="production", auth_enabled=True, auto_login_email=""), \
                        patch("app.main.resolve_generated_asset", return_value=asset), \
                        patch("app.services.auth_service.auth_user_from_request", return_value={"workspace_id": "a" * 32}), \
                        patch("app.main.workspace_owns_generated_file", return_value=True) as ownership:
                    response = client.get("/media/generated/private.png")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"private")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                ownership.assert_called_once_with("a" * 32, "private.png")
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()
