#!/usr/bin/env python3
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.core.config import settings  # noqa: E402


ERRORS: list[str] = []
WARNINGS: list[str] = []


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    WARNINGS.append(message)
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    ERRORS.append(message)
    print(f"[FAIL] {message}")


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def check_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        fail(".env is missing. Copy .env.production.example to .env and add secrets.")
        return

    mode = stat.S_IMODE(env_file.stat().st_mode)
    if mode & 0o077:
        warn(f".env permissions are {oct(mode)}. Run: chmod 600 {env_file}")
    else:
        ok(".env permissions are private")

    if not settings.is_production:
        fail(f"APP_ENV must be production for server mode (current: {settings.app_env!r})")
    else:
        ok("APP_ENV=production")

    if settings.debug:
        fail("DEBUG must be false in production")
    else:
        ok("DEBUG=false")

    if settings.video_provider != "modal":
        warn(f"VIDEO_PROVIDER is {settings.video_provider!r}; Modal is recommended for production")
    else:
        ok("VIDEO_PROVIDER=modal")

    if not settings.gemini_api_key:
        warn("GEMINI_API_KEY is empty; storyboard mode will use the local fallback")
    else:
        ok("Gemini key configured")

    if not settings.modal_app_name or not settings.modal_function_name:
        fail("Modal app/function name is missing")
    else:
        ok("Modal app/function configured")

    if settings.triven_ltx_repo_ref == "main":
        warn("TRIVEN_LTX_REPO_REF=main is not reproducible; pin the validated LTX-2 commit/tag before long-lived production")
    else:
        ok(f"LTX repository ref pinned to {settings.triven_ltx_repo_ref}")

    if settings.enable_sync_render_endpoints:
        warn("ENABLE_SYNC_RENDER_ENDPOINTS=true bypasses the bounded job queue")
    else:
        ok("Synchronous paid render endpoints disabled")


def check_runtime() -> None:
    if not (ROOT / ".venv" / "bin" / "python").exists():
        fail(".venv/bin/python is missing")
    else:
        ok("Python virtualenv present")

    for command in ("ffmpeg", "ffprobe", "node", "npm"):
        if command_exists(command):
            ok(f"{command} available")
        else:
            fail(f"{command} not found in PATH")

    if not (ROOT / "apps" / "web" / ".next").exists():
        warn("Next.js production build is missing; install script will build it")
    else:
        ok("Next.js production build present")

    if command_exists("modal"):
        try:
            completed = subprocess.run(
                ["modal", "config", "show"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if completed.returncode == 0:
                ok("Modal CLI authentication/config detected")
            else:
                warn("Modal CLI is installed but `modal config show` failed")
        except Exception:
            warn("Could not validate Modal CLI config")
    else:
        warn("Modal CLI command not found; Python Modal auth may still exist, but validate before production")


def check_disk_and_location() -> None:
    storage = ROOT / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(storage)
    free_gb = usage.free / (1024**3)
    if free_gb < settings.minimum_free_disk_gb:
        fail(
            f"Only {free_gb:.1f} GiB free; minimum configured is {settings.minimum_free_disk_gb:.1f} GiB"
        )
    else:
        ok(f"Disk free: {free_gb:.1f} GiB")

    root_text = str(ROOT)
    if "/Desktop/" in root_text or root_text.endswith("/Desktop"):
        warn(
            "Project is under Desktop. For a long-running macOS service, move it to "
            "~/Services/triven-cinema to avoid Desktop/TCC/iCloud surprises."
        )
    else:
        ok("Project is outside Desktop/Documents protected folders")


def check_git_secrets() -> None:
    if not (ROOT / ".git").exists():
        return
    try:
        tracked = subprocess.run(
            ["git", "ls-files", ".env", ".env.local", "apps/web/.env.local"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if tracked:
            fail(f"Secret environment file is tracked by git: {tracked}")
        else:
            ok("No common secret env files tracked by git")
    except Exception:
        warn("Could not verify git secret-file tracking")



def check_listeners() -> None:
    if not command_exists("lsof"):
        return
    for port in (8000, 3000):
        try:
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        lines = result.stdout.splitlines()[1:]
        public = [line for line in lines if f"*:{port}" in line or f"0.0.0.0:{port}" in line]
        if public:
            warn(
                f"Port {port} is currently listening on all interfaces. Production scripts bind it to 127.0.0.1."
            )
        else:
            ok(f"Existing listener on port {port} is not wildcard-bound")

def main() -> int:
    print("Triven Cinema macOS production preflight")
    print(f"Project: {ROOT}")
    check_env()
    check_runtime()
    check_disk_and_location()
    check_git_secrets()
    check_listeners()

    print(f"\nSummary: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
    if ERRORS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
