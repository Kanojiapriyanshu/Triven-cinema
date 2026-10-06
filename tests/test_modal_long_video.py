import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODAL_DIR = ROOT / "modal"
if str(MODAL_DIR) not in sys.path:
    sys.path.append(str(MODAL_DIR))

spec = importlib.util.spec_from_file_location("triven_ltx_worker_long", MODAL_DIR / "ltx_worker.py")
assert spec and spec.loader
ltx_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ltx_worker)


class ModalLongVideoTests(unittest.TestCase):
    def test_thirty_second_clip_uses_native_temporal_windowing(self):
        command = ltx_worker.build_command(
            prompt="A continuous cinematic tracking shot with synchronized natural audio.",
            output_path=Path("/tmp/out.mp4"),
            width=1024,
            height=576,
            duration_seconds=30,
            seed=42,
            decoder="conv",
        )
        self.assertIn("--chunk-pixel-frames", command)
        self.assertIn("--chunk-carry-frames", command)
        self.assertNotIn("--chunk-blend-frames", command)
        self.assertGreater(ltx_worker.temporal_chunk_count(30), 1)
        self.assertEqual(ltx_worker.LONG_VIDEO_PIXEL_FRAMES, 97)

    def test_twenty_second_distilled_clip_remains_single_window(self):
        command = ltx_worker.build_command(
            prompt="A twenty second continuous cinematic shot.",
            output_path=Path("/tmp/out.mp4"),
            width=1024,
            height=576,
            duration_seconds=20,
            seed=42,
            decoder="conv",
        )
        self.assertNotIn("--chunk-pixel-frames", command)
        self.assertEqual(ltx_worker.temporal_chunk_count(20), 1)
        frames_index = command.index("--num-frames") + 1
        self.assertEqual(command[frames_index], "481")

    def test_dfr_uses_production_pipeline_detailing_lora_and_diffusion_vae(self):
        command = ltx_worker.build_command(
            prompt="Radha hears the flute beside the Yamuna.",
            output_path=Path("/tmp/out.mp4"),
            width=1024,
            height=576,
            duration_seconds=8,
            seed=42,
            decoder="conv",
            render_mode="dfr",
        )
        joined = " ".join(command)
        self.assertIn("ltx_pipelines.dfr_pipeline", command)
        self.assertIn("--detailing-lora", command)
        self.assertIn("ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors", joined)
        self.assertIn("ltx-2.5-video-vae-bf16.safetensors", joined)
        self.assertNotIn("--chunk-pixel-frames", command)

    def test_dfr_thirty_second_1080p_is_one_pipeline_call_without_chunk_flags(self):
        command = ltx_worker.build_command(
            prompt="One continuous thirty second cinematic shot with no artificial chunk cuts.",
            output_path=Path("/tmp/out.mp4"),
            width=1920,
            height=1088,
            duration_seconds=30,
            seed=42,
            decoder="diffusion",
            render_mode="dfr",
        )
        self.assertIn("ltx_pipelines.dfr_pipeline", command)
        self.assertNotIn("--chunk-pixel-frames", command)
        self.assertNotIn("--chunk-carry-frames", command)
        frames_index = command.index("--num-frames") + 1
        self.assertEqual(command[frames_index], "721")

    def test_ingredients_uses_ic_lora_and_can_compose_previous_frame(self):
        command = ltx_worker.build_command(
            prompt="Reference sheet: Radha and Krishna. Generated video: Radha approaches Krishna.",
            output_path=Path("/tmp/out.mp4"),
            width=1024,
            height=576,
            duration_seconds=15,
            seed=42,
            decoder="conv",
            render_mode="dfr",
            reference_image_path=Path("/tmp/previous.png"),
            reference_strength=0.85,
            element_reference_video_path=Path("/tmp/reference.mp4"),
            element_reference_strength=1.0,
        )
        joined = " ".join(command)
        self.assertIn("ltx_pipelines.ic_lora", command)
        self.assertIn("--video-conditioning", command)
        self.assertIn("--lora", command)
        self.assertIn("ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors", joined)
        self.assertIn("--image", command)
        self.assertNotIn("--detailing-lora", command)

    def test_ingredients_rejects_thirty_second_identity_scene(self):
        with self.assertRaises(ValueError):
            ltx_worker.build_command(
                prompt="Reference sheet: Radha. Generated video: one long shot.",
                output_path=Path("/tmp/out.mp4"),
                width=1920,
                height=1088,
                duration_seconds=30,
                seed=42,
                decoder="conv",
                render_mode="dfr",
                element_reference_video_path=Path("/tmp/reference.mp4"),
            )

    def test_dfr_rejects_more_than_thirty_seconds_single_pass(self):
        with self.assertRaises(ValueError):
            ltx_worker.build_command(
                prompt="An excessively long single-pass shot.",
                output_path=Path("/tmp/out.mp4"),
                width=1920,
                height=1088,
                duration_seconds=31,
                seed=42,
                decoder="diffusion",
                render_mode="dfr",
            )


if __name__ == "__main__":
    unittest.main()
