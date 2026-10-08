"""Prompt wording that LTX renders as a blown hazy glow is neutralised."""
import unittest
from unittest.mock import patch

import re

from app.core.config import settings
from app.services.continuity_service import compose_render_integrity_prompt
from app.services.lighting_hygiene import (
    BACKGROUND_AUTHORITY_NOTE,
    EXPOSURE_INTEGRITY_NOTE,
    normalize_lighting,
)


class NormalizeLightingTests(unittest.TestCase):
    def test_the_real_bloom_line_is_neutralised_but_direction_is_kept(self):
        line = "Soft key light from the front left, shallow depth of field, natural film look."
        cleaned, changes = normalize_lighting(line)
        low = cleaned.lower()
        self.assertNotIn("soft key light", low)
        self.assertNotIn("shallow depth of field", low)
        self.assertNotIn("natural film look", low)
        self.assertIn("from the front left", low)   # framing/direction survives
        self.assertIn("even key light", low)
        self.assertTrue(changes)

    def test_flare_and_backlight_vocabulary_is_removed(self):
        for trigger in ["lens flare", "backlit", "golden hour", "god rays", "overexposed", "hazy", "dreamy glow"]:
            cleaned, _ = normalize_lighting(f"a shot with {trigger} over her face")
            self.assertNotIn(trigger.split()[0].lower(), cleaned.lower(), trigger)

    def test_clean_prompt_is_left_alone(self):
        clean = "She stands against a pink backdrop holding a phone and speaks to camera."
        cleaned, changes = normalize_lighting(clean)
        self.assertEqual(cleaned, clean)
        self.assertEqual(changes, [])

    def test_no_double_spaces_left_behind(self):
        cleaned, _ = normalize_lighting("warm soft light, and a calm mood")
        self.assertNotIn("  ", cleaned)


class ExposureNoteSafetyTests(unittest.TestCase):
    def test_the_notes_never_name_an_artifact_lts_would_then_render(self):
        # LTX has no negative prompt: naming these nouns summons them. The notes must be positive-only.
        for note in (EXPOSURE_INTEGRITY_NOTE, BACKGROUND_AUTHORITY_NOTE):
            low = note.lower()
            for word in ["bloom", "haze", "hazy", "glare", "flare", "light wash", "blown", "overexpos", "halo"]:
                self.assertNotIn(word, low, f"note must not contain {word!r}: {note[:30]}")
            self.assertFalse(
                re.search(r"\b(no|not|without|avoid|never|free of)\b", low),
                f"note must be positive-only (no negation words): {note[:30]}",
            )

    def test_the_whole_composed_prompt_is_free_of_summoning_nouns(self):
        out = compose_render_integrity_prompt("Soft key light, shallow depth of field, natural film look.").lower()
        for word in ["bloom", "hazy", " glare", "lens flare", "light wash", "blown-out"]:
            self.assertNotIn(word, out, f"composed prompt leaked {word!r}")


class IntegrityCompositionTests(unittest.TestCase):
    def test_exposure_and_background_constraints_are_appended_when_enabled(self):
        out = compose_render_integrity_prompt("Soft key light, shallow depth of field.")
        self.assertIn("EXPOSURE INTEGRITY", out)
        self.assertIn("BACKGROUND AUTHORITY", out)
        self.assertNotIn("soft key light", out.lower())

    def test_hygiene_can_be_switched_off(self):
        with patch.object(settings, "lighting_hygiene_enabled", False):
            out = compose_render_integrity_prompt("Soft key light, shallow depth of field.")
        self.assertNotIn("EXPOSURE INTEGRITY", out)
        self.assertIn("soft key light", out.lower())  # user wording untouched when off

    def test_composition_is_idempotent(self):
        once = compose_render_integrity_prompt("Soft key light from the front left.")
        twice = compose_render_integrity_prompt(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
