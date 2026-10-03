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


class VideoProvider(ABC):
    name: str

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
        reference_image_path: str | None = None,
        reference_strength: float = 0.95,
    ) -> VideoGenerationResult:
        raise NotImplementedError
