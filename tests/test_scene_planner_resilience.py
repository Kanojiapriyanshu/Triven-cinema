import unittest
from unittest.mock import patch

import httpx

from app.services.scene_planner import create_scene_plan_with_meta


class ScenePlannerResilienceTests(unittest.TestCase):
    def test_single_scene_skips_gemini(self):
        result = create_scene_plan_with_meta(
            "A fox walks through snow.",
            scene_count=1,
            aspect_ratio="16:9",
        )
        self.assertEqual(result.source, "direct")
        self.assertEqual(len(result.scenes), 1)
        self.assertEqual(result.scenes[0].prompt, "A fox walks through snow.")

    @patch("app.services.scene_planner._generate_with_gemini")
    def test_timeout_falls_back_to_exact_scene_count(self, mocked):
        mocked.side_effect = httpx.ReadTimeout("slow")
        result = create_scene_plan_with_meta(
            "A fox walks through snow.",
            scene_count=3,
            aspect_ratio="16:9",
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(len(result.scenes), 3)
        self.assertIn("editable local storyboard", result.note or "")


if __name__ == "__main__":
    unittest.main()
