import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.video_combiner import extract_continuity_frame, extract_last_frame


ROOT = Path(__file__).resolve().parents[1]


class FFmpegCompatibilityTests(unittest.TestCase):
    def test_extract_last_frame_does_not_use_removed_vsync_option(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_path = root / "scene.mp4"
            output_path = root / "continuity.png"
            input_path.write_bytes(b"video")
            commands: list[list[str]] = []

            def fake_run(command: list[str]) -> None:
                commands.append(command)
                Path(command[-1]).write_bytes(b"png" + bytes([len(commands)]))

            with patch(
                "app.services.video_combiner._run_ffmpeg",
                side_effect=fake_run,
            ):
                result = extract_last_frame(input_path, output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(commands)
            for command in commands:
                self.assertNotIn("-vsync", command)
                self.assertEqual(command[-2], "1")

    def test_continuity_extractor_samples_multiple_near_end_frames(self):
        source = (ROOT / "services/api/app/services/video_combiner.py").read_text()
        self.assertNotIn('"-vsync"', source)
        self.assertIn("def extract_continuity_frame", source)
        self.assertIn("0.35, 0.20, 0.08", source)

    def test_continuity_frame_function_is_publicly_callable(self):
        self.assertTrue(callable(extract_continuity_frame))


if __name__ == "__main__":
    unittest.main()
