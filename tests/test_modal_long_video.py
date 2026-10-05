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


if __name__ == "__main__":
    unittest.main()
