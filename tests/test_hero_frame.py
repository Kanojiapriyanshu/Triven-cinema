"""Start frame (hero frame): compose the cast into one still, approve it, then animate that exact frame."""
import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.api.routes import factory as factory_route
from app.core.config import settings
from app.main import app
from app.services import hero_frame_service as hero
from app.services.job_service import workspace_owns_generated_file
from tests.test_cast_and_continuation import FactoryContinuationTests, binding

WORKSPACE = "a" * 32


def png_b64(size=(64, 36), color=(200, 120, 110)) -> str:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def model_reply(**extra):
    payload = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": png_b64()}}]}}]}
    payload.update(extra)
    return payload


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise hero.httpx.HTTPStatusError("error", request=None, response=self)


def real_binding(path: Path, handle="zoe", kind="character", name="Zoe"):
    item = binding(handle, kind=kind)
    return item.model_copy(update={"name": name, "primary_asset_path": str(path), "reference_asset_paths": [str(path)]})


def write_photo(directory: Path, name: str, size=(600, 800), color=(200, 150, 130)) -> Path:
    path = directory / name
    Image.new("RGB", size, color).save(path)
    return path


def write_sheet(directory: Path) -> Path:
    image = Image.new("RGB", (1280, 720), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 0, 465, 719), fill=(200, 150, 130))
    for index in range(5):
        left = 490 + index * 155
        draw.rectangle((left, 80, left + 110, 640), fill=(150, 160, 210))
    path = directory / "sheet.png"
    image.save(path)
    return path


