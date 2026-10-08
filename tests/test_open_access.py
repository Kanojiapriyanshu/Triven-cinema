"""Open access (AUTO_LOGIN_EMAIL): no sign-in, everyone lands in the studio as one shared account."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app
from app.services import auth_service

SECRET = "open-access-test-secret-0123456789abcdef"


class OpenAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = (auth_service.AUTH_DIR, auth_service.AUTH_DB, auth_service._INITIALIZED)
        auth_service.AUTH_DIR = root / "auth"
        auth_service.AUTH_DB = auth_service.AUTH_DIR / "auth.sqlite3"
        auth_service._INITIALIZED = False
        auth_service._AUTO_USER.clear()
        self.patch = patch.multiple(
            settings, auth_enabled=True, triven_secret_key=SECRET, auto_login_email="owner@example.com",
            demo_auth_show_otp=False, smtp_host="", smtp_from="",
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        auth_service.AUTH_DIR, auth_service.AUTH_DB, auth_service._INITIALIZED = self.saved
        auth_service._AUTO_USER.clear()
        self.tmp.cleanup()

    def test_me_signs_everyone_in_without_any_cookie(self):
        with TestClient(app) as client:
            body = client.get("/api/v1/auth/me").json()
        self.assertTrue(body["authenticated"])
        self.assertTrue(body["open_access"])
        self.assertEqual(body["user"]["email"], "owner@example.com")

    def test_studio_apis_are_open_instead_of_returning_401(self):
        with TestClient(app) as client:
            self.assertNotEqual(client.get("/api/v1/elements").status_code, 401)
            self.assertNotEqual(client.get("/api/v1/chats").status_code, 401)

    def test_every_request_maps_to_the_same_workspace(self):
        with TestClient(app) as first, TestClient(app) as second:
            a = first.post("/api/v1/identity/bootstrap").json()["workspace_id"]
            b = second.post("/api/v1/identity/bootstrap").json()["workspace_id"]
            me = first.get("/api/v1/auth/me").json()["user"]["workspace_id"]
        self.assertEqual(a, b)
        self.assertEqual(a, me)

    def test_an_existing_account_keeps_its_workspace_and_data(self):
        with TestClient(app) as client:
            client.get("/api/v1/auth/me")
        original = dict(auth_service._AUTO_USER["owner@example.com"])
        auth_service._AUTO_USER.clear()  # simulate a restart
        with TestClient(app) as client:
            again = client.get("/api/v1/auth/me").json()["user"]
        self.assertEqual(again["workspace_id"], original["workspace_id"])
        self.assertEqual(again["id"], original["id"])

    def test_an_old_login_cookie_for_another_account_is_ignored(self):
        with closing(auth_service._connect()) as _:
            pass
        other = auth_service.verify_auth_token(None)
        self.assertIsNone(other)
        with TestClient(app) as client:
            client.cookies.set(auth_service.AUTH_COOKIE_NAME, "not-a-real-token")
            body = client.get("/api/v1/auth/me").json()
        self.assertEqual(body["user"]["email"], "owner@example.com")

    def test_the_email_code_routes_are_switched_off(self):
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/v1/auth/otp/request", json={"email": "a@b.co"}).status_code, 404)
            self.assertEqual(client.post("/api/v1/auth/otp/verify", json={"email": "a@b.co", "otp": "123456"}).status_code, 404)

    def test_an_invalid_configured_email_stops_the_app_with_a_clear_error(self):
        with patch.object(settings, "auto_login_email", "not-an-email"):
            with self.assertRaisesRegex(RuntimeError, "AUTO_LOGIN_EMAIL"):
                with TestClient(app):
                    pass


class SignInStillWorksWhenOpenAccessIsOffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = (auth_service.AUTH_DIR, auth_service.AUTH_DB, auth_service._INITIALIZED)
        auth_service.AUTH_DIR = root / "auth"
        auth_service.AUTH_DB = auth_service.AUTH_DIR / "auth.sqlite3"
        auth_service._INITIALIZED = False
        auth_service._AUTO_USER.clear()
        self.patch = patch.multiple(settings, auth_enabled=True, triven_secret_key=SECRET, auto_login_email="", demo_auth_show_otp=True)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        auth_service.AUTH_DIR, auth_service.AUTH_DB, auth_service._INITIALIZED = self.saved
        self.tmp.cleanup()

    def test_visitors_are_not_signed_in_and_the_studio_apis_are_gated(self):
        with TestClient(app) as client:
            me = client.get("/api/v1/auth/me").json()
            elements = client.get("/api/v1/elements")
        self.assertFalse(me["authenticated"])
        self.assertFalse(me["open_access"])
        self.assertEqual(elements.status_code, 401)

    def test_the_email_code_flow_still_works(self):
        with TestClient(app) as client:
            requested = client.post("/api/v1/auth/otp/request", json={"email": "ada@example.com"})
            self.assertEqual(requested.status_code, 200)
            code = requested.json()["demo_otp"]
            verified = client.post("/api/v1/auth/otp/verify", json={"email": "ada@example.com", "otp": code})
            self.assertEqual(verified.status_code, 200)
            self.assertTrue(verified.json()["authenticated"])
            self.assertFalse(verified.json()["open_access"])


class ProductionRulesForOpenAccessTests(unittest.TestCase):
    BASE = dict(
        _env_file=None, app_env="production", debug=False, triven_secret_key="x" * 40, auth_enabled=True,
        demo_auth_show_otp=False, smtp_host="", smtp_from="", enable_sync_render_endpoints=False, gemini_api_key="g",
    )

    def test_open_access_needs_no_email_setup_but_is_loudly_warned(self):
        errors, warnings = Settings(**{**self.BASE, "auto_login_email": "studio@triven.local"}).production_problems()
        self.assertEqual(errors, [])
        self.assertTrue(any("AUTO_LOGIN_EMAIL" in item and "GPU" in item for item in warnings))

    def test_without_open_access_or_email_delivery_startup_is_still_blocked(self):
        errors, _ = Settings(**self.BASE).production_problems()
        self.assertTrue(any("SMTP_HOST" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
