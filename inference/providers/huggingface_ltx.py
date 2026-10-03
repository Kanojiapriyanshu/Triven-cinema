import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from gradio_client import Client


load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "storage" / "generated"


class HuggingFaceLTXProvider:
    def __init__(self):
        self.token = os.getenv("HF_TOKEN")
        self.space = os.getenv(
            "HF_LTX_SPACE",
            "ChopperBlu/ltx-2-5-demo",
        )

        if not self.token:
            raise RuntimeError(
                "HF_TOKEN is missing from .env"
            )

        GENERATED_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    def generate(
        self,
        prompt: str,
        width: int = 512,
        height: int = 512,
        duration_seconds: float = 1.0,
        seed: int = 42,
        decoder: str = "conv",
        enhance_prompt: bool = False,
    ) -> dict:

        client = Client(
            self.space,
            token=self.token,
        )

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
        seed_used = result[1]
        render_details = result[2]

        filename = (
            f"ltx-{uuid.uuid4().hex}.mp4"
        )

        destination = (
            GENERATED_DIR / filename
        )

        shutil.copy2(
            remote_video_path,
            destination,
        )

        return {
            "filename": filename,
            "path": str(destination),
            "seed": seed_used,
            "render_details": render_details,
            "prompt": prepared_prompt,
        }
