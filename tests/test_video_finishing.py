"""The finishing pass: steady exposure (deflicker) and tamed highlight bloom.

Unit tests check the ffmpeg command we build; the integration test actually runs
ffmpeg on a synthetic pulsing/bloomed clip and proves the temporal luminance
variance drops and the audio survives. It skips when ffmpeg is unavailable.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inference.providers import finishing


class FinishCommandTests(unittest.TestCase):
    def test_default_command_stabilises_exposure_and_tames_highlights(self):
        command = finishing.build_finish_command(
            input_path=Path("/tmp/in.mp4"), output_path=Path("/tmp/out.mp4")
        )
        joined = " ".join(command)
        self.assertIn("deflicker=mode=am:size=31", joined)
        self.assertIn("curves=all=", joined)
        self.assertIn("format=yuv420p", joined)
        # Audio is stream-copied untouched; the picture is re-encoded.
        self.assertIn("-c:a", command)
        self.assertEqual(command[command.index("-c:a") + 1], "copy")
        self.assertIn("0:a?", command)
        self.assertIn("-c:v", command)
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")

    def test_deflicker_is_omitted_when_the_window_is_too_small(self):
        filters = finishing.build_video_filters(deflicker_window=1, rolloff=0.1)
        self.assertNotIn("deflicker", filters)
        self.assertIn("curves", filters)

    def test_highlight_rolloff_can_be_switched_off(self):
        filters = finishing.build_video_filters(deflicker_window=15, rolloff=0.0)
        self.assertIn("deflicker", filters)
        self.assertNotIn("curves", filters)

    def test_the_highlight_curve_protects_mid_tones_and_pulls_down_the_peak(self):
        curve = finishing._highlight_curve(0.10)
        points = dict(pair.split("/") for pair in re.findall(r"[\d.]+/[\d.]+", curve))
        self.assertEqual(points["0.6"], "0.6")          # mid-tones (skin) untouched
        self.assertLess(float(points["1"]), 1.0)        # peak highlight pulled down
        self.assertLessEqual(float(points["0.8"]), 0.8)  # knee compresses the highlights
        # Monotonically non-decreasing so no tonal inversion.
        xs = sorted(float(x) for x in points)
        ys = [float(points[f"{x:g}"]) for x in xs]
        self.assertEqual(ys, sorted(ys))

    def test_env_toggles_are_respected(self):
        with patch.dict("os.environ", {"TRIVEN_VIDEO_FINISHING": "false"}, clear=False):
            self.assertFalse(finishing.finishing_enabled())
        with patch.dict("os.environ", {"TRIVEN_VIDEO_FINISHING": "true"}, clear=False):
            self.assertTrue(finishing.finishing_enabled())
        with patch.dict("os.environ", {"TRIVEN_VIDEO_DEFLICKER_SIZE": "30"}, clear=False):
            self.assertEqual(finishing.deflicker_size(), 30)
        with patch.dict("os.environ", {"TRIVEN_VIDEO_HIGHLIGHT_ROLLOFF": "0.25"}, clear=False):
            self.assertAlmostEqual(finishing.highlight_rolloff(), 0.25)
        # Out-of-range roll-off is clamped so the curve stays sane.
        with patch.dict("os.environ", {"TRIVEN_VIDEO_HIGHLIGHT_ROLLOFF": "9"}, clear=False):
            self.assertLessEqual(finishing.highlight_rolloff(), 0.4)

    def test_finishing_returns_none_when_disabled(self):
        with patch.dict("os.environ", {"TRIVEN_VIDEO_FINISHING": "false"}, clear=False):
            self.assertIsNone(finishing.finish_video(Path("/tmp/does-not-matter.mp4")))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for the finishing integration test")
class FinishIntegrationTests(unittest.TestCase):
    def _luma_series(self, path: Path) -> list[float]:
        proc = subprocess.run(
            ["ffmpeg", "-i", str(path), "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        return [float(m) for m in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", proc.stdout + proc.stderr)]

    @staticmethod
    def _stddev(vals: list[float]) -> float:
        mean = sum(vals) / len(vals)
        return (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5

    def test_pulsing_and_bloom_are_reduced_and_audio_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "pulsing.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=0x808080:s=320x240:r=24:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-vf", "drawbox=x=120:y=90:w=80:h=60:color=white:t=fill,"
                           "eq=brightness=0.18*sin(2*PI*1.5*t):eval=frame,format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-c:a", "aac", "-shortest", str(src),
                ],
                check=True,
            )
            finished = finishing.finish_video(src)
            self.assertIsNotNone(finished)
            before, after = self._luma_series(src), self._luma_series(finished)
            self.assertEqual(len(after), len(before))               # no dropped frames
            self.assertLess(self._stddev(after), self._stddev(before) * 0.6)  # pulsing calmed
            self.assertLessEqual(max(after), max(before))           # bloom not increased
            has_audio = subprocess.run(
                ["ffprobe", "-i", str(finished), "-select_streams", "a", "-show_streams", "-of", "csv"],
                capture_output=True, text=True,
            ).stdout.strip()
            self.assertTrue(has_audio)


if __name__ == "__main__":
    unittest.main()
