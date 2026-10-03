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
