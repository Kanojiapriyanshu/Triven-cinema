from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VideoGenerationResult:
    filename: str
    path: str
    seed: int
    render_details: str
    render_seconds: float
    prompt: str
    provider: str
    model: str = "ltx-2.5"
    gpu: str | None = None
    wall_seconds: float | None = None
    reference_conditioned: bool = False
    chunk_count: int = 1
    render_mode: str = "distilled"


class VideoProvider(ABC):
    name: str
    supports_native_long_video: bool = False
    supports_audio_retake: bool = False

    @abstractmethod
    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        duration_seconds: float,
        seed: int,
        decoder: str,
        enhance_prompt: bool = False,
        render_mode: str = "distilled",
        reference_image_path: str | None = None,
        reference_strength: float = 0.95,
        element_reference_sheet_path: str | None = None,
        element_reference_strength: float = 1.0,
    ) -> VideoGenerationResult:
        raise NotImplementedError

    def retake_audio(
        self,
        *,
        video_path: str,
        prompt: str,
        duration_seconds: float,
        seed: int,
    ) -> VideoGenerationResult:
        raise NotImplementedError(f"{self.name} does not support LTX audio Retake.")
