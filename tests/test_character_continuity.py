import importlib.util
import sys
import unittest
from pathlib import Path

from app.schemas.generation import EntityLock
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
        self.assertEqual(command[image_index + 1], str(Path("/tmp/previous.png")))
        self.assertEqual(command[image_index + 2], "0")
        self.assertEqual(command[image_index + 3], "0.950")
        self.assertEqual(command[image_index + 4], "0")


    def test_reference_prompt_treats_existing_character_as_single_instance(self):
        prompt = compose_continuity_prompt(
            scene_prompt="Leo extends his hand toward the fox.",
            character_bible="LEO has short brown hair and a blue jacket. FOX has red fur.",
            style_bible="Cinematic feature animation.",
            scene_index=1,
            scene_count=2,
            entity_locks=[
                EntityLock(label="LEO", expected_count=1, description="main adventurer"),
                EntityLock(label="FOX", expected_count=1, description="red fox companion"),
            ],
            visible_entity_counts={"LEO": 1, "FOX": 1},
            reference_frame_present=True,
        )
        self.assertIn("THIS SHOT MUST SHOW EXACTLY: LEO=1, FOX=1", prompt)
        self.assertIn("one and only canonical physical instance", prompt)
        self.assertIn("DO NOT introduce, recreate, re-enter, spawn, mirror or clone", prompt)
        self.assertIn("Never create duplicate copies", prompt)


    def test_scene_wardrobe_override_does_not_freeze_reference_clothing(self):
        prompt = compose_continuity_prompt(
            scene_prompt="The presenter now wears a white and soft-lavender cable-knit sweater.",
            character_bible="Same presenter face, hair and body proportions.",
            style_bible="Photoreal studio footage.",
            scene_index=1,
            scene_count=2,
            reference_frame_present=True,
            prompt_wardrobe_authoritative=True,
        )
        self.assertIn("current scene wardrobe is authoritative", prompt.lower())
        self.assertIn("WARDROBE OVERRIDE", prompt)
        self.assertIn("white and soft-lavender cable-knit sweater", prompt)

    def test_continuity_id_is_filename_safe(self):
        self.assertEqual(safe_continuity_id("../../story / demo"), "story-demo")

    def test_storyboard_seed_does_not_drift_between_scenes(self):
        page = (ROOT / "apps/web/src/app/page.tsx").read_text(encoding="utf-8")
        routes = (ROOT / "services/api/app/api/routes/generations.py").read_text(encoding="utf-8")
        self.assertNotIn("seed: seed +", page)
        self.assertNotIn("seed=request.seed +", routes)
        self.assertIn("reference_frame_filename", page)
        self.assertIn("extract_continuity_frame", routes)


if __name__ == "__main__":
    unittest.main()
