#!/usr/bin/env python3
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "storage"
JOBS_DB = STORAGE / "jobs" / "jobs.sqlite3"
METRICS = STORAGE / "metrics"
BACKUPS = STORAGE / "backups"
RETENTION_DAYS = 14


def main() -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUPS / timestamp
    target.mkdir(parents=True, exist_ok=False)

    if JOBS_DB.exists():
        destination = target / "jobs.sqlite3"
        source_conn = sqlite3.connect(f"file:{JOBS_DB}?mode=ro", uri=True)
        dest_conn = sqlite3.connect(destination)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

    if METRICS.exists():
        target_metrics = target / "metrics"
        target_metrics.mkdir(exist_ok=True)
        for path in METRICS.glob("generations.jsonl*"):
            if path.is_file():
                shutil.copy2(path, target_metrics / path.name)

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    for path in BACKUPS.iterdir():
        if not path.is_dir() or path == target:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            shutil.rmtree(path, ignore_errors=True)

    print(f"State backup created: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
