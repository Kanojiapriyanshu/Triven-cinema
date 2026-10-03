import unittest
from unittest.mock import patch

from app.services.scene_planner import create_scene_plan


class ScenePlannerResilienceTests(unittest.TestCase):
    def test_single_scene_skips_remote_planner(self):
        with patch("app.services.scene_planner._gemini_storyboard") as remote:
            result = create_scene_plan(
                "A red fox walking through a snowy pine forest at sunrise.",
                1,
                "16:9",
            )
        remote.assert_not_called()
        self.assertEqual(result.source, "direct")
        self.assertEqual(len(result.scenes), 1)
        self.assertIn("red fox", result.scenes[0].prompt.lower())

    def test_multiscene_falls_back_when_gemini_fails(self):
        with patch(
            "app.services.scene_planner._gemini_storyboard",
            side_effect=RuntimeError("Gemini unavailable"),
        ):
            result = create_scene_plan(
                "A red fox walking through a snowy pine forest at sunrise.",
                2,
                "16:9",
            )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(len(result.scenes), 2)
        self.assertIn("Gemini unavailable", result.note or "")


if __name__ == "__main__":
    unittest.main()
