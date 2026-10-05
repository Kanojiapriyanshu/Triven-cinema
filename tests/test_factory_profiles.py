import unittest

from app.schemas.factory import FactoryGenerationRequest
from app.schemas.generation import VideoGenerationRequest
from app.services.video_combiner import delivery_dimensions
from app.services.video_profiles import duration_profile, validate_scene_duration
from app.services.scene_planner import create_scene_plan


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
        request = VideoGenerationRequest(prompt="A cinematic fox walks through fresh snow at sunrise.", quality="1080p", duration_seconds=30)
        validate_scene_duration(quality=request.quality, duration_seconds=request.duration_seconds)

    def test_factory_accepts_multi_minute_target(self):
        request = FactoryGenerationRequest(
            prompt="A cinematic expedition progresses across a snowy forest with synchronized natural sound.",
            target_duration_seconds=120,
            scene_duration_seconds=30,
            quality="1080p",
        )
        self.assertEqual(request.target_duration_seconds, 120)

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
