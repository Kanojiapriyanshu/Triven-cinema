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

    def test_named_characters_do_not_collapse_to_person_one(self):
        prompt = """
# STORY
## OPENING
A little girl named Radha walks beside the Yamuna.

## RADHA — PERMANENT CHARACTER IDENTITY
Radha has warm medium-brown skin and a soft oval face.
### Radha facial identity
Large dark-brown eyes and long dark hair.

# KRISHNA — PERMANENT CHARACTER IDENTITY
Krishna has dark curls, deep-brown eyes, a yellow-gold dhoti and one peacock feather.

# FIRST MEETING
Radha reaches the clearing. Krishna lowers his flute. Radha and Krishna look at one another.
### KRISHNA
“Why did you follow my flute?”
### RADHA
“I don't know.”
""".strip()
        plan = create_scene_plan(prompt, 1, "16:9")
        locks = {lock.label: lock for lock in plan.entity_locks}
        self.assertIn("RADHA", locks)
        self.assertIn("KRISHNA", locks)
        self.assertNotIn("PERSON", locks)
        self.assertEqual(locks["RADHA"].expected_count, 1)
        self.assertEqual(locks["KRISHNA"].expected_count, 1)
        self.assertIn("medium-brown", locks["RADHA"].description)
        self.assertIn("yellow-gold", locks["KRISHNA"].description)

    def test_factory_defaults_to_strict_qc_and_balanced_anchor_strength(self):
        request = FactoryGenerationRequest(
            prompt="A young adventurer walks with a red fox through a snowy forest.",
        )
        self.assertEqual(request.continuity_qc_mode, "strict")
        self.assertEqual(request.continuity_max_retries, 1)
        self.assertEqual(request.continuity_strength, 0.95)


if __name__ == "__main__":
    unittest.main()
