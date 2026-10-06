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

    def test_short_clip_remains_single_window(self):
        command = ltx_worker.build_command(
            prompt="A five second cinematic shot.",
            output_path=Path("/tmp/out.mp4"),
            width=1024,
            height=576,
            duration_seconds=5,
            seed=42,
            decoder="conv",
        )
        self.assertNotIn("--chunk-pixel-frames", command)
        self.assertEqual(ltx_worker.temporal_chunk_count(5), 1)

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


if __name__ == "__main__":
    unittest.main()
