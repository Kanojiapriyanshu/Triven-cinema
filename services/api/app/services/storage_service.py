import shutil
from pathlib import Path

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[4]
STORAGE_DIR = PROJECT_ROOT / "storage"
GENERATED_DIR = STORAGE_DIR / "generated"


class StorageCapacityError(RuntimeError):
    pass


def free_disk_gb() -> float:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(STORAGE_DIR).free / (1024**3)


def ensure_minimum_free_disk() -> float:
    free_gb = free_disk_gb()
    minimum = max(1.0, float(settings.minimum_free_disk_gb))
    if free_gb < minimum:
        raise StorageCapacityError(
            f"Application server disk is low ({free_gb:.1f} GiB free; {minimum:.1f} GiB required). "
            "Run storage cleanup before starting another paid render."
        )
    return free_gb


def resolve_generated_asset(filename: str, *, extensions: set[str]) -> Path:
    """Resolve one generated asset by basename without allowing path traversal."""
    name = Path(filename).name
    if name != filename or not name:
        raise ValueError("Invalid generated asset filename.")
    suffix = Path(name).suffix.lower()
    if suffix not in extensions:
        raise ValueError(f"Unsupported generated asset type: {suffix or 'none'}")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = (GENERATED_DIR / name).resolve()
    if path.parent != GENERATED_DIR.resolve():
        raise ValueError("Invalid generated asset path.")
    if not path.exists():
        raise FileNotFoundError(f"Generated asset not found: {name}")
    return path


def missing_media_tools() -> list[str]:
    """Names of ffmpeg tools a render needs after the GPU step and that are not on PATH."""
    return [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]


def media_tools_error() -> str | None:
    missing = missing_media_tools()
    if not missing:
        return None
    return (
        f"{' and '.join(missing)} not found on PATH. Rendering is blocked before it starts so a paid GPU job "
        "is not wasted on a video that cannot be finished. Install FFmpeg (it ships ffmpeg and ffprobe) and restart the API."
    )
