"""Production safety: fail fast on unsafe settings, and real sign-in email delivery."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app
from app.services import auth_service, email_service

SAFE = dict(
    _env_file=None,
    app_env="production",
    debug=False,
    triven_secret_key="x" * 40,
    auth_enabled=True,
    demo_auth_show_otp=False,
    smtp_host="smtp.example.test",
    smtp_from="no-reply@example.test",
    enable_sync_render_endpoints=False,
    gemini_api_key="g",
)


def make(**overrides) -> Settings:
    return Settings(**{**SAFE, **overrides})


class ProductionProblemsTests(unittest.TestCase):
    def test_a_correct_production_setup_has_no_blockers_or_warnings(self):
        errors, warnings = make().production_problems()
        self.assertEqual((errors, warnings), ([], []))

    def test_missing_signing_secret_blocks_startup(self):
        errors, _ = make(triven_secret_key="").production_problems()
        self.assertTrue(any("TRIVEN_SECRET_KEY" in item for item in errors))

    def test_debug_blocks_startup(self):
        errors, _ = make(debug=True).production_problems()
        self.assertTrue(any("DEBUG" in item for item in errors))

    def test_login_without_any_way_to_deliver_codes_blocks_startup(self):
        errors, _ = make(smtp_host="", smtp_from="", demo_auth_show_otp=False).production_problems()
        self.assertTrue(any("SMTP_HOST" in item for item in errors))

    def test_demo_mode_is_allowed_but_loudly_warned(self):
        errors, warnings = make(smtp_host="", smtp_from="", demo_auth_show_otp=True).production_problems()
        self.assertEqual(errors, [])
        self.assertTrue(any("DEMO_AUTH_SHOW_OTP" in item for item in warnings))

    def test_other_risky_settings_are_warned(self):
        _, warnings = make(enable_sync_render_endpoints=True, cors_origins="*", triven_secret_key="short-secret", gemini_api_key="").production_problems()
        joined = " ".join(warnings)
        for needle in ("ENABLE_SYNC_RENDER_ENDPOINTS", "CORS_ORIGINS", "TRIVEN_SECRET_KEY is short", "GEMINI_API_KEY"):
            self.assertIn(needle, joined)

    def test_billing_needs_its_stripe_secrets(self):
        errors, _ = make(billing_enabled=True).production_problems()
        self.assertTrue(any("STRIPE" in item for item in errors))

    def test_the_app_refuses_to_start_in_production_with_a_blocker(self):
        with patch.object(settings, "app_env", "production"), patch.object(settings, "triven_secret_key", ""):
            with self.assertRaisesRegex(RuntimeError, "refusing to start"):
                with TestClient(app):
                    pass


class EmailTests(unittest.TestCase):
    def _smtp(self, security):
        return patch.multiple(
            settings, smtp_host="smtp.example.test", smtp_from="no-reply@example.test", smtp_security=security,
            smtp_username="user", smtp_password="pw", smtp_port=587,
        )

    def test_message_contains_the_code_and_expiry(self):
        with self._smtp("starttls"):
            message = email_service.build_otp_message("ada@example.com", "123456", 600)
        self.assertIn("123456", message["Subject"])
        self.assertIn("123456", message.get_content())
        self.assertIn("10 minutes", message.get_content())
        self.assertEqual(message["To"], "ada@example.com")

    def test_starttls_login_and_send(self):
        client = MagicMock()
        client.__enter__.return_value = client
        with self._smtp("starttls"), patch.object(email_service.smtplib, "SMTP", return_value=client) as smtp:
            email_service.send_otp_email("ada@example.com", "123456", 600)
        smtp.assert_called_once()
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("user", "pw")
        client.send_message.assert_called_once()

    def test_implicit_ssl_does_not_starttls(self):
        client = MagicMock()
        client.__enter__.return_value = client
        with self._smtp("ssl"), patch.object(email_service.smtplib, "SMTP_SSL", return_value=client):
            email_service.send_otp_email("ada@example.com", "123456", 600)
        client.starttls.assert_not_called()
        client.send_message.assert_called_once()

    def test_provider_failures_become_a_safe_message(self):
        with self._smtp("starttls"), patch.object(email_service.smtplib, "SMTP", side_effect=OSError("secret host detail")):
            with self.assertRaises(email_service.EmailDeliveryError) as caught:
                email_service.send_otp_email("ada@example.com", "123456", 600)
        self.assertNotIn("secret host detail", str(caught.exception))

    def test_sending_without_configuration_is_refused(self):
        with patch.multiple(settings, smtp_host="", smtp_from=""):
            with self.assertRaises(email_service.EmailDeliveryError):
                email_service.send_otp_email("ada@example.com", "123456", 600)


class SignInRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = (auth_service.AUTH_DIR, auth_service.AUTH_DB, auth_service._INITIALIZED)
        auth_service.AUTH_DIR = root / "auth"
        auth_service.AUTH_DB = auth_service.AUTH_DIR / "auth.sqlite3"
        auth_service._INITIALIZED = False
        self.patches = [patch.multiple(settings, auth_enabled=True, triven_secret_key="route-test-secret-key-1234567890")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        auth_service.AUTH_DIR, auth_service.AUTH_DB, auth_service._INITIALIZED = self.saved
        self.tmp.cleanup()

    def _request(self, email="ada@example.com"):
        from app.api.routes import auth as auth_route

        with TestClient(app) as client:
            return client.post("/api/v1/auth/otp/request", json={"email": email})

    def test_real_email_is_sent_and_the_code_is_not_returned_to_the_browser(self):
        with patch.multiple(settings, smtp_host="smtp.example.test", smtp_from="no-reply@example.test", demo_auth_show_otp=False), \
                patch("app.api.routes.auth.send_otp_email") as send:
            response = self._request()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["demo_otp"])
        self.assertEqual(response.json()["demo_mode"], False)
        address, otp, ttl = send.call_args.args
        self.assertEqual(address, "ada@example.com")
        self.assertEqual(len(otp), 6)

    def test_a_second_code_inside_the_cooldown_is_refused_so_inboxes_cannot_be_flooded(self):
        with patch.multiple(settings, smtp_host="smtp.example.test", smtp_from="no-reply@example.test", demo_auth_show_otp=False, auth_otp_cooldown_seconds=60), \
                patch("app.api.routes.auth.send_otp_email") as send:
            first = self._request()
            second = self._request()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertIn("Wait", second.json()["detail"])
        self.assertEqual(send.call_count, 1)

    def test_a_delivery_failure_is_a_clean_502(self):
        with patch.multiple(settings, smtp_host="smtp.example.test", smtp_from="no-reply@example.test", demo_auth_show_otp=False), \
                patch("app.api.routes.auth.send_otp_email", side_effect=email_service.EmailDeliveryError("We could not send the sign-in email.")):
            response = self._request()
        self.assertEqual(response.status_code, 502)

    def test_no_email_and_no_demo_mode_is_a_clear_503(self):
        with patch.multiple(settings, smtp_host="", smtp_from="", demo_auth_show_otp=False):
            response = self._request()
        self.assertEqual(response.status_code, 503)

    def test_demo_mode_still_returns_the_code_when_email_is_not_configured(self):
        with patch.multiple(settings, smtp_host="", smtp_from="", demo_auth_show_otp=True):
            response = self._request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["demo_otp"]), 6)


if __name__ == "__main__":
    unittest.main()
