import importlib.util
import sys
import unittest
from pathlib import Path

from app.services.continuity_service import compose_continuity_prompt, safe_continuity_id
from app.services.scene_planner import create_scene_plan

ROOT = Path(__file__).resolve().parents[1]
MODAL_DIR = ROOT / "modal"
if str(MODAL_DIR) not in sys.path:
    sys.path.append(str(MODAL_DIR))
spec = importlib.util.spec_from_file_location("triven_ltx_worker", MODAL_DIR / "ltx_worker.py")
assert spec and spec.loader
ltx_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ltx_worker)
build_command = ltx_worker.build_command


class CharacterContinuityTests(unittest.TestCase):
    def test_storyboard_repeats_identity_lock_in_every_scene(self):
        result = create_scene_plan(
            "A photorealistic young man in a dark winter jacket walks with a red fox through snow.",
            3,
            "16:9",
        )
        self.assertTrue(result.character_bible)
        self.assertTrue(result.style_bible)
        for scene in result.scenes:
            self.assertIn("[TRIVEN CONTINUITY LOCK]", scene.prompt)
            self.assertIn("CHARACTER BIBLE", scene.prompt)
            self.assertIn("VISUAL STYLE BIBLE", scene.prompt)

    def test_prompt_lock_is_not_duplicated(self):
        prompt = compose_continuity_prompt(
            scene_prompt="The adventurer walks forward.",
            character_bible="Same adventurer face, hair and clothes.",
            style_bible="Feature-animation look.",
            scene_index=0,
            scene_count=2,
        )
        second = compose_continuity_prompt(
            scene_prompt=prompt,
            character_bible="Same adventurer face, hair and clothes.",
            style_bible="Feature-animation look.",
            scene_index=0,
            scene_count=2,
        )
        self.assertEqual(prompt, second)

    def test_ltx_command_uses_first_frame_conditioning(self):
        command = build_command(
            prompt="same character",
            output_path=Path("/tmp/out.mp4"),
            width=768,
            height=432,
            duration_seconds=5,
            seed=42,
            decoder="conv",
            reference_image_path=Path("/tmp/previous.png"),
            reference_strength=0.95,
        )
        image_index = command.index("--image")
        self.assertEqual(command[image_index + 1], "/tmp/previous.png")
        self.assertEqual(command[image_index + 2], "0")
        self.assertEqual(command[image_index + 3], "0.950")

    def test_continuity_id_is_filename_safe(self):
        self.assertEqual(safe_continuity_id("../../story / demo"), "story-demo")

    def test_storyboard_seed_does_not_drift_between_scenes(self):
        page = (ROOT / "apps/web/src/app/page.tsx").read_text()
        routes = (ROOT / "services/api/app/api/routes/generations.py").read_text()
        self.assertNotIn("seed: seed +", page)
        self.assertNotIn("seed=request.seed +", routes)
        self.assertIn("reference_frame_filename", page)
        self.assertIn("extract_last_frame", routes)


if __name__ == "__main__":
    unittest.main()
