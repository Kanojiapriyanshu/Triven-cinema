import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.api.routes import health
from app.core.config import settings


class ReadinessTests(unittest.TestCase):
    def test_storage_probe_creates_missing_directory_and_leaves_no_files(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Path(folder) / "storage"
            with patch.object(health, "STORAGE_DIR", storage):
                self.assertTrue(health._storage_writable())
            self.assertEqual(list(storage.iterdir()), [])

    def test_unavailable_disk_returns_not_ready_instead_of_an_internal_error(self):
        with patch.object(health, "_storage_writable", return_value=False), \
                patch.object(health.shutil, "disk_usage", side_effect=OSError("unavailable")), \
                patch.object(health.shutil, "which", return_value="/usr/bin/tool"):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(health.readiness_check())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail["status"], "not_ready")

    def test_full_disk_returns_not_ready(self):
        with patch.object(health, "_storage_writable", return_value=True), \
                patch.object(health, "_disk_free_gb", return_value=1.0), \
                patch.object(health.shutil, "which", return_value="/usr/bin/tool"), \
                patch.object(settings, "minimum_free_disk_gb", 10.0):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(health.readiness_check())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertFalse(caught.exception.detail["checks"]["disk_ok"])


if __name__ == "__main__":
    unittest.main()
