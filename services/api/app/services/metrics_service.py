import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


PROJECT_ROOT = Path(__file__).resolve().parents[4]
METRICS_DIR = PROJECT_ROOT / "storage" / "metrics"
METRICS_FILE = METRICS_DIR / "generations.jsonl"
_LOCK = Lock()


def record_generation_metric(payload: dict) -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }

    with _LOCK:
        with METRICS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
