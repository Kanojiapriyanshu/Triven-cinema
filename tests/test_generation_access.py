import unittest
from unittest.mock import patch

from fastapi import HTTPException, Request, Response

from app.api.routes import generations
from app.schemas.generation import VideoGenerationRequest


class GenerationAccessTests(unittest.TestCase):
    def _payload(self):
        return VideoGenerationRequest(
            prompt="A quiet shot beside the sea",
            continuity_mode="strict",
            reference_frame_filename="private-reference.png",
        )

    def test_another_workspace_reference_is_rejected_before_charging_or_queueing(self):
        with patch.object(generations, "ensure_workspace", return_value="a" * 32), \
                patch.object(generations, "workspace_owns_generated_file", return_value=False), \
                patch.object(generations, "consume_credits") as charge, \
                patch.object(generations, "submit_job") as submit:
            with self.assertRaises(HTTPException) as caught:
                generations.create_video_job(self._payload(), Request({"type": "http"}), Response())
        self.assertEqual(caught.exception.status_code, 404)
        charge.assert_not_called()
        submit.assert_not_called()

    def test_owned_reference_can_be_queued(self):
        with patch.object(generations, "ensure_workspace", return_value="a" * 32), \
                patch.object(generations, "workspace_owns_generated_file", return_value=True) as ownership, \
                patch.object(generations, "media_tools_error", return_value=None), \
                patch.object(generations, "consume_credits"), \
                patch.object(generations, "submit_job", return_value="job-123") as submit:
            result = generations.create_video_job(self._payload(), Request({"type": "http"}), Response())
        self.assertEqual(result.job_id, "job-123")
        ownership.assert_called_once_with("a" * 32, "private-reference.png")
        self.assertEqual(submit.call_args.args[1]["workspace_id"], "a" * 32)


if __name__ == "__main__":
    unittest.main()
