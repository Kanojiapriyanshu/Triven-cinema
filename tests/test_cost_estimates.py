import unittest
from unittest.mock import patch

from app.services.metrics_service import estimate_gpu_cost


class CostEstimateTests(unittest.TestCase):
    @patch("app.services.metrics_service.gpu_hourly_rate", return_value=3.6)
    def test_cost_math(self, _rate):
        cost, per_minute, note = estimate_gpu_cost(
            render_seconds=10,
            gpu="B200",
            output_duration_seconds=5,
        )
        self.assertAlmostEqual(cost, 0.01, places=6)
        self.assertAlmostEqual(per_minute, 0.12, places=4)
        self.assertIn("Estimated", note)

    @patch("app.services.metrics_service.gpu_hourly_rate", return_value=0.0)
    def test_unconfigured_rate_returns_none(self, _rate):
        cost, per_minute, note = estimate_gpu_cost(
            render_seconds=10,
            gpu="B200",
            output_duration_seconds=5,
        )
        self.assertIsNone(cost)
        self.assertIsNone(per_minute)
        self.assertIn("not configured", note)


if __name__ == "__main__":
    unittest.main()
