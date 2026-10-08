"""Cast resolution and shot-to-shot continuity regressions."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routes import factory as factory_route
from app.core.config import settings
from app.main import app
from app.schemas.elements import ResolvedElementBinding
from app.schemas.factory import FactoryGenerationRequest
from app.services import factory_service
from app.services.continuity_service import CONTINUATION_ANCHOR_NOTE
from app.services.element_service import (
    park_tag_only_characters,
    parked_character_warning,
    split_trailing_tags,
)

STILL = str(Path(tempfile.gettempdir()) / "elements-char1.png")

# The shape of a real creator prompt: one speaker, then two reference tags appended at the end.
PRESENTER_PROMPT = (
    "Live-action footage continuing the exact shot of @char1, filmed as one continuous shot. "
    "@char1 is a real young woman in her mid-twenties and she says: \"Okay, let's be honest.\" "
    "The only sound is her voice, over a very quiet room tone. @ijustine @radha"
)


def binding(handle: str, element_type: str = "character", **overrides) -> ResolvedElementBinding:
    values = dict(
        element_id=f"el_{handle}",
        version_id=f"ev_{handle}",
        handle=handle,
        name=handle.title(),
        type=element_type,
        description="",
        reference_mode="identity",
        wardrobe_policy="prompt",
        strength=1.0,
        apply_to_all_scenes=True,
        primary_asset_path=f"/tmp/{handle}.png",
        primary_asset_url=f"/assets/{handle}.png",
    )
    values.update(overrides)
    return ResolvedElementBinding(**values)


class TrailingTagTests(unittest.TestCase):
    def test_trailing_run_is_split_from_the_story(self):
        story, tags = split_trailing_tags(PRESENTER_PROMPT)
        self.assertEqual(tags, ["ijustine", "radha"])
        self.assertTrue(story.rstrip().endswith("room tone."))
        self.assertNotIn("@ijustine", story)

    def test_mention_that_ends_a_sentence_is_narrative(self):
        story, tags = split_trailing_tags("She slowly walks over to @Mira")
        self.assertEqual(tags, [])
        self.assertIn("@Mira", story)

    def test_tag_line_after_newline_is_a_tag_run(self):
        _, tags = split_trailing_tags("Mira waves at the camera\n@Mira @Studio")
        self.assertEqual(tags, ["Mira", "Studio"])


class ParkTagOnlyCharactersTests(unittest.TestCase):
    def test_extra_character_tags_leave_the_identity_sheet(self):
        kept, parked = park_tag_only_characters(
            PRESENTER_PROMPT, [binding("char1"), binding("ijustine"), binding("radha")]
        )
        self.assertEqual([item.handle for item in kept], ["char1"])
        self.assertEqual([item.handle for item in parked], ["ijustine", "radha"])
        self.assertIn("@ijustine, @radha are only tagged", parked_character_warning(parked))

    def test_creator_can_force_a_tagged_character_into_the_shot(self):
        kept, parked = park_tag_only_characters(
            PRESENTER_PROMPT,
            [binding("char1"), binding("ijustine", cast_role="cast"), binding("radha")],
        )
        self.assertEqual([item.handle for item in kept], ["char1", "ijustine"])
        self.assertEqual([item.handle for item in parked], ["radha"])

    def test_nothing_is_parked_without_a_narrative_character(self):
        kept, parked = park_tag_only_characters(
            "A quiet street at dawn. @mira @leo", [binding("mira"), binding("leo")]
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual(parked, [])

    def test_props_and_locations_are_never_parked(self):
        kept, parked = park_tag_only_characters(
            "@char1 sips tea and smiles. @Studio @Mug",
            [binding("char1"), binding("Studio", "location"), binding("Mug", "prop")],
        )
        self.assertEqual(len(kept), 3)
        self.assertEqual(parked, [])

    def test_character_described_in_the_story_is_kept_even_if_also_tagged(self):
        kept, parked = park_tag_only_characters(
            "@mira and @leo talk by the window. @leo", [binding("mira"), binding("leo")]
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual(parked, [])


class FactoryContinuationTests(unittest.TestCase):
    def _run(self, *, bindings, request_overrides=None, scene_prompts=None, continue_frame=None):
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            scene_prompts = scene_prompts or ["@char1 greets the camera.", "@char1 keeps talking."]
            plan = SimpleNamespace(
                scenes=[SimpleNamespace(prompt=text, visible_entity_counts={}) for text in scene_prompts],
                source="prompt_only", note="test", character_bible="", style_bible="", entity_locks=[],
            )
            provider = SimpleNamespace(name="modal", supports_audio_retake=False)

            def fake_render(**kwargs):
                calls.append(kwargs)
                path = out / f"scene-{len(calls)}.mp4"
                path.write_bytes(b"clip")
                return SimpleNamespace(
                    path=str(path), render_seconds=1.0, wall_seconds=1.0, chunk_count=1,
                    gpu="B200", detail_refined=False, render_details="fake",
                )

            def fake_extract(_video, target):
                Path(target).write_bytes(b"png")
                return Path(target)

            def fake_delivery(*_a, **_k):
                final = out / "final.mp4"
                final.write_bytes(b"final")
                return final

            def fake_resolve_generated(name, **_k):
                if continue_frame is None:
                    raise FileNotFoundError(name)
                return continue_frame

            with ExitStack() as stack:
                stack.enter_context(patch.object(factory_service, "GENERATED_DIR", out))
                stack.enter_context(patch.object(factory_service, "ensure_minimum_free_disk"))
                stack.enter_context(patch.object(factory_service, "resolve_element_bindings", return_value=bindings))
                stack.enter_context(patch.object(factory_service, "create_prompt_only_plan", return_value=plan))
                stack.enter_context(patch.object(factory_service, "get_video_provider", return_value=provider))
                stack.enter_context(patch.object(factory_service, "render_long_clip", side_effect=fake_render))
                stack.enter_context(patch.object(factory_service, "extract_continuity_frame", side_effect=fake_extract))
                stack.enter_context(patch.object(factory_service, "build_reference_sheet", side_effect=lambda _b, path: path))
                stack.enter_context(patch.object(factory_service, "resolve_generated_asset", side_effect=fake_resolve_generated))
                stack.enter_context(patch.object(factory_service, "combine_videos", side_effect=lambda _s, t: t.write_bytes(b"c")))
                stack.enter_context(patch.object(factory_service, "prepare_delivery", side_effect=fake_delivery))
                stack.enter_context(patch.object(factory_service, "_media_info", return_value=SimpleNamespace(
                    duration_seconds=30.0, has_audio=False, width=1280, height=720)))
                stack.enter_context(patch.object(factory_service, "estimate_gpu_cost", return_value=(0.0, 0.0, "test")))
                stack.enter_context(patch.object(factory_service, "record_generation_metric"))

                fields = dict(
                    prompt="@char1 greets the camera. Then @char1 keeps talking.",
                    target_duration_seconds=30,
                    scene_duration_seconds=15,
                    quality="preview",
                    audio_mode="mute",
                    continuity_mode="strict",
                    continuity_qc_mode="off",
                    continuity_max_retries=0,
                )
                fields.update(request_overrides or {})
                request = FactoryGenerationRequest(**fields)
                result = factory_service.run_factory_generation(request, workspace_id="demo")
        return result, calls

    def test_start_frame_element_opens_only_the_first_scene(self):
        still = binding("char1", reference_mode="start_frame", primary_asset_path=STILL)
        result, calls = self._run(bindings=[still])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["reference_image_path"], STILL)
        # Scene 2 must continue from scene 1's last frame, not snap back to the still.
        second = calls[1]["reference_image_path"]
        self.assertIsNotNone(second)
        self.assertNotEqual(second, STILL)
        self.assertIn(".factory-continuity-", Path(second).name)

    def test_continue_frame_opens_scene_one_and_is_kept_for_the_next_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path(tmp) / "continuity-old-final.png"
            previous.write_bytes(b"png")
            still = binding("char1", reference_mode="start_frame", primary_asset_path=STILL)
            result, calls = self._run(
                bindings=[still],
                request_overrides={"start_frame_filename": previous.name},
                continue_frame=previous,
            )
            self.assertEqual(calls[0]["reference_image_path"], str(previous))
            self.assertIn(CONTINUATION_ANCHOR_NOTE, calls[0]["prompt"])
            self.assertTrue(previous.exists(), "the creator's earlier frame must not be deleted")
            self.assertTrue(any("previous video's last frame" in note for note in result.continuity_warnings))
            # The still is consumed by the continuation and must not reappear in scene 2.
            self.assertNotEqual(calls[1]["reference_image_path"], STILL)
            self.assertTrue(result.continuity_frame_filename.startswith("continuity-"))
            self.assertTrue(result.continuity_frame_url.endswith(result.continuity_frame_filename))

    def test_missing_continue_frame_fails_before_any_gpu_work(self):
        with self.assertRaisesRegex(ValueError, "no longer available"):
            self._run(bindings=[], request_overrides={"start_frame_filename": "gone.png"})

    def test_continue_frame_requires_strict_continuity(self):
        with self.assertRaisesRegex(ValueError, "requires Strict continuity"):
            self._run(
                bindings=[],
                request_overrides={"start_frame_filename": "x.png", "continuity_mode": "balanced"},
            )

    def test_trailing_character_tags_do_not_reach_the_render(self):
        bindings = [binding("char1"), binding("ijustine"), binding("radha")]
        with patch.object(factory_service, "compile_element_prompt", side_effect=lambda p, items: p) as compile_prompt:
            result, calls = self._run(
                bindings=bindings,
                scene_prompts=["@char1 greets the camera.", "@char1 keeps talking. @ijustine @radha"],
                request_overrides={"prompt": PRESENTER_PROMPT},
            )
        for call in compile_prompt.call_args_list:
            self.assertEqual([item.handle for item in call.args[1]], ["char1"])
        self.assertEqual(result.elements_used, ["@char1"])
        self.assertTrue(any("only tagged after the last sentence" in note for note in result.continuity_warnings))


class ContinueSceneRouteTests(unittest.TestCase):
    PAYLOAD = {
        "prompt": "Same continued scene with @char1 speaking to camera.",
        "target_duration_seconds": 15,
        "scene_duration_seconds": 15,
        "quality": "preview",
        "start_frame_filename": "continuity-factory-abc-final.png",
    }

    def _post(self, *, owns=True, tools_error=None, submit_result="job123"):
        with patch.object(settings, "auth_enabled", False),                 patch.object(factory_route, "media_tools_error", return_value=tools_error),                 patch.object(factory_route, "workspace_owns_generated_file", return_value=owns),                 patch.object(factory_route, "submit_job", return_value=submit_result) as submit:
            with TestClient(app) as client:
                response = client.post("/api/v1/factory/jobs", json=self.PAYLOAD)
        return response, submit

    def test_continuing_from_a_frame_the_workspace_does_not_own_is_rejected(self):
        response, submit = self._post(owns=False)
        self.assertEqual(response.status_code, 404)
        submit.assert_not_called()

    def test_continuing_from_an_owned_frame_queues_the_job(self):
        response, submit = self._post(owns=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(submit.call_args.args[1]["start_frame_filename"], self.PAYLOAD["start_frame_filename"])

    def test_a_render_is_refused_before_any_gpu_work_when_ffmpeg_tools_are_missing(self):
        response, submit = self._post(tools_error="ffprobe not found on PATH.")
        self.assertEqual(response.status_code, 503)
        self.assertIn("ffprobe", response.json()["detail"])
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
