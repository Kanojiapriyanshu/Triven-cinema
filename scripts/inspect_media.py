#!/usr/bin/env python3
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "api"))

from app.services.media_probe import probe_media  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/inspect_media.py storage/generated/video.mp4")
        return 2

    path = Path(sys.argv[1]).expanduser().resolve()
    info = probe_media(path)
    print(json.dumps(info, indent=2))
    print()
    print("Native/embedded audio stream:", "YES" if info["has_audio"] else "NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
