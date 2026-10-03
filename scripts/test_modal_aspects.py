#!/usr/bin/env python3
"""Paid end-to-end Modal smoke test for all required aspect ratios.

Requires the API to be running locally and RUN_PAID_BENCHMARKS=1.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_URL = os.getenv("TRIVEN_API_URL", "http://127.0.0.1:8000")
OUT_DIR = Path("storage/benchmarks")


def post_json(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60 * 60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    if os.getenv("RUN_PAID_BENCHMARKS") != "1":
        print("Refusing to spend GPU credits. Re-run with RUN_PAID_BENCHMARKS=1")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for aspect in ("1:1", "16:9", "9:16"):
        print(f"Testing {aspect} on Modal...")
        payload = {
            "prompt": (
                "A polished cinematic product shot of a brushed metal wristwatch "
                "rotating slowly on a dark pedestal, soft studio highlights, precise "
                "camera movement, realistic materials."
            ),
            "aspect_ratio": aspect,
            "duration_seconds": 1,
            "seed": 42,
            "decoder": "conv",
            "enhance_prompt": False,
            "quality": "preview",
            "provider": "modal",
            "model": "ltx-2.5",
        }
        try:
            result = post_json("/api/v1/generations/video", payload)
        except urllib.error.HTTPError as exc:
            print(exc.read().decode("utf-8", errors="replace"))
            return 1
        results.append({"aspect_ratio": aspect, **result})
        print(
            f"  {result['media_info']['width']}x{result['media_info']['height']} | "
            f"audio={result['media_info']['has_audio']} | "
            f"render={result['render_seconds']}s | wall={result['wall_seconds']}s"
        )

    output = OUT_DIR / "modal-aspect-smoke.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved benchmark results: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
