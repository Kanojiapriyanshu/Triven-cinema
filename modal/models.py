from pathlib import Path


MODEL_ROOT = Path("/models/ltx-2.5")

TRANSFORMER = MODEL_ROOT / "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors"
TEXT_ENCODER = MODEL_ROOT / "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors"
VIDEO_VAE_DIFFUSION = MODEL_ROOT / "vae/ltx-2.5-video-vae-bf16.safetensors"
VIDEO_VAE_CONV = MODEL_ROOT / "vae/ltx-2.5-video-vae-conv-bf16.safetensors"
AUDIO_VAE = MODEL_ROOT / "vae/ltx-2.5-audio-vae-bf16.safetensors"
SPATIAL_UPSCALER = MODEL_ROOT / "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
DETAILING_LORA = MODEL_ROOT / "loras/ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors"

BASE_MODEL_FILES = [
    "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
    "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
    "vae/ltx-2.5-video-vae-bf16.safetensors",
    "vae/ltx-2.5-video-vae-conv-bf16.safetensors",
    "vae/ltx-2.5-audio-vae-bf16.safetensors",
    "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
]

REQUIRED_MODEL_FILES = BASE_MODEL_FILES
DFR_REQUIRED_FILES = [DETAILING_LORA]
