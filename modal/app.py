import os
import time
import uuid
from pathlib import Path

import modal

from ltx_worker import build_command, run_ltx_command
from models import MODEL_ROOT, REQUIRED_MODEL_FILES


APP_NAME = "triven-cinema-ltx"
GPU_TYPE = os.getenv("TRIVEN_MODAL_GPU", "B200")

app = modal.App(APP_NAME)

models_volume = modal.Volume.from_name(
    "triven-cinema-models",
    create_if_missing=True,
)

outputs_volume = modal.Volume.from_name(
    "triven-cinema-outputs",
    create_if_missing=True,
)

hf_secret = modal.Secret.from_name("huggingface-secret")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "build-essential")
    .uv_pip_install("uv", "huggingface_hub")
    .run_commands(
        "git clone --depth 1 https://github.com/Lightricks/LTX-2.git /opt/LTX-2",
        "cd /opt/LTX-2 && uv sync --extra natten",
    )
    .add_local_python_source("ltx_worker", "models")
)


@app.function(
    image=image,
    secrets=[hf_secret],
    volumes={"/models": models_volume},
    timeout=60 * 60,
)
def download_models() -> dict:
    """Download gated LTX-2.5 weights once into the persistent model volume."""
    from huggingface_hub import hf_hub_download

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN is missing from the Modal secret `huggingface-secret`."
        )

    MODEL_ROOT.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for filename in REQUIRED_MODEL_FILES:
        path = hf_hub_download(
            repo_id="Lightricks/LTX-2.5",
            filename=filename,
            local_dir=str(MODEL_ROOT),
            token=token,
        )
        downloaded.append(path)

    models_volume.commit()
    return {"downloaded": downloaded, "count": len(downloaded)}


@app.function(
    image=image,
    gpu=GPU_TYPE,
    secrets=[hf_secret],
    volumes={
        "/models": models_volume,
        "/outputs": outputs_volume,
    },
    timeout=60 * 60,
    scaledown_window=60,
)
def generate_video(
    prompt: str,
    width: int = 1024,
    height: int = 576,
    duration_seconds: float = 1.0,
    seed: int = 42,
    decoder: str = "conv",
    enhance_prompt: bool = False,
) -> dict:
    del enhance_prompt  # Prompt enhancement currently happens in Triven/Gemini.

    missing = [
        path for path in REQUIRED_MODEL_FILES
        if not (MODEL_ROOT / path).exists()
    ]
    if missing:
        raise RuntimeError(
            "LTX-2.5 model files are missing. Run "
            "`modal run modal/app.py::download_models` before generation. "
            f"Missing: {missing[:3]}"
        )

    started = time.perf_counter()
    output_path = Path("/outputs") / f"ltx-{uuid.uuid4().hex}.mp4"

    command = build_command(
        prompt=prompt,
        output_path=output_path,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        seed=seed,
        decoder=decoder,
    )
    run_ltx_command(command)

    if not output_path.exists():
        raise RuntimeError("LTX finished without producing an MP4 file.")

    outputs_volume.commit()
    elapsed = time.perf_counter() - started

    return {
        "video_bytes": output_path.read_bytes(),
        "seed": seed,
        "prompt": prompt,
        "render_details": (
            f"{width}x{height} · {duration_seconds:.2f}s · "
            f"{decoder} decoder · {GPU_TYPE}"
        ),
        "render_seconds": elapsed,
        "gpu": GPU_TYPE,
    }


@app.local_entrypoint()
def main():
    print(f"Triven Cinema Modal app: {APP_NAME}")
    print(f"GPU: {GPU_TYPE}")
    print("Prepare models: modal run modal/app.py::download_models")
    print("Deploy: modal deploy modal/app.py")
