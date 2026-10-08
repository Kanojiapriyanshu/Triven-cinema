"""Start frame ("hero frame") generation: a still image of the cast already in position.

Video models are far more accurate at animating a frame than at inventing a person who holds a specific
product from separate reference photos. This is the Reference Anchor workflow used by Higgsfield Cinema Studio:
compose one still from the saved Elements (face photos, product photo) and the scene text with an image model,
let the creator approve it, then animate that exact frame.
"""
import base64
import re
import time
import uuid
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from app.core.config import settings
from app.schemas.elements import ResolvedElementBinding
from app.services.element_service import primary_subject_box
from app.services.storage_service import STORAGE_DIR

GENERATED_DIR = STORAGE_DIR / "generated"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
MAX_REFERENCE_IMAGES = 5
MAX_REFERENCE_SIDE = 1280
SUPPORTED_RATIOS = {"16:9", "9:16", "1:1"}

_MODEL_CACHE: dict[str, tuple[float, str]] = {}


class HeroFrameError(RuntimeError):
    pass


class HeroFrameUnavailable(HeroFrameError):
    """Raised when image generation is not configured."""


def hero_filename_prefix(workspace_id: str) -> str:
    return f"hero-{workspace_id}-"


def _model_rank(name: str) -> tuple[int, bool, str]:
    """Best first: pro over flash, a stable release over a preview, then the newest name."""
    lowered = name.lower()
    tier = 0
    if "lite" in lowered:
        tier = 0
    elif "pro" in lowered:
        tier = 3
    elif "flash" in lowered:
        tier = 2
    return (tier, "preview" not in lowered, lowered)


def ranked_image_models(models: list[dict]) -> list[str]:
    """Image-capable generateContent models, best first."""
    candidates = []
    for item in models:
        name = str(item.get("name", "")).removeprefix("models/")
        methods = item.get("supportedGenerationMethods") or []
        if "image" in name.lower() and "generateContent" in methods and "imagen" not in name.lower():
            candidates.append(name)
    return sorted(candidates, key=_model_rank, reverse=True)


def pick_image_model(models: list[dict]) -> str | None:
    ranked = ranked_image_models(models)
    return ranked[0] if ranked else None


def resolve_image_models() -> list[str]:
    """Models to try in order. A model named in GEMINI_IMAGE_MODEL is used alone."""
    configured = settings.gemini_image_model.strip()
    if configured:
        return [configured]
    cached = _MODEL_CACHE.get("auto")
    if cached and time.time() - cached[0] < 3600:
        return list(cached[1])
    try:
        response = httpx.get(f"{API_ROOT}/models", params={"key": settings.gemini_api_key, "pageSize": 200}, timeout=20)
        response.raise_for_status()
        ranked = ranked_image_models(response.json().get("models") or [])
    except httpx.HTTPError as exc:
        raise HeroFrameError(f"Could not list Gemini models: {str(exc)[:160]}") from exc
    if not ranked:
        raise HeroFrameError(
            "No Gemini image model is available for this key. Set GEMINI_IMAGE_MODEL in .env to an image-capable model."
        )
    _MODEL_CACHE["auto"] = (time.time(), ranked[:4])
    return ranked[:4]


def resolve_image_model() -> str:
    return resolve_image_models()[0]


# Statuses worth retrying on the next model: no access / no quota / temporary trouble for THIS model.
FALLBACK_STATUSES = {404, 429, 500, 502, 503, 504}


