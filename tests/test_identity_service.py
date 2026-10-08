import unittest
from unittest.mock import patch

from fastapi import Request

from app.core.config import settings
from app.services.identity_service import sign_workspace_id, verify_workspace_token, workspace_id_from_request


class WorkspaceIdentityTests(unittest.TestCase):
    def test_signed_workspace_round_trips(self):
        workspace_id = "0123456789abcdef0123456789abcdef"
        token = sign_workspace_id(workspace_id)
        self.assertEqual(verify_workspace_token(token), workspace_id)

    def test_tampering_is_rejected(self):
        workspace_id = "0123456789abcdef0123456789abcdef"
        token = sign_workspace_id(workspace_id)
        self.assertIsNone(verify_workspace_token(token + "x"))

    def _request_with_workspace(self, workspace_id):
        cookie = f"triven_workspace={sign_workspace_id(workspace_id)}".encode()
        return Request({"type": "http", "headers": [(b"cookie", cookie)]})

    def test_current_account_overrides_a_stale_workspace_cookie(self):
        with patch.multiple(settings, app_env="production", auth_enabled=True, auto_login_email="", triven_secret_key="x" * 40), \
                patch("app.services.auth_service.auth_user_from_request", return_value={"workspace_id": "a" * 32}):
            request = self._request_with_workspace("b" * 32)
            self.assertEqual(workspace_id_from_request(request), "a" * 32)

    def test_standalone_workspace_cookie_cannot_authorize_production_media(self):
        with patch.multiple(settings, app_env="production", auth_enabled=True, auto_login_email="", triven_secret_key="x" * 40), \
                patch("app.services.auth_service.auth_user_from_request", return_value=None):
            request = self._request_with_workspace("b" * 32)
            self.assertIsNone(workspace_id_from_request(request))


if __name__ == "__main__":
    unittest.main()
