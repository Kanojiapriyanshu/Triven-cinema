import unittest

from app.services.identity_service import sign_workspace_id, verify_workspace_token


class WorkspaceIdentityTests(unittest.TestCase):
    def test_signed_workspace_round_trips(self):
        workspace_id = "0123456789abcdef0123456789abcdef"
        token = sign_workspace_id(workspace_id)
        self.assertEqual(verify_workspace_token(token), workspace_id)

    def test_tampering_is_rejected(self):
        workspace_id = "0123456789abcdef0123456789abcdef"
        token = sign_workspace_id(workspace_id)
        self.assertIsNone(verify_workspace_token(token + "x"))


if __name__ == "__main__":
    unittest.main()
