import unittest

from app.schemas.factory import FactoryGenerationRequest
from app.services.scene_planner import create_scene_plan


class EntityCardinalityGuardTests(unittest.TestCase):
    def test_local_planner_detects_common_single_subjects(self):
        plan = create_scene_plan(
            "A photorealistic young man in a blue jacket walks beside a red fox through snow.",
            1,
            "16:9",
        )
        locks = {lock.label: lock.expected_count for lock in plan.entity_locks}
        self.assertEqual(locks.get("PERSON"), 1)
        self.assertEqual(locks.get("FOX"), 1)
        self.assertIn("ENTITY COUNT LOCK", plan.scenes[0].prompt)

    def test_explicit_multiple_subject_count_is_preserved(self):
        plan = create_scene_plan(
            "Two robots walk together through a neon warehouse.",
            1,
            "16:9",
        )
        locks = {lock.label: lock.expected_count for lock in plan.entity_locks}
        self.assertEqual(locks.get("ROBOT"), 2)

    def test_factory_defaults_to_auto_qc_and_full_anchor_strength(self):
        request = FactoryGenerationRequest(
            prompt="A young adventurer walks with a red fox through a snowy forest.",
        )
        self.assertEqual(request.continuity_qc_mode, "auto")
        self.assertEqual(request.continuity_max_retries, 1)
        self.assertEqual(request.continuity_strength, 1.0)


if __name__ == "__main__":
    unittest.main()
