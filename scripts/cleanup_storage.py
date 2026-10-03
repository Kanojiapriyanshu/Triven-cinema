#!/usr/bin/env python3
import argparse
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.core.config import settings  # noqa: E402
from app.services.job_service import prune_old_jobs  # noqa: E402

GENERATED = ROOT / "storage" / "generated"
LOGS = ROOT / "storage" / "logs"


def _is_final(path: Path) -> bool:
    return path.name.startswith("final-") or path.name.startswith("scene-1080p-")



def rotate_logs(apply: bool) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    max_bytes = max(1024 * 1024, int(settings.log_max_bytes))
    rotated_count = 0
    for path in LOGS.glob("*.log"):
        try:
            if path.stat().st_size < max_bytes:
                continue
            print(f"{'ROTATE' if apply else 'WOULD ROTATE'} {path.name}")
            if apply:
                oldest = path.with_name(path.name + ".2")
                older = path.with_name(path.name + ".1")
                oldest.unlink(missing_ok=True)
                if older.exists():
                    older.replace(oldest)
                shutil.copy2(path, older)
                # Truncate in place so launchd's already-open file descriptor keeps
                # writing to the active log instead of the renamed archive.
                with path.open("w", encoding="utf-8"):
                    pass
            rotated_count += 1
        except FileNotFoundError:
            continue
    return rotated_count

def cleanup(apply: bool) -> tuple[int, int]:
    GENERATED.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    preview_cutoff = now - timedelta(days=max(1, settings.preview_retention_days))
    final_cutoff = now - timedelta(days=max(1, settings.final_retention_days))

    removed_files = 0
    removed_bytes = 0

    for path in GENERATED.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() == ".mp4":
            cutoff = final_cutoff if _is_final(path) else preview_cutoff
        elif path.name.endswith(".part") or path.name.startswith(".normalized-"):
            cutoff = now - timedelta(days=1)
        else:
            continue

        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified >= cutoff:
                continue
            size = path.stat().st_size
            print(f"{'DELETE' if apply else 'WOULD DELETE'} {path.name} ({size / 1024 / 1024:.1f} MiB)")
            if apply:
                path.unlink(missing_ok=True)
            removed_files += 1
            removed_bytes += size
        except FileNotFoundError:
            continue

    pruned_jobs = 0
    if apply:
        pruned_jobs = prune_old_jobs(settings.job_retention_days)
    rotated_logs = rotate_logs(apply)

    print(
        f"Generated media: {removed_files} file(s), {removed_bytes / 1024 / 1024:.1f} MiB "
        f"{'removed' if apply else 'eligible'}; jobs pruned: {pruned_jobs}; "
        f"logs {'rotated' if apply else 'eligible for rotation'}: {rotated_logs}."
    )
    return removed_files, pruned_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean old Triven Cinema local server state.")
    parser.add_argument("--apply", action="store_true", help="Actually delete eligible files and old jobs.")
    args = parser.parse_args()
    cleanup(args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
