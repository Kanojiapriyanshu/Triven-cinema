import os
import shutil
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from gradio_client import Client

from inference.providers.base import VideoGenerationResult, VideoProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(
    dotenv_path=PROJECT_ROOT / ".env",
    override=False,
)

GENERATED_DIR = PROJECT_ROOT / "storage" / "generated"


class HuggingFaceLTXProvider(VideoProvider):
    name = "huggingface-zero-gpu"

    def __init__(self):
        self.token = os.getenv("HF_TOKEN")
        self.space = os.getenv(
            "HF_LTX_SPACE",
            "ChopperBlu/ltx-2-5-demo",
        )

        if not self.token:
            raise RuntimeError("HF_TOKEN is missing from .env")

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        prompt: str,
        width: int = 512,
        height: int = 512,
        duration_seconds: float = 1.0,
        seed: int = 42,
        decoder: str = "conv",
        enhance_prompt: bool = False,
        reference_image_path: str | None = None,
        reference_strength: float = 0.95,
    ) -> VideoGenerationResult:
        del reference_image_path, reference_strength  # ZeroGPU fallback does not expose Triven first-frame conditioning.
        started = time.perf_counter()

        client = Client(self.space, token=self.token)

        prepared_prompt = client.predict(
            prompt,
            None,
            enhance_prompt,
            api_name="/prepare_prompt",
        )

        result = client.predict(
            prepared_prompt,
            None,
            width,
            height,
            duration_seconds,
            False,
            seed,
            False,
            decoder,
            api_name="/generate_video",
        )

        remote_video_path = result[0]
        seed_used = int(result[1])
        render_details = str(result[2])

        filename = f"ltx-{uuid.uuid4().hex}.mp4"
        destination = GENERATED_DIR / filename
        temporary = destination.with_suffix(".mp4.part")
        shutil.copy2(remote_video_path, temporary)
        temporary.replace(destination)

        elapsed = time.perf_counter() - started

        return VideoGenerationResult(
            filename=filename,
            path=str(destination),
            seed=seed_used,
            render_details=render_details,
            render_seconds=elapsed,
            prompt=str(prepared_prompt),
            provider=self.name,
            gpu="ZeroGPU",
            wall_seconds=elapsed,
        )
