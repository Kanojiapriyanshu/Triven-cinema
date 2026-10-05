import time
import unittest

from app.services.job_service import get_job, submit_job, workspace_owns_generated_file


class JobServiceTests(unittest.TestCase):
    def test_background_job_reaches_completed(self):
        job_id = submit_job(
            "test",
            {"hello": "world"},
            lambda _job_id: {"ok": True},
        )

        deadline = time.time() + 3
        job = None
        while time.time() < deadline:
            job = get_job(job_id)
            if job and job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"], {"ok": True})


    def test_generated_file_is_scoped_to_workspace(self):
        filename = "factory-secure-test.mp4"
        owner = "a" * 32
        other = "b" * 32
        job_id = submit_job(
            "factory-test",
            {"workspace_id": owner},
            lambda _job_id: {
                "final_video_url": f"/media/generated/{filename}",
                "final_filename": filename,
            },
        )

        deadline = time.time() + 3
        while time.time() < deadline:
            job = get_job(job_id)
            if job and job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        self.assertTrue(workspace_owns_generated_file(owner, filename))
        self.assertFalse(workspace_owns_generated_file(other, filename))



if __name__ == "__main__":
    unittest.main()
