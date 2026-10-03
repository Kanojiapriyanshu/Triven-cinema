import time
import unittest

from app.services.job_service import get_job, submit_job


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


if __name__ == "__main__":
    unittest.main()
