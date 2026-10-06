import unittest
from unittest.mock import patch

from app.services.scene_planner import create_prompt_only_plan, create_scene_plan


class ScenePlannerResilienceTests(unittest.TestCase):
    def test_prompt_only_factory_plan_never_calls_gemini_and_sequences_source(self):
        prompt = """
# CORE VISUAL STYLE
Premium Indian mythological cinematic animation with warm volumetric sunset light.

# STORY
## OPENING
Radha walks beside the Yamuna and hears a distant flute.

## FOLLOWING THE FLUTE
Radha follows the melody through flowering vines and kadamba trees.

## FIRST REVEAL
Krishna stands in a clearing with the flute and Radha sees him.
""".strip()
        with patch("app.services.scene_planner._gemini_storyboard") as remote:
            result = create_prompt_only_plan(
                prompt,
                3,
                target_scene_duration_seconds=8,
            )
        remote.assert_not_called()
        self.assertEqual(result.source, "direct")
        self.assertEqual(len(result.scenes), 3)
        self.assertEqual(len({scene.prompt for scene in result.scenes}), 3)
        self.assertIn("Radha walks beside the Yamuna", result.scenes[0].prompt)
        self.assertIn("flowering vines", result.scenes[1].prompt)
        self.assertIn("Krishna stands in a clearing", result.scenes[2].prompt)
        self.assertNotIn("Krishna stands in a clearing", result.scenes[0].prompt)
        self.assertTrue(all(len(scene.prompt.split()) <= 190 for scene in result.scenes))
        self.assertTrue(all(scene.duration_seconds == 8 for scene in result.scenes))
        self.assertIn("AI Enhancement is OFF", result.note or "")

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

    def test_fallback_uses_story_sections_not_speaker_headings(self):
        prompt = """
# STORY
## OPENING — THE FOREST THAT SPOKE
Radha walks beside the Yamuna and hears a distant flute.
### NARRATOR
“Long before the moon learned how to paint Vrindavan silver...”

## FIRST REVEAL OF KRISHNA
Krishna stands in a clearing and lowers the flute. Radha sees him.
### KRISHNA
“Why did you follow my flute?”
### RADHA
“I don't know.”

## AFTER KRISHNA LEAVES
Radha stands alone by the river. Do not show Krishna physically nearby.
""".strip()
        with patch(
            "app.services.scene_planner._gemini_storyboard",
            side_effect=RuntimeError("Gemini unavailable"),
        ):
            result = create_scene_plan(prompt, 3, "16:9")

        self.assertEqual(result.source, "fallback")
        self.assertEqual(
            [scene.title for scene in result.scenes],
            ["OPENING — THE FOREST THAT SPOKE", "FIRST REVEAL OF KRISHNA", "AFTER KRISHNA LEAVES"],
        )
        self.assertTrue(all("NARRATOR" != scene.title for scene in result.scenes))
        self.assertTrue(all(len(scene.prompt.split()) <= 200 for scene in result.scenes))
        # The fallback no longer pastes the entire manuscript into every LTX shot.
        self.assertTrue(all(scene.prompt.count("FIRST REVEAL OF KRISHNA") <= 1 for scene in result.scenes))


if __name__ == "__main__":
    unittest.main()
