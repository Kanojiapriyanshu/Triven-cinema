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
    ) -> VideoGenerationResult:
        raise NotImplementedError
