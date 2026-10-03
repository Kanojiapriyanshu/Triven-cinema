import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[4]
METRICS_DIR = PROJECT_ROOT / "storage" / "metrics"
METRICS_FILE = METRICS_DIR / "generations.jsonl"
_LOCK = Lock()


def _rotate_metrics_if_needed() -> None:
    max_bytes = max(1024 * 1024, int(settings.metrics_max_bytes))
    if not METRICS_FILE.exists() or METRICS_FILE.stat().st_size < max_bytes:
        return

    rotated = METRICS_FILE.with_suffix(".jsonl.1")
    rotated.unlink(missing_ok=True)
    METRICS_FILE.replace(rotated)


def record_generation_metric(payload: dict) -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }

    with _LOCK:
        _rotate_metrics_if_needed()
        with METRICS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def gpu_hourly_rate(gpu: str | None) -> float:
    normalized = (gpu or "").upper()
    if "B200" in normalized:
        return float(settings.modal_gpu_hourly_usd_b200 or 0.0)
    if "H200" in normalized:
        return float(settings.modal_gpu_hourly_usd_h200 or 0.0)
    if "H100" in normalized:
        return float(settings.modal_gpu_hourly_usd_h100 or 0.0)
    return 0.0


def estimate_gpu_cost(
    *,
    render_seconds: float,
    gpu: str | None,
    output_duration_seconds: float,
) -> tuple[float | None, float | None, str]:
    rate = gpu_hourly_rate(gpu)
    if rate <= 0 or render_seconds <= 0:
        return (
            None,
            None,
            "GPU cost rate is not configured. Set the current Modal hourly rate "
            "for this GPU in .env to enable estimates; estimates are not billed cost.",
        )

    estimated_cost = (render_seconds / 3600.0) * rate
    per_minute = None
    if output_duration_seconds > 0:
        per_minute = estimated_cost * (60.0 / output_duration_seconds)

    return (
        round(estimated_cost, 6),
        round(per_minute, 4) if per_minute is not None else None,
        "Estimated from configured hourly GPU rate and measured render time; "
        "Modal billed cost may differ because of startup, minimum billing, and other overhead.",
    )


def summarize_generation_metrics() -> dict:
    if not METRICS_FILE.exists():
        return {
            "total_events": 0,
            "total_render_seconds": 0.0,
            "total_estimated_cost_usd": 0.0,
            "average_render_seconds": None,
            "average_estimated_cost_usd": None,
            "by_gpu": {},
        }

    events: list[dict] = []
    metric_files = [METRICS_FILE.with_suffix(".jsonl.1"), METRICS_FILE]
    for metric_file in metric_files:
        if not metric_file.exists():
            continue
        for line in metric_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    render_events = [
        event for event in events if float(event.get("render_seconds") or 0.0) > 0
    ]
    total_render = sum(float(event.get("render_seconds") or 0.0) for event in render_events)
    estimated_costs = [
        float(event["estimated_cost_usd"])
        for event in events
        if event.get("estimated_cost_usd") is not None
    ]

    by_gpu: dict[str, dict] = {}
    for event in events:
        gpu = str(event.get("gpu") or "unknown")
        entry = by_gpu.setdefault(
            gpu,
            {"count": 0, "render_seconds": 0.0, "estimated_cost_usd": 0.0},
        )
        entry["count"] += 1
        entry["render_seconds"] += float(event.get("render_seconds") or 0.0)
        entry["estimated_cost_usd"] += float(event.get("estimated_cost_usd") or 0.0)

    for entry in by_gpu.values():
        entry["render_seconds"] = round(entry["render_seconds"], 3)
        entry["estimated_cost_usd"] = round(entry["estimated_cost_usd"], 6)

    return {
        "total_events": len(events),
        "total_render_seconds": round(total_render, 3),
        "total_estimated_cost_usd": round(sum(estimated_costs), 6),
        "average_render_seconds": (
            round(total_render / len(render_events), 3) if render_events else None
        ),
        "average_estimated_cost_usd": (
            round(sum(estimated_costs) / len(estimated_costs), 6)
            if estimated_costs
            else None
        ),
        "by_gpu": by_gpu,
    }
