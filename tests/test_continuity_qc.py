import unittest
from pathlib import Path

from app.schemas.generation import EntityLock
from app.services.continuity_qc import evaluate_scene_cardinality


class ContinuityQCTests(unittest.TestCase):
    def test_off_mode_skips_without_touching_media(self):
        result = evaluate_scene_cardinality(
            Path("/does/not/need/to/exist.mp4"),
            entity_locks=[EntityLock(label="LEO", expected_count=1)],
            visible_entity_counts={"LEO": 1},
            character_bible="LEO is the recurring adventurer.",
            scene_prompt="LEO walks forward.",
            qc_mode="off",
        )
        self.assertTrue(result.skipped)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