class ModelSelectionTests(unittest.TestCase):
    def test_prefers_the_pro_image_model_and_ignores_imagen_and_non_generate_models(self):
        models = [
            {"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-9-flash-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-9-pro-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/imagen-9-image", "supportedGenerationMethods": ["predict"]},
            {"name": "models/gemini-10-pro-image", "supportedGenerationMethods": ["countTokens"]},
        ]
        self.assertEqual(hero.pick_image_model(models), "gemini-9-pro-image")

    def test_a_stable_release_beats_a_preview_and_lite_models_come_last(self):
        names = ["gemini-3-pro-image-preview", "gemini-3-pro-image", "gemini-3.1-flash-lite-image", "gemini-3.1-flash-image"]
        models = [{"name": f"models/{name}", "supportedGenerationMethods": ["generateContent"]} for name in names]
        self.assertEqual(hero.pick_image_model(models), "gemini-3-pro-image")
        models = [item for item in models if "pro" not in item["name"]]
        self.assertEqual(hero.pick_image_model(models), "gemini-3.1-flash-image")

    def test_no_image_model_returns_none(self):
        self.assertIsNone(hero.pick_image_model([{"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]}]))


class GenerateHeroFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _generate(self, bindings, reply=None, prompt="@zoe holds @phone in both hands and smiles.", ratio="16:9"):
        with patch.object(settings, "gemini_api_key", "test-key"), \
                patch.object(settings, "gemini_image_model", "test-image-model"), \
                patch.object(hero, "GENERATED_DIR", self.dir / "out"), \
                patch.object(hero.httpx, "post", return_value=FakeResponse(reply or model_reply())) as post:
            path, model = hero.generate_hero_frame(workspace_id=WORKSPACE, prompt=prompt, bindings=bindings, aspect_ratio=ratio)
        return path, model, post

    def test_builds_one_frame_from_the_cast_photos_and_the_scene_text(self):
        zoe = real_binding(write_photo(self.dir, "zoe.png"))
        phone = real_binding(write_photo(self.dir, "phone.png", (400, 800), (30, 30, 40)), "phone", "prop", "iPhone18")
        path, model, post = self._generate([zoe, phone])
        body = post.call_args.kwargs["json"]
        parts = body["contents"][0]["parts"]
        text = parts[0]["text"]
        self.assertEqual(model, "test-image-model")
        self.assertEqual(sum(1 for part in parts if "inlineData" in part), 2)
        self.assertIn("Zoe holds iPhone18 in both hands", text)
        self.assertNotIn("@", text)
        self.assertIn("five fingers", text)
        self.assertIn("no collage", text)
        self.assertEqual(body["generationConfig"]["imageConfig"]["aspectRatio"], "16:9")
        self.assertEqual(body["generationConfig"]["responseModalities"], ["IMAGE"])
        self.assertTrue(path.name.startswith(f"hero-{WORKSPACE}-") and path.suffix == ".png")
        with Image.open(path) as saved:
            self.assertEqual(saved.format, "PNG")

    def test_a_turnaround_sheet_is_sent_as_the_cropped_portrait_not_the_whole_sheet(self):
        zoe = real_binding(write_sheet(self.dir))
        _, _, post = self._generate([zoe], prompt="@zoe looks into the lens and smiles gently.")
        parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
        sent = [part for part in parts if "inlineData" in part]
        self.assertEqual(len(sent), 2, "the portrait first, then the whole sheet for clothing and proportions")
        with Image.open(BytesIO(base64.b64decode(sent[0]["inlineData"]["data"]))) as image:
            self.assertLess(image.width / image.height, 0.9, "the portrait, not the 16:9 sheet")
        with Image.open(BytesIO(base64.b64decode(sent[1]["inlineData"]["data"]))) as image:
            self.assertGreater(image.width / image.height, 1.5, "the whole sheet")
        text = parts[0]["text"]
        self.assertIn("turnaround sheet of the same person", text)
        self.assertIn("Never copy its layout", text)

    def test_requires_a_key(self):
        with patch.object(settings, "gemini_api_key", ""):
            with self.assertRaises(hero.HeroFrameUnavailable):
                hero.generate_hero_frame(workspace_id=WORKSPACE, prompt="@zoe smiles at camera.", bindings=[real_binding(write_photo(self.dir, "z.png"))])

    def test_requires_a_cast(self):
        with patch.object(settings, "gemini_api_key", "k"):
            with self.assertRaises(hero.HeroFrameError):
                hero.generate_hero_frame(workspace_id=WORKSPACE, prompt="A quiet street at dawn.", bindings=[])

    def test_a_blocked_or_empty_reply_gives_a_readable_error(self):
        zoe = real_binding(write_photo(self.dir, "zoe.png"))
        with self.assertRaisesRegex(hero.HeroFrameError, "blocked: SAFETY"):
            self._generate([zoe], reply={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})

    def _post_sequence(self, replies, models="m1,m2,m3"):
        zoe = real_binding(write_photo(self.dir, "zoe.png"))
        calls: list[str] = []

        def fake_post(url, **_kwargs):
            calls.append(url.rsplit("/", 1)[-1].split(":")[0])
            return replies[len(calls) - 1]

        listing = {"models": [{"name": f"models/{name}", "supportedGenerationMethods": ["generateContent"]} for name in models.split(",")]}
        hero._MODEL_CACHE.clear()
        with patch.object(settings, "gemini_api_key", "k"), patch.object(settings, "gemini_image_model", ""), \
                patch.object(hero, "GENERATED_DIR", self.dir / "out"), \
                patch.object(hero.httpx, "get", return_value=FakeResponse(listing)), \
                patch.object(hero.httpx, "post", side_effect=fake_post):
            try:
                path, model = hero.generate_hero_frame(workspace_id=WORKSPACE, prompt="@zoe smiles at camera.", bindings=[zoe])
            finally:
                hero._MODEL_CACHE.clear()
        return path, model, calls

    def test_a_quota_refusal_falls_back_to_the_next_image_model(self):
        quota = FakeResponse({"error": {"message": "You exceeded your current quota."}}, 429)
        _, model, calls = self._post_sequence([quota, FakeResponse(model_reply())], models="gemini-9-pro-image,gemini-9-flash-image")
        self.assertEqual(calls, ["gemini-9-pro-image", "gemini-9-flash-image"])
        self.assertEqual(model, "gemini-9-flash-image", "the model that actually made the picture is reported")

    def test_when_every_model_is_out_of_quota_the_message_explains_billing(self):
        free = FakeResponse(
            {"error": {"message": "You exceeded your current quota. For more information on this error, head to: x", "details": [
                {"violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests"}]}]}}, 429
        )
        with self.assertRaises(hero.HeroFrameError) as caught:
            self._post_sequence([free, free, free], models="a-pro-image,b-flash-image,c-flash-image")
        text = str(caught.exception)
        self.assertIn("quota exceeded", text)
        self.assertIn("free tier does not include image models", text)
        self.assertIn("turn on billing", text)
        for name in ("a-pro-image", "b-flash-image", "c-flash-image"):
            self.assertIn(name, text)
        self.assertNotIn("head to", text, "no raw Google boilerplate")

    def test_a_plain_rate_limit_suggests_waiting_not_billing(self):
        limit = FakeResponse({"error": {"message": "Resource has been exhausted (e.g. check quota)."}}, 429)
        with self.assertRaisesRegex(hero.HeroFrameError, "Wait a minute"):
            self._post_sequence([limit, limit], models="a-pro-image,b-flash-image")

    def test_a_permission_error_stops_immediately_without_trying_other_models(self):
        denied = FakeResponse({"error": {"message": "API key not valid."}}, 403)
        with self.assertRaisesRegex(hero.HeroFrameError, "HTTP 403"):
            _, _, calls = self._post_sequence([denied, FakeResponse(model_reply())], models="a-pro-image,b-flash-image")
        # a second call would have used the 200 reply; the error above proves it was never reached

    def test_a_configured_model_is_used_alone(self):
        zoe = real_binding(write_photo(self.dir, "zoe.png"))
        quota = FakeResponse({"error": {"message": "quota"}}, 429)
        with patch.object(settings, "gemini_api_key", "k"), patch.object(settings, "gemini_image_model", "only-model"), \
                patch.object(hero, "GENERATED_DIR", self.dir / "out"), \
                patch.object(hero.httpx, "post", return_value=quota) as post:
            with self.assertRaisesRegex(hero.HeroFrameError, "only-model"):
                hero.generate_hero_frame(workspace_id=WORKSPACE, prompt="@zoe smiles at camera.", bindings=[zoe])
        self.assertEqual(post.call_count, 1)

    def test_start_frames_belong_to_the_workspace_that_made_them(self):
        name = f"hero-{WORKSPACE}-abc123.png"
        self.assertTrue(workspace_owns_generated_file(WORKSPACE, name))
        self.assertFalse(workspace_owns_generated_file("b" * 32, name))


class HeroFrameRouteTests(unittest.TestCase):
    PAYLOAD = {"prompt": "@zoe holds @phone and smiles.", "aspect_ratio": "16:9", "element_bindings": []}

    def _post(self, **patches):
        zoe = binding("zoe", apply_all=False)
        with patch.object(settings, "auth_enabled", False), \
                patch.object(factory_route, "resolve_element_bindings", return_value=[zoe]), \
                patch.object(factory_route, "generate_hero_frame", **patches) as generate:
            with TestClient(app) as client:
                return client.post("/api/v1/factory/hero-frame", json=self.PAYLOAD), generate

    def test_returns_the_frame_to_approve(self):
        response, generate = self._post(return_value=(Path("hero-x-1.png"), "img-model"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["filename"], "hero-x-1.png")
        self.assertEqual(body["url"], "/media/generated/hero-x-1.png")
        self.assertEqual(body["model"], "img-model")
        self.assertEqual(generate.call_args.kwargs["aspect_ratio"], "16:9")

    def test_missing_key_is_a_clear_503(self):
        response, _ = self._post(side_effect=hero.HeroFrameUnavailable("Start frames need a Gemini API key."))
        self.assertEqual(response.status_code, 503)
        self.assertIn("Gemini API key", response.json()["detail"])

    def test_upstream_failure_is_a_502_with_the_reason(self):
        response, _ = self._post(side_effect=hero.HeroFrameError("The image model returned HTTP 429."))
        self.assertEqual(response.status_code, 502)


class UploadedStartFrameTests(unittest.TestCase):
    def _png(self, size=(640, 360)) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", size, (120, 90, 80)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_a_valid_picture_becomes_a_start_frame_owned_by_the_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(hero, "GENERATED_DIR", Path(tmp)):
            path = hero.save_uploaded_hero_frame(WORKSPACE, self._png())
            self.assertTrue(path.name.startswith(f"hero-{WORKSPACE}-"))
            self.assertTrue(workspace_owns_generated_file(WORKSPACE, path.name))
            with Image.open(path) as saved:
                self.assertEqual(saved.size, (640, 360))

    def test_bad_uploads_are_rejected_with_a_readable_reason(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(hero, "GENERATED_DIR", Path(tmp)):
            with self.assertRaisesRegex(hero.HeroFrameError, "empty"):
                hero.save_uploaded_hero_frame(WORKSPACE, b"")
            with self.assertRaisesRegex(hero.HeroFrameError, "not a valid"):
                hero.save_uploaded_hero_frame(WORKSPACE, b"not an image at all")
            with self.assertRaisesRegex(hero.HeroFrameError, "256 pixels"):
                hero.save_uploaded_hero_frame(WORKSPACE, self._png((100, 100)))
            with self.assertRaisesRegex(hero.HeroFrameError, "15 MB"):
                hero.save_uploaded_hero_frame(WORKSPACE, b"x" * (hero.MAX_UPLOAD_BYTES + 1))

    def test_the_upload_route_returns_the_frame_and_rejects_non_images(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings, "auth_enabled", False), \
                patch.object(hero, "GENERATED_DIR", Path(tmp)):
            with TestClient(app) as client:
                good = client.post("/api/v1/factory/hero-frame/upload", files={"file": ("frame.png", self._png(), "image/png")})
                bad = client.post("/api/v1/factory/hero-frame/upload", files={"file": ("frame.txt", b"hello", "text/plain")})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.json()["model"], "uploaded")
        self.assertTrue(good.json()["filename"].startswith("hero-"))
        self.assertEqual(bad.status_code, 400)


class HeroModeFactoryTests(unittest.TestCase):
    """Animating an approved start frame: no reference sheet, exact first frame, names instead of @handles."""

    def _run(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / f"hero-{WORKSPACE}-abc.png"
            Image.new("RGB", (64, 36)).save(frame)
            helper = FactoryContinuationTests("test_start_frame_element_opens_only_the_first_scene")
            overrides = {"hero_frame_filename": frame.name, **kwargs.pop("request_overrides", {})}
            return frame, *helper._run(request_overrides=overrides, continue_frame=frame, **kwargs)

    def test_the_start_frame_is_frame_zero_and_no_reference_sheet_is_built(self):
        zoe = binding("zoe", apply_all=True)
        phone = binding("phone", kind="prop", apply_all=True)
        frame, result, calls = self._run(
            bindings=[zoe, phone], scene_prompts=["@zoe holds @phone and smiles."], request_overrides={"target_duration_seconds": 15}
        )
        self.assertEqual(calls[0]["reference_image_path"], str(frame))
        self.assertIsNone(calls[0]["element_reference_sheet_path"])
        self.assertEqual(calls[0]["reference_strength"], 1.0)
        self.assertIn("OPENING FRAME", calls[0]["prompt"])
        self.assertIn("Zoe holds Phone and smiles", calls[0]["prompt"])
        self.assertNotIn("@zoe", calls[0]["prompt"])
        self.assertEqual(result.elements_used, ["@phone", "@zoe"])
        self.assertIn("start_frame_image", result.element_reference_mode)

    def test_later_scenes_continue_from_the_previous_frame_without_repeating_the_opening_block(self):
        frame, _, calls = self._run(bindings=[binding("zoe", apply_all=True)], scene_prompts=["@zoe greets.", "@zoe keeps talking."])
        self.assertEqual(len(calls), 2)
        self.assertNotIn("OPENING FRAME", calls[1]["prompt"])
        self.assertIn("Zoe keeps talking", calls[1]["prompt"])
        self.assertNotEqual(calls[1]["reference_image_path"], str(frame))
        self.assertIsNone(calls[1]["element_reference_sheet_path"])

    def test_two_start_frame_elements_do_not_conflict_when_a_start_frame_is_used(self):
        zoe = binding("zoe", mode="start_frame", apply_all=True)
        phone = binding("phone", mode="start_frame", kind="prop", apply_all=True)
        _, _, calls = self._run(bindings=[zoe, phone], scene_prompts=["@zoe holds @phone."])
        self.assertEqual(len(calls), 1)

    def test_a_missing_start_frame_fails_before_any_gpu_work(self):
        helper = FactoryContinuationTests("test_start_frame_element_opens_only_the_first_scene")
        with self.assertRaisesRegex(ValueError, "no longer available"):
            helper._run(bindings=[], request_overrides={"hero_frame_filename": "gone.png"})

    def test_a_start_frame_and_a_continuation_cannot_be_combined(self):
        from pydantic import ValidationError
        from app.schemas.factory import FactoryGenerationRequest

        with self.assertRaises(ValidationError):
            FactoryGenerationRequest(
                prompt="@zoe greets the camera.", hero_frame_filename="hero-x-1.png", start_frame_filename="continuity-x.png"
            )


if __name__ == "__main__":
    unittest.main()
