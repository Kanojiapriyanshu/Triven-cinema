import unittest
from unittest.mock import Mock, patch

from app.services.gemini_service import generate_content


class GeminiServiceTests(unittest.TestCase):
    @patch("app.services.gemini_service.time.sleep")
    @patch("app.services.gemini_service.httpx.post")
    def test_retries_503_then_succeeds(self, post, sleep):
        unavailable = Mock(status_code=503)
        unavailable.json.return_value = {"error": {"status": "UNAVAILABLE"}}
        success = Mock(status_code=200)
        success.json.return_value = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        post.side_effect = [unavailable, success]

        with (
            patch("app.services.gemini_service.settings.gemini_api_key", "test-key"),
            patch("app.services.gemini_service.settings.gemini_model", "gemini-primary"),
            patch("app.services.gemini_service.settings.gemini_fallback_models", "gemini-fallback"),
            patch("app.services.gemini_service.settings.gemini_max_attempts_per_model", 3),
            patch("app.services.gemini_service.settings.gemini_retry_backoff_seconds", 0.01),
        ):
            result = generate_content(parts=[{"text": "plan"}])

        self.assertEqual(result.model, "gemini-primary")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()

    @patch("app.services.gemini_service.time.sleep")
    @patch("app.services.gemini_service.httpx.post")
    def test_fails_over_after_primary_retries(self, post, _sleep):
        unavailable = Mock(status_code=503)
        unavailable.json.return_value = {"error": {"status": "UNAVAILABLE"}}
        success = Mock(status_code=200)
        success.json.return_value = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        post.side_effect = [unavailable, unavailable, success]

        with (
            patch("app.services.gemini_service.settings.gemini_api_key", "test-key"),
            patch("app.services.gemini_service.settings.gemini_model", "gemini-primary"),
            patch("app.services.gemini_service.settings.gemini_fallback_models", "gemini-fallback"),
            patch("app.services.gemini_service.settings.gemini_max_attempts_per_model", 2),
            patch("app.services.gemini_service.settings.gemini_retry_backoff_seconds", 0.0),
        ):
            result = generate_content(parts=[{"text": "plan"}])

        self.assertEqual(result.model, "gemini-fallback")
        self.assertEqual(result.attempts, 3)
        self.assertIn("gemini-fallback", post.call_args_list[-1].args[0])


if __name__ == "__main__":
    unittest.main()
