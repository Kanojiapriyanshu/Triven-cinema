import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.video_combiner import extract_last_frame


class FFmpegCompatibilityTests(unittest.TestCase):
    def test_extract_last_frame_does_not_use_removed_vsync_option(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_path = root / "scene.mp4"
            output_path = root / "continuity.png"
            input_path.write_bytes(b"video")
            captured: dict[str, list[str]] = {}

            def fake_run(command: list[str]) -> None:
                captured["command"] = command
                output_path.write_bytes(b"png")

            with patch(
                "app.services.video_combiner._run_ffmpeg",
                side_effect=fake_run,
            ):
                result = extract_last_frame(input_path, output_path)

            self.assertEqual(result, output_path)
            self.assertNotIn("-vsync", captured["command"])
            self.assertEqual(captured["command"][-1], str(output_path))


if __name__ == "__main__":
    unittest.main()
