import logging
import os
import time
import uuid
from pathlib import Path

import modal
from dotenv import load_dotenv

from inference.providers.base import VideoGenerationResult, VideoProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
GENERATED_DIR = PROJECT_ROOT / "storage" / "generated"
LOGGER = logging.getLogger("triven.modal_ltx")


class ModalLTXProvider(VideoProvider):
    """Client for the self-hosted LTX-2.5 Modal app in modal/app.py."""

    name = "modal-ltx-2.5"
    supports_native_long_video = True

    def __init__(self):
        self.app_name = os.getenv(
            "MODAL_APP_NAME",
            "triven-cinema-ltx",
        )
        self.function_name = os.getenv(
            "MODAL_FUNCTION_NAME",
            "generate_video",
        )
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        duration_seconds: float,
        seed: int,
        decoder: str,
        enhance_prompt: bool = False,
        reference_image_path: str | None = None,
        reference_strength: float = 0.95,
    ) -> VideoGenerationResult:
        started = time.perf_counter()

        reference_bytes: bytes | None = None
        reference_suffix = ".png"
        if reference_image_path:
            path = Path(reference_image_path)
            if not path.exists():
                raise FileNotFoundError(f"Continuity reference frame not found: {path.name}")
            reference_bytes = path.read_bytes()
            reference_suffix = path.suffix.lower() or ".png"

        try:
            remote_function = modal.Function.from_name(
                self.app_name,
                self.function_name,
            )
            result = remote_function.remote(
                prompt=prompt,
                width=width,
                height=height,
                duration_seconds=duration_seconds,
                seed=seed,
                decoder=decoder,
                enhance_prompt=enhance_prompt,
                reference_image_bytes=reference_bytes,
                reference_image_suffix=reference_suffix,
                reference_strength=float(reference_strength),
            )
        except Exception as exc:
            LOGGER.exception(
                "Modal LTX remote invocation failed app=%s function=%s",
                self.app_name,
                self.function_name,
            )
            detail = (str(exc) or repr(exc)).strip().replace("\n", " ")[:600]
            raise RuntimeError(
                "Modal LTX generation failed. Redeploy the current worker with "
                "`modal deploy modal/app.py`, then inspect `modal app logs "
                f"{self.app_name}` if it still fails. Remote error: {detail}"
            ) from exc

        video_bytes = result.get("video_bytes")
        if not video_bytes:
            raise RuntimeError("Modal returned no video bytes.")

        filename = f"ltx-modal-{uuid.uuid4().hex}.mp4"
        destination = GENERATED_DIR / filename
        temporary = destination.with_suffix(".mp4.part")
        temporary.write_bytes(video_bytes)
        temporary.replace(destination)

        wall_elapsed = time.perf_counter() - started
        elapsed = float(result.get("render_seconds") or 0.0)
        if elapsed <= 0:
            elapsed = wall_elapsed

        return VideoGenerationResult(
            filename=filename,
            path=str(destination),
            seed=int(result.get("seed", seed)),
            render_details=str(
                result.get(
                    "render_details",
                    f"{width}x{height} · Modal LTX-2.5",
                )
            ),
            render_seconds=elapsed,
            prompt=str(result.get("prompt", prompt)),
            provider=self.name,
            gpu=str(result.get("gpu") or "Modal GPU"),
            wall_seconds=wall_elapsed,
            reference_conditioned=bool(result.get("reference_conditioned", False)),
            chunk_count=max(1, int(result.get("chunk_count") or 1)),
        )
