"""Frozen-still guard: a held reference image with audio must be retried, not delivered silently."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

from app.core.config import settings
from app.schemas.elements import ResolvedElementBinding
from app.schemas.factory import FactoryGenerationRequest
from app.services import factory_service, motion_qc
from app.services.continuity_service import MOTION_RETRY_NOTE
from app.services.motion_qc import MotionReport, measure_motion, motion_report


def frame(shift: int = 0) -> Image.Image:
    image = Image.new("RGB", (160, 90), (40, 40, 48))
    ImageDraw.Draw(image).ellipse((50 + shift, 15, 110 + shift, 75), fill=(220, 180, 160))
    return image


class MotionReportTests(unittest.TestCase):
    def test_identical_frames_are_a_frozen_still(self):
        report = motion_report([frame(), frame(), frame(), frame()])
        self.assertTrue(report.still)
        self.assertEqual(report.mean_diff, 0.0)

    def test_a_moving_subject_is_not_flagged(self):
        report = motion_report([frame(0), frame(8), frame(16), frame(8), frame(0)])
        self.assertFalse(report.still)
        self.assertGreater(report.mean_diff, settings.motion_guard_min_mean_diff)

    def test_compression_noise_alone_still_counts_as_frozen(self):
        base = frame()
        noisy = base.copy()
        noisy.putpixel((3, 3), (45, 45, 52))
        self.assertTrue(motion_report([base, noisy, base, noisy]).still)

    def test_a_single_frame_cannot_be_judged(self):
        self.assertFalse(motion_report([frame()]).still)

    def test_measure_motion_skips_instead_of_failing_when_frames_cannot_be_read(self):
        def broken(_path):
            raise RuntimeError("ffmpeg is not installed")

        self.assertIsNone(measure_motion(Path("x.mp4"), frame_loader=broken))

    def test_guard_can_be_disabled(self):
        with patch.object(settings, "factory_motion_guard_enabled", False):
            self.assertIsNone(measure_motion(Path("x.mp4"), frame_loader=lambda _p: [frame(), frame()]))


def character(strength: float = 1.0) -> ResolvedElementBinding:
    return ResolvedElementBinding(
        element_id="el_char2", version_id="ev_char2", handle="char2", name="Char2", type="character",
        description="", reference_mode="identity", wardrobe_policy="prompt", strength=strength,
        apply_to_all_scenes=True, primary_asset_path=str(Path(tempfile.gettempdir()) / "char2.png"),
        primary_asset_url="/a.png",
    )


class FactoryMotionGuardTests(unittest.TestCase):
    def _run(self, reports, *, retries=1, bindings=None):
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            plan = SimpleNamespace(
                scenes=[SimpleNamespace(prompt="@char2 greets the camera.", visible_entity_counts={})],
                source="prompt_only", note="t", character_bible="", style_bible="", entity_locks=[],
            )

            def fake_render(**kwargs):
                calls.append(kwargs)
                path = out / f"clip-{len(calls)}.mp4"
                path.write_bytes(b"clip")
                return SimpleNamespace(path=str(path), render_seconds=1.0, wall_seconds=1.0, chunk_count=1,
                                       gpu="B200", detail_refined=False, render_details="fake")

            queue = list(reports)
            with ExitStack() as stack:
                stack.enter_context(patch.object(factory_service, "GENERATED_DIR", out))
                stack.enter_context(patch.object(factory_service, "ensure_minimum_free_disk"))
                stack.enter_context(patch.object(factory_service, "resolve_element_bindings", return_value=bindings if bindings is not None else [character()]))
                stack.enter_context(patch.object(factory_service, "create_prompt_only_plan", return_value=plan))
                stack.enter_context(patch.object(factory_service, "get_video_provider", return_value=SimpleNamespace(name="modal", supports_audio_retake=False)))
                stack.enter_context(patch.object(factory_service, "render_long_clip", side_effect=fake_render))
                stack.enter_context(patch.object(factory_service, "build_reference_sheet", side_effect=lambda _b, p: p))
                stack.enter_context(patch.object(factory_service, "extract_continuity_frame", side_effect=lambda _v, t: Path(t)))
                stack.enter_context(patch.object(factory_service, "measure_motion", side_effect=lambda _p: queue.pop(0)))
                stack.enter_context(patch.object(factory_service, "combine_videos", side_effect=lambda _s, t: t.write_bytes(b"c")))
                stack.enter_context(patch.object(factory_service, "prepare_delivery", side_effect=lambda *a, **k: (out / "final.mp4")))
                stack.enter_context(patch.object(factory_service, "_media_info", return_value=SimpleNamespace(
                    duration_seconds=15.0, has_audio=False, width=1280, height=720)))
                stack.enter_context(patch.object(factory_service, "estimate_gpu_cost", return_value=(0.0, 0.0, "t")))
                stack.enter_context(patch.object(factory_service, "record_generation_metric"))
                request = FactoryGenerationRequest(
                    prompt="@char2 greets the camera.", target_duration_seconds=15, scene_duration_seconds=15,
                    quality="preview", audio_mode="mute", continuity_mode="strict", continuity_qc_mode="off",
                    continuity_max_retries=retries,
                )
                result = factory_service.run_factory_generation(request, workspace_id="demo")
        return result, calls

    STILL = MotionReport(mean_diff=0.1, max_diff=0.2, frames=6, still=True)
    LIVE = MotionReport(mean_diff=4.0, max_diff=6.0, frames=6, still=False)

    def test_a_frozen_first_attempt_is_retried_with_looser_references(self):
        result, calls = self._run([self.STILL, self.LIVE])
        self.assertEqual(len(calls), 2)
        self.assertNotIn(MOTION_RETRY_NOTE, calls[0]["prompt"])
        self.assertIn(MOTION_RETRY_NOTE, calls[1]["prompt"])
        self.assertLess(calls[1]["element_reference_strength"], calls[0]["element_reference_strength"])
        self.assertEqual(result.continuity_regenerations, 1)
        self.assertFalse(any("frozen still" in note for note in result.continuity_warnings))

    def test_a_clip_that_stays_frozen_is_kept_but_flagged_unapproved(self):
        result, calls = self._run([self.STILL, self.STILL])
        self.assertEqual(len(calls), 2)
        self.assertFalse(result.continuity_qc_passed)
        self.assertTrue(any("frozen still" in note and "retained for review" in note for note in result.continuity_warnings))

    def test_with_no_retries_budget_a_frozen_clip_is_flagged_not_discarded(self):
        result, calls = self._run([self.STILL], retries=0)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result.continuity_qc_passed)

    def test_a_live_clip_is_accepted_first_time(self):
        result, calls = self._run([self.LIVE])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.continuity_regenerations, 0)

    def test_text_only_renders_are_not_measured(self):
        result, calls = self._run([], bindings=[])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
