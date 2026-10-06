import unittest

from app.schemas.factory import FactoryGenerationRequest
from app.schemas.generation import ScenePlanRequest, VideoGenerationRequest
from app.services.video_combiner import delivery_dimensions
from app.services.video_profiles import duration_profile, validate_factory_scene_duration, validate_scene_duration
from app.services.scene_planner import create_scene_plan
from app.services.factory_service import _factory_scene_durations, _scene_seed


class FactoryProfileTests(unittest.TestCase):
    def test_delivery_4k_dimensions(self):
        self.assertEqual(delivery_dimensions("16:9", "4k"), (3840, 2160))
        self.assertEqual(delivery_dimensions("9:16", "4k"), (2160, 3840))
        self.assertEqual(delivery_dimensions("1:1", "4k"), (2160, 2160))

    def test_default_duration_profile(self):
        profile = duration_profile()
        self.assertGreaterEqual(profile["1080p"], 30)
        self.assertGreaterEqual(profile["4k"], 15)

    def test_schema_accepts_thirty_second_1080p_scene(self):
        request = VideoGenerationRequest(
            prompt="A cinematic fox walks through fresh snow at sunrise.",
            quality="1080p",
            duration_seconds=30,
        )
        validate_scene_duration(quality=request.quality, duration_seconds=request.duration_seconds)

    def test_factory_accepts_multi_minute_target(self):
        request = FactoryGenerationRequest(
            prompt="A cinematic expedition progresses across a snowy forest with synchronized natural sound.",
            target_duration_seconds=120,
            scene_duration_seconds=30,
            quality="1080p",
        )
        self.assertEqual(request.target_duration_seconds, 120)

    def test_factory_defaults_to_twenty_second_single_pass_scenes(self):
        request = FactoryGenerationRequest(
            prompt="A cinematic expedition progresses across a snowy forest with synchronized natural sound."
        )
        self.assertEqual(request.scene_duration_seconds, 20)
        self.assertEqual(request.continuity_qc_mode, "strict")
        self.assertEqual(request.continuity_strength, 0.85)

    def test_factory_rejects_sub_fifteen_second_scene(self):
        with self.assertRaises(ValueError):
            FactoryGenerationRequest(
                prompt="A cinematic expedition progresses across a snowy forest with synchronized natural sound.",
                scene_duration_seconds=10,
            )

    def test_factory_validates_standard_fifteen_and_twenty_second_scenes(self):
        validate_factory_scene_duration(quality="1080p", duration_seconds=15)
        validate_factory_scene_duration(quality="1080p", duration_seconds=20)

    def test_factory_allows_experimental_thirty_second_1080p_single_pass(self):
        validate_factory_scene_duration(quality="1080p", duration_seconds=30)

    def test_factory_keeps_4k_at_fifteen_seconds(self):
        validate_factory_scene_duration(quality="4k", duration_seconds=15)
        with self.assertRaises(ValueError):
            validate_factory_scene_duration(quality="4k", duration_seconds=20)

    def test_factory_does_not_create_sub_fifteen_second_tail_scene(self):
        self.assertEqual(_factory_scene_durations(30, 20, 15), [15.0, 15.0])
        self.assertEqual(_factory_scene_durations(60, 20, 15), [20.0, 20.0, 20.0])
        self.assertEqual(_factory_scene_durations(60, 30, 15), [30.0, 30.0])

    def test_factory_uses_distinct_deterministic_seed_per_scene(self):
        seeds = [_scene_seed(42, index, 0) for index in range(6)]
        self.assertEqual(len(set(seeds)), 6)
        self.assertEqual(seeds, [_scene_seed(42, index, 0) for index in range(6)])
        self.assertNotEqual(_scene_seed(42, 2, 0), _scene_seed(42, 2, 1))

    def test_factory_and_storyboard_accept_long_manuscripts(self):
        manuscript = "Vrindavan story beat. " * 1300
        self.assertGreater(len(manuscript), 8000)
        self.assertLess(len(manuscript), 50000)
        factory = FactoryGenerationRequest(prompt=manuscript)
        storyboard = ScenePlanRequest(prompt=manuscript, scene_count=8)
        self.assertEqual(factory.prompt, manuscript)
        self.assertEqual(storyboard.prompt, manuscript)

    def test_individual_render_keeps_bounded_prompt_limit(self):
        with self.assertRaises(ValueError):
            VideoGenerationRequest(prompt="x" * 8001)

    def test_factory_storyboard_is_paced_for_long_scene(self):
        plan = create_scene_plan(
            "A cinematic expedition progresses across a snowy forest with synchronized natural sound.",
            1,
            "16:9",
            target_scene_duration_seconds=30,
        )
        self.assertEqual(plan.scenes[0].duration_seconds, 30)


if __name__ == "__main__":
    unittest.main()