def _failure_detail(response) -> tuple[str, bool]:
    """(short reason, whether Google says the free tier has no quota for this model)."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        return "", False
    message = str(error.get("message") or error.get("status") or "")
    haystack = message.lower()
    for detail in error.get("details") or []:
        for violation in (detail or {}).get("violations") or []:
            haystack += " " + str(violation.get("quotaMetric", "")).lower() + " " + str(violation.get("quotaId", "")).lower()
    free_tier = "free_tier" in haystack or "freetier" in haystack or "free tier" in haystack or "limit: 0" in haystack
    return message.split(". For more information")[0][:220], free_tier


def _png_bytes(image: Image.Image) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((MAX_REFERENCE_SIDE, MAX_REFERENCE_SIDE), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def reference_images(bindings: list[ResolvedElementBinding]) -> list[tuple[ResolvedElementBinding, bytes, str]]:
    """Reference pictures for the image model as (element, png bytes, kind).

    kind "photo": the picture to copy the look from. When an upload is a turnaround sheet the main portrait is
    sent as the photo, and the whole sheet follows as kind "sheet" so clothing and proportions from other angles
    can be used without copying the sheet's layout.
    """
    result: list[tuple[ResolvedElementBinding, bytes, str]] = []
    for binding in bindings:
        paths = list(binding.reference_asset_paths or [binding.primary_asset_path])
        limit = 2 if binding.type == "character" else 1
        for path in paths[:limit]:
            if len(result) >= MAX_REFERENCE_IMAGES:
                return result
            with Image.open(path) as opened:
                source = ImageOps.exif_transpose(opened).convert("RGB")
            box = primary_subject_box(source)
            result.append((binding, _png_bytes(source.crop(box) if box else source), "photo"))
            if box and binding.type == "character" and len(result) < MAX_REFERENCE_IMAGES:
                result.append((binding, _png_bytes(source), "sheet"))
    return result


def _replace_handles(text: str, bindings: list[ResolvedElementBinding]) -> str:
    for binding in bindings:
        text = re.sub(rf"(?<![A-Za-z0-9_])@{re.escape(binding.handle)}\b", binding.name, text, flags=re.IGNORECASE)
    return text


def build_instruction(prompt: str, bindings: list[ResolvedElementBinding], aspect_ratio: str, images: list[tuple[ResolvedElementBinding, bytes, str]]) -> str:
    lines: list[str] = []
    for index, (binding, _, kind) in enumerate(images, start=1):
        if kind == "sheet":
            lines.append(
                f"Image {index} is a turnaround sheet of the same person, {binding.name}, seen from the front, side and back. "
                "Use it only to confirm clothing, hair from other angles and body proportions. Never copy its layout: show "
                "one single view of one person."
            )
        elif binding.type == "character":
            lines.append(
                f"Image {index} is {binding.name}, a real person. Reproduce this exact person: face shape, eyes, nose, mouth, "
                "skin tone, hair colour and style, age and proportions. Clothing: follow the scene text; if the scene text does not describe "
                "clothing, use the outfit shown in the reference pictures."
            )
        else:
            lines.append(
                f"Image {index} is {binding.name} ({binding.type}). Reproduce it exactly: same shape, proportions, colours, "
                "materials and every visible detail. Do not invent or change its design."
            )
    scene = _replace_handles(" ".join(prompt.split()), bindings)
    return (
        "Create ONE photorealistic still image: the very first frame of a live-action video shot, as if photographed on a "
        "high-end cinema camera. Natural skin with visible pores, real fabric and material texture, accurate anatomy, sharp "
        "focus on the subject, natural light, true-to-life colour.\n\n"
        + "\n".join(lines)
        + "\n\nShow the instant before anything is said or done, with a relaxed, natural, restrained expression. Ignore "
        "any instruction about sound, speech or camera movement. If a person holds an object, both hands are anatomically "
        "correct with five fingers each and the object is clearly visible, held naturally and at the right scale.\n\n"
        f"SCENE: {scene}\n\n"
        f"Frame it for {aspect_ratio}. Single frame only: no collage, no split screen, no reference sheet, no borders, "
        "no captions, no text overlays, no logos or watermarks that are not on the real objects."
    )


def _extract_image(payload: dict) -> bytes:
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    reason = ""
    for candidate in payload.get("candidates") or []:
        reason = str(candidate.get("finishReason") or reason)
    feedback = (payload.get("promptFeedback") or {}).get("blockReason")
    raise HeroFrameError(
        "The image model returned no picture"
        + (f" (blocked: {feedback})" if feedback else f" ({reason})" if reason else "")
        + ". Try a simpler description or different reference photos."
    )


def generate_hero_frame(
    *,
    workspace_id: str,
    prompt: str,
    bindings: list[ResolvedElementBinding],
    aspect_ratio: str = "16:9",
) -> tuple[Path, str]:
    if not settings.gemini_api_key:
        raise HeroFrameUnavailable(
            "Start frames need a Gemini API key. Add GEMINI_API_KEY to the .env file and restart the API."
        )
    if aspect_ratio not in SUPPORTED_RATIOS:
        aspect_ratio = "16:9"
    if not bindings:
        raise HeroFrameError("Add a character or product with @ first; a start frame is built from your saved photos.")

    images = reference_images(bindings)
    instruction = build_instruction(prompt, bindings, aspect_ratio, images)
    parts: list[dict] = [{"text": instruction}]
    for _, data, _kind in images:
        parts.append({"inlineData": {"mimeType": "image/png", "data": base64.b64encode(data).decode("ascii")}})

    models = resolve_image_models()
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect_ratio}},
    }
    failures: list[tuple[str, int, str, bool]] = []
    response = None
    model = models[0]
    for model in models:
        try:
            response = httpx.post(
                f"{API_ROOT}/models/{model}:generateContent",
                params={"key": settings.gemini_api_key},
                json=body,
                timeout=httpx.Timeout(float(settings.hero_frame_timeout_seconds)),
            )
        except httpx.HTTPError as exc:
            raise HeroFrameError(f"The image model request failed: {str(exc)[:160]}") from exc
        if response.status_code == 200:
            break
        reason, free_tier = _failure_detail(response)
        failures.append((model, response.status_code, reason, free_tier))
        if response.status_code not in FALLBACK_STATUSES:
            break
        response = None

    if response is None or response.status_code != 200:
        last_model, status, reason, _ = failures[-1]
        tried = ", ".join(f"{name} (HTTP {code})" for name, code, _, _ in failures)
        if all(code == 429 for _, code, _, _ in failures):
            hint = (
                "Google says this key's project has no image-generation quota. The free tier does not include image models: "
                "turn on billing for the Google AI Studio project that owns the key."
                if any(free for _, _, _, free in failures)
                else "Google says the quota is used up. Wait a minute and try again, or check usage and billing for the key's project."
            )
            raise HeroFrameError(f"Image generation was refused (quota exceeded). Tried: {tried}. {hint}")
        raise HeroFrameError(f"The image model ({last_model}) returned HTTP {status}. {reason} Tried: {tried}.".strip())

    picture = _extract_image(response.json())
    try:
        with Image.open(BytesIO(picture)) as check:
            check.verify()
    except Exception as exc:  # noqa: BLE001
        raise HeroFrameError("The image model returned a file that is not a valid picture.") from exc

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / f"{hero_filename_prefix(workspace_id)}{uuid.uuid4().hex[:12]}.png"
    with Image.open(BytesIO(picture)) as image:
        image.convert("RGB").save(path, format="PNG")
    return path, model


MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def save_uploaded_hero_frame(workspace_id: str, data: bytes) -> Path:
    """Use a picture the creator made elsewhere (for example in the Gemini app) as the start frame."""
    if not data:
        raise HeroFrameError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HeroFrameError("The start frame must be smaller than 15 MB.")
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        with Image.open(BytesIO(data)) as image:
            picture = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HeroFrameError("The uploaded file is not a valid PNG, JPEG or WEBP picture.") from exc
    if min(picture.size) < 256:
        raise HeroFrameError("The start frame must be at least 256 pixels on its shortest side.")
    picture.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / f"{hero_filename_prefix(workspace_id)}{uuid.uuid4().hex[:12]}.png"
    picture.save(path, format="PNG")
    return path
