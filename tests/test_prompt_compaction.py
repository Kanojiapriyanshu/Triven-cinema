"""A long creator prompt must keep what is said and done; only look/lighting filler may be dropped."""
import unittest

from app.services.scene_planner import _split_sentences, create_prompt_only_plan

LOOK = (
    "Live-action footage from a high-end studio production, filmed as one continuous static shot with the natural "
    "look of a high-end cinema camera, fine film grain and true-to-life color. "
    "The camera is locked off at eye level in a medium shot, framing @zoe from the hips up in the center of the frame. "
    "Behind her is one seamless, flat studio backdrop in soft baby pink. "
    "@zoe is a 22-year-old woman with long wavy black hair, a thin gold chain necklace and a chunky white and "
    "lavender striped cable-knit sweater, with real human skin, visible pores and natural texture. "
    "Her voice is warm, bright and natural, recorded clean and close. "
    "The lighting is a premium studio setup in clean daylight-white around 5600K: a large soft key light slightly "
    "above eye level, about forty-five degrees to the left of the camera, with a gentle natural shadow on the right "
    "side of her face; a soft fill light from the right; a soft rim light from behind outlining her hair; and a "
    "separate soft light on the backdrop. Large soft catchlights shine in her eyes. "
    "She moves the way a real person talks to a friend: relaxed shoulders, small natural shifts of her weight, and "
    "gentle head tilts and nods on the words she stresses, with both hands and the phone inside the frame. "
    "The color grade stays neutral and clean with soft highlight roll-off, rich but natural skin tones, a very "
    "gentle falloff toward the edges of the backdrop, and no visible logos, text, subtitles or watermarks anywhere. "
)
PERFORMANCE = (
    '@zoe stands relaxed, holding a sleek smartphone in both hands at chest height. '
    'She smiles into the lens and says: "Okay… this is it. The iPhone Eighteen." '
    'She slowly tilts the phone to show its back, then says: "I\'ve been waiting for this one." '
    '@zoe looks back into the lens, her eyebrows lifting, and says: "So let\'s find out if it\'s actually worth it." '
    "She blinks naturally and breathes between sentences. "
    "The only sound is her voice, over a very quiet room tone."
)


class SentenceSplitTests(unittest.TestCase):
    def test_never_splits_inside_a_spoken_line(self):
        parts = _split_sentences('She says: "Okay… this is it. The iPhone 18." She smiles. Then she waves.')
        self.assertEqual(parts, ['She says: "Okay… this is it. The iPhone 18."', "She smiles.", "Then she waves."])

    def test_a_line_that_ends_with_a_closing_quote_ends_the_sentence(self):
        parts = _split_sentences('She says: "Hello." He nods. He says: "Hi there!" The end.')
        self.assertEqual(len(parts), 4)
        self.assertTrue(parts[0].endswith('"Hello."'))

    def test_curly_quotes_are_respected(self):
        parts = _split_sentences("She says: “Wait. Look at this.” Then she leaves.")
        self.assertEqual(len(parts), 2)

    def test_unbalanced_quotes_fall_back_to_plain_splitting(self):
        parts = _split_sentences('She says: "Hello there. How are you? He waves.')
        self.assertGreater(len(parts), 1)


class SingleShotCompactionTests(unittest.TestCase):
    def test_dialogue_and_action_survive_a_long_look_description(self):
        prompt = LOOK + PERFORMANCE
        self.assertGreater(len(prompt.split()), 320)
        scene = create_prompt_only_plan(prompt, 1, target_scene_duration_seconds=15).scenes[0].prompt
        for required in (
            "The iPhone Eighteen",
            "tilts the phone to show its back",
            "waiting for this one",
            "actually worth it",
            "only sound is her voice",
        ):
            self.assertIn(required, scene)
        self.assertEqual(scene.count('"') % 2, 0, "a spoken line was cut in half")

    def test_filler_is_dropped_before_the_performance(self):
        filler = "Natural studio production detail. " * 150
        scene = create_prompt_only_plan(LOOK + filler + PERFORMANCE, 1, target_scene_duration_seconds=15).scenes[0].prompt
        self.assertIn("waiting for this one", scene)
        self.assertIn("actually worth it", scene)
        self.assertLess(scene.count("Natural studio production detail"), 150)

    def test_short_prompts_are_not_touched(self):
        prompt = '@zoe says: "Hi." She waves.'
        scene = create_prompt_only_plan(prompt, 1, target_scene_duration_seconds=15).scenes[0].prompt
        self.assertIn(prompt, scene)

    def test_sentence_order_is_preserved(self):
        scene = create_prompt_only_plan(LOOK + PERFORMANCE, 1, target_scene_duration_seconds=15).scenes[0].prompt
        self.assertLess(scene.index("Okay"), scene.index("waiting for this one"))
        self.assertLess(scene.index("waiting for this one"), scene.index("actually worth it"))


class ParagraphPerSceneTests(unittest.TestCase):
    PRESENTER = (
        '@zoe stands in front of a pink backdrop and says: "Okay… this is it. The new phone." '
        'She smiles and says: "I have been waiting for this one." She looks at the lens and says: "Is it worth it?" '
        "She blinks naturally and breathes between sentences."
    )
    PRODUCT = (
        "Product close-up of @phone on a pink surface. Soft light slowly glides across its glass back, "
        "then the camera pushes in. No people and no text."
    )

    BOTH = PRESENTER + "\n\n" + PRODUCT

    def test_one_paragraph_per_scene_is_kept_intact(self):
        plan = create_prompt_only_plan(self.BOTH, 2, target_scene_duration_seconds=15)
        first, second = plan.scenes[0].prompt, plan.scenes[1].prompt
        self.assertIn("Is it worth it?", first)
        self.assertNotIn("Product close-up", first)
        self.assertIn("glides across its glass back", second)
        self.assertIn("No people and no text", second)
        self.assertNotIn("Is it worth it?", second)

    def test_a_scene_that_follows_does_not_claim_a_previous_frame(self):
        plan = create_prompt_only_plan(self.BOTH, 2, target_scene_duration_seconds=15)
        self.assertNotIn("supplied previous frame", plan.scenes[1].prompt)
        self.assertIn("supplied first frame", plan.scenes[1].prompt)

    def test_paragraph_count_not_matching_scene_count_still_uses_the_story_splitter(self):
        plan = create_prompt_only_plan(self.BOTH, 3, target_scene_duration_seconds=15)
        self.assertEqual(len(plan.scenes), 3)


if __name__ == "__main__":
    unittest.main()
