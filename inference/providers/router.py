import os

from inference.providers.base import VideoProvider
from inference.providers.huggingface_ltx import HuggingFaceLTXProvider
from inference.providers.modal_ltx import ModalLTXProvider


def get_video_provider(
    provider: str | None = None,
    model: str = "ltx-2.5",
) -> VideoProvider:
    selected = provider or os.getenv("VIDEO_PROVIDER", "huggingface")

    if model != "ltx-2.5":
        raise NotImplementedError(
            f"{model} is visible in the architecture but is not enabled yet. "
            "Use ltx-2.5 for the current MVP."
        )

    if selected == "huggingface":
        return HuggingFaceLTXProvider()

    if selected == "modal":
        return ModalLTXProvider()

    raise ValueError(f"Unsupported video provider: {selected}")
