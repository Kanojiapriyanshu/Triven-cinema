from inference.providers.huggingface_ltx import (
    HuggingFaceLTXProvider,
)


def get_video_provider(
    provider: str = "huggingface",
):
    if provider == "huggingface":
        return HuggingFaceLTXProvider()

    raise ValueError(
        f"Unsupported video provider: {provider}"
    )
