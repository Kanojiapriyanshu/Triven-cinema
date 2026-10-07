import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.services import auth_service, chat_service


class AuthAndChatTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)

        self.original_auth_dir = auth_service.AUTH_DIR
        self.original_auth_db = auth_service.AUTH_DB
        self.original_auth_initialized = auth_service._INITIALIZED
        auth_service.AUTH_DIR = root / "auth"
        auth_service.AUTH_DB = auth_service.AUTH_DIR / "auth.sqlite3"
        auth_service._INITIALIZED = False

        self.original_chat_dir = chat_service.CHAT_DIR
        self.original_chat_db = chat_service.CHAT_DB
        self.original_chat_initialized = chat_service._INITIALIZED
        chat_service.CHAT_DIR = root / "chats"
        chat_service.CHAT_DB = chat_service.CHAT_DIR / "chats.sqlite3"
        chat_service._INITIALIZED = False

        self.original_secret = settings.triven_secret_key
        self.original_env = settings.app_env
        settings.triven_secret_key = "unit-test-secret-key"
        settings.app_env = "development"

    def tearDown(self):
        auth_service.AUTH_DIR = self.original_auth_dir
        auth_service.AUTH_DB = self.original_auth_db
        auth_service._INITIALIZED = self.original_auth_initialized
        chat_service.CHAT_DIR = self.original_chat_dir
        chat_service.CHAT_DB = self.original_chat_db
        chat_service._INITIALIZED = self.original_chat_initialized
        settings.triven_secret_key = self.original_secret
        settings.app_env = self.original_env
        self.tempdir.cleanup()

    def test_demo_otp_creates_stable_account_and_signed_session(self):
        preferred_workspace = "a" * 32
        _, otp, ttl = auth_service.request_otp("Creator@Example.com")
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())
        self.assertGreaterEqual(ttl, 60)

        user = auth_service.verify_otp(
            "creator@example.com",
            otp,
            preferred_workspace_id=preferred_workspace,
        )
        self.assertEqual(user["email"], "creator@example.com")
        self.assertEqual(user["workspace_id"], preferred_workspace)

        token = auth_service.sign_auth_user(user)
        verified = auth_service.verify_auth_token(token)
        self.assertIsNotNone(verified)
        self.assertEqual(verified["id"], user["id"])

        _, second_otp, _ = auth_service.request_otp("creator@example.com")
        second_user = auth_service.verify_otp(
            "creator@example.com",
            second_otp,
            preferred_workspace_id="b" * 32,
        )
        self.assertEqual(second_user["id"], user["id"])
        self.assertEqual(second_user["workspace_id"], preferred_workspace)

    def test_wrong_otp_is_rejected(self):
        _, otp, _ = auth_service.request_otp("wrong@example.com")
        wrong = "000000" if otp != "000000" else "999999"
        with self.assertRaises(auth_service.AuthError):
            auth_service.verify_otp("wrong@example.com", wrong)

    def test_chat_history_is_workspace_scoped_and_deletable(self):
        workspace_a = "a" * 32
        workspace_b = "b" * 32
        saved = chat_service.save_chat(
            workspace_a,
            "chat-12345678",
            title=" First   scene ",
            workspace={"prompt": "A natural portrait", "quality": "1080p"},
            created_at=100,
            updated_at=200,
        )
        self.assertEqual(saved["title"], "First scene")
        self.assertEqual(len(chat_service.list_chats(workspace_a)), 1)
        self.assertEqual(chat_service.list_chats(workspace_b), [])
        self.assertTrue(chat_service.delete_chat(workspace_a, "chat-12345678"))
        self.assertEqual(chat_service.list_chats(workspace_a), [])


if __name__ == "__main__":
    unittest.main()
