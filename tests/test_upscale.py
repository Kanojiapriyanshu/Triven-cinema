"""Draft -> Full HD: the same video with more detail, not a new generation."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routes import factory as factory_route
from app.core.config import settings
from app.main import app
from app.schemas.upscale import UpscaleRequest
from app.services import upscale_service
from inference.providers.base import VideoProvider

ROOT = Path(__file__).resolve().parents[1]
MODAL_DIR = ROOT / "modal"
if str(MODAL_DIR) not in sys.path:
    sys.path.append(str(MODAL_DIR))
spec = importlib.util.spec_from_file_location("triven_ltx_worker_upscale", MODAL_DIR / "ltx_worker.py")
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerCommandTests(unittest.TestCase):
    def test_the_draft_is_scaled_to_the_final_canvas_with_picture_only(self):
        command = worker.build_prescale_command(
            input_path=Path("/tmp/draft.mp4"), output_path=Path("/tmp/up.mp4"), width=1920, height=1088
        )
        joined = " ".join(command)
        self.assertIn("scale=1920:1088:flags=lanczos", joined)
        self.assertIn("fps=24", joined)
        self.assertIn("-an", command)
        self.assertEqual(command[0], "ffmpeg")

    def test_upscale_refines_the_scaled_draft_then_restores_the_drafts_own_audio(self):
        calls: list[tuple] = []
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "draft.mp4", Path(tmp) / "final.mp4"
            source.write_bytes(b"draft")

            def fake_run(command, **_kwargs):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"prescaled")
                    calls.append(("prescale", command))
                return SimpleNamespace(returncode=0, stderr="")

            def fake_ltx(command):
                calls.append(("refine", command))
                Path(command[command.index("--output-path") + 1]).write_bytes(b"refined")

            def fake_audio(*, refined_video_path, source_video_path, output_path):
                calls.append(("audio", refined_video_path, source_video_path))
                output_path.write_bytes(b"final")

            with patch.object(worker.subprocess, "run", side_effect=fake_run), \
                    patch.object(worker, "run_ltx_command", side_effect=fake_ltx), \
                    patch.object(worker, "preserve_source_audio", side_effect=fake_audio):
                worker.upscale_draft_video(
                    source_path=source, output_path=output, width=1920, height=1088, duration_seconds=15.04, seed=7
                )

            self.assertEqual([item[0] for item in calls], ["prescale", "refine", "audio"])
            refine = calls[1][1]
            self.assertIn("ltx_pipelines.ic_lora", refine)
            conditioning = refine[refine.index("--video-conditioning") + 1]
            self.assertTrue(conditioning.endswith("-prescaled.mp4"), "the refine pass must be conditioned on the Draft")
            self.assertEqual(refine[refine.index("--width") + 1], "1920")
            self.assertEqual(refine[refine.index("--height") + 1], "1088")
            self.assertEqual(refine[refine.index("--num-frames") + 1], str(worker.frames_for_duration(15.04)))
            self.assertEqual(calls[2][2], source, "audio comes from the approved Draft, not a new generation")
            self.assertEqual(output.read_bytes(), b"final")
            self.assertFalse(any(path.name.endswith(("-prescaled.mp4", "-refined.mp4")) for path in Path(tmp).iterdir()))

    def test_a_failed_prescale_stops_before_any_gpu_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "draft.mp4", Path(tmp) / "final.mp4"
            source.write_bytes(b"draft")
            with patch.object(worker.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="bad input")), \
                    patch.object(worker, "run_ltx_command") as ltx:
                with self.assertRaisesRegex(RuntimeError, "prepare the Draft"):
                    worker.upscale_draft_video(
                        source_path=source, output_path=output, width=1920, height=1088, duration_seconds=15, seed=1
                    )
            ltx.assert_not_called()


class FakeProvider:
    name = "modal-ltx-2.5"
    supports_upscale = True

    def __init__(self, directory: Path):
        self.directory, self.calls = directory, []

    def upscale(self, **kwargs):
        self.calls.append(kwargs)
        path = self.directory / "raw-upscale.mp4"
        path.write_bytes(b"up")
        return SimpleNamespace(path=str(path), render_seconds=250.0, wall_seconds=260.0, gpu="B200", provider=self.name)


class UpscaleServiceTests(unittest.TestCase):
    def _run(self, *, width=1024, height=576, duration=15.04, provider_supports=True):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            draft = out / "draft.mp4"
            draft.write_bytes(b"draft")
            provider = FakeProvider(out)
            provider.supports_upscale = provider_supports
            final = out / "upscale-final.mp4"

            def fake_probe(path):
                if Path(path) == final:
                    return {"width": 1920, "height": 1080, "duration_seconds": duration, "has_audio": True}
                return {"width": width, "height": height, "duration_seconds": duration, "has_audio": True}

            def fake_delivery(source, **kwargs):
                final.write_bytes(b"final")
                self.delivery_kwargs = kwargs
                return final

            with patch.object(upscale_service, "ensure_minimum_free_disk"), \
                    patch.object(upscale_service, "resolve_generated_asset", return_value=draft), \
                    patch.object(upscale_service, "probe_media", side_effect=fake_probe), \
                    patch.object(upscale_service, "get_video_provider", return_value=provider), \
                    patch.object(upscale_service, "prepare_delivery", side_effect=fake_delivery), \
                    patch.object(upscale_service, "estimate_gpu_cost", return_value=(0.4, 1.6, "estimate")), \
                    patch.object(upscale_service, "record_generation_metric"):
                response = upscale_service.run_upscale(UpscaleRequest(source_filename="draft.mp4"), workspace_id="w")
            return response, provider

    def test_sends_the_draft_to_the_worker_at_the_full_hd_canvas(self):
        response, provider = self._run()
        call = provider.calls[0]
        self.assertEqual((call["width"], call["height"]), (1920, 1088))
        self.assertAlmostEqual(call["duration_seconds"], 15.04)
        self.assertEqual(response.final_filename, "upscale-final.mp4")
        self.assertEqual((response.width, response.height), (1920, 1080))
        self.assertTrue(response.has_audio)
        self.assertEqual(self.delivery_kwargs["audio_mode"], "native", "the Draft's audio must not be re-mastered")
        self.assertIn("same", response.quality_note)

    def test_portrait_drafts_use_the_portrait_canvas(self):
        _, provider = self._run(width=576, height=1024)
        self.assertEqual((provider.calls[0]["width"], provider.calls[0]["height"]), (1088, 1920))

    def test_a_video_that_is_already_full_hd_is_refused(self):
        with self.assertRaisesRegex(ValueError, "already Full HD"):
            self._run(width=1920, height=1080)

    def test_a_clip_longer_than_the_validated_1080p_ceiling_is_refused(self):
        with self.assertRaisesRegex(ValueError, "limited to"):
            self._run(duration=45.0)

    def test_a_provider_that_cannot_upscale_is_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot upscale"):
            self._run(provider_supports=False)

    def test_the_base_provider_does_not_pretend_to_upscale(self):
        with self.assertRaises(NotImplementedError):
            VideoProvider.upscale(SimpleNamespace(name="x"), video_path="a", width=1, height=1, duration_seconds=1, seed=1)


class UpscaleRouteTests(unittest.TestCase):
    PAYLOAD = {"source_filename": "factory-mastered-abc.mp4"}

    def _post(self, *, owns=True, tools_error=None, inspect=(Path("d.mp4"), {}, 15.0)):
        with patch.object(settings, "auth_enabled", False), \
                patch.object(factory_route, "media_tools_error", return_value=tools_error), \
                patch.object(factory_route, "workspace_owns_generated_file", return_value=owns), \
                patch.object(factory_route, "inspect_draft", return_value=inspect), \
                patch.object(factory_route, "submit_job", return_value="job-u") as submit:
            with TestClient(app) as client:
                return client.post("/api/v1/factory/upscale", json=self.PAYLOAD), submit

    def test_queues_an_upscale_job_for_an_owned_draft(self):
        response, submit = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(submit.call_args.args[0], "upscale")
        self.assertEqual(submit.call_args.args[1]["source_filename"], self.PAYLOAD["source_filename"])

    def test_another_workspaces_video_is_not_found(self):
        response, submit = self._post(owns=False)
        self.assertEqual(response.status_code, 404)
        submit.assert_not_called()

    def test_missing_ffmpeg_tools_block_the_job_before_any_gpu_spend(self):
        response, submit = self._post(tools_error="ffprobe not found on PATH.")
        self.assertEqual(response.status_code, 503)
        submit.assert_not_called()

    def test_an_unusable_video_is_a_clear_400(self):
        with patch.object(settings, "auth_enabled", False), \
                patch.object(factory_route, "media_tools_error", return_value=None), \
                patch.object(factory_route, "workspace_owns_generated_file", return_value=True), \
                patch.object(factory_route, "inspect_draft", side_effect=ValueError("no longer available")), \
                patch.object(factory_route, "submit_job") as submit:
            with TestClient(app) as client:
                response = client.post("/api/v1/factory/upscale", json=self.PAYLOAD)
        self.assertEqual(response.status_code, 400)
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
