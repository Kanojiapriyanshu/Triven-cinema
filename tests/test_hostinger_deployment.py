import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class HostingerDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
        self.services = self.compose["services"]

    def test_only_caddy_publishes_public_ports(self):
        self.assertNotIn("ports", self.services["api"])
        self.assertNotIn("ports", self.services["web"])
        self.assertNotIn("ports", self.services["maintenance"])
        caddy_ports = {str(value) for value in self.services["caddy"]["ports"]}
        self.assertIn("80:80", caddy_ports)
        self.assertIn("443:443", caddy_ports)

    def test_api_and_maintenance_share_persistent_storage(self):
        self.assertIn("./storage:/app/storage", self.services["api"]["volumes"])
        self.assertIn("./storage:/app/storage", self.services["maintenance"]["volumes"])

    def test_production_template_protects_paid_render_path(self):
        text = (ROOT / ".env.production.example").read_text()
        self.assertIn("APP_ENV=\"production\"", text)
        self.assertIn("VIDEO_PROVIDER=\"modal\"", text)
        self.assertIn("ENABLE_SYNC_RENDER_ENDPOINTS=false", text)
        self.assertIn("JOB_WORKERS=1", text)
        self.assertIn("JOB_MAX_PENDING=3", text)


if __name__ == "__main__":
    unittest.main()
