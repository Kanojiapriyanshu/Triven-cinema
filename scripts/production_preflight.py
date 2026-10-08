#!/usr/bin/env python3
import json
import math
import os
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ERRORS: list[str] = []
WARNINGS: list[str] = []
PRODUCTION_DOMAIN = "cinema.devansh.info"
TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    WARNINGS.append(message)
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    ERRORS.append(message)
    print(f"[FAIL] {message}")


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def command_ok(*command: str) -> bool:
    try:
        return subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        ).returncode == 0
    except Exception:
        return False


def port_in_use(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def hostname_resolves(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        return True
    except socket.gaierror:
        return False


def validate_production_settings(env: dict[str, str]) -> None:
    """Validate deployment policy without exposing secret values in diagnostics."""
    if env.get("TRIVEN_DOMAIN", "").strip() != PRODUCTION_DOMAIN:
        fail(f"TRIVEN_DOMAIN must be {PRODUCTION_DOMAIN} (hostname only, no https://)")
    else:
        ok(f"Production domain is {PRODUCTION_DOMAIN}")

    expected_url = f"https://{PRODUCTION_DOMAIN}"
    if env.get("FRONTEND_URL", "").strip().rstrip("/") != expected_url:
        fail(f"FRONTEND_URL must be {expected_url}")
    else:
        ok("FRONTEND_URL matches the production HTTPS origin")

    if env.get("APP_ENV", "").strip().lower() not in {"production", "prod"}:
        fail("APP_ENV must be production")
    if env.get("DEBUG", "").strip().lower() not in FALSE_VALUES:
        fail("DEBUG must be false")

    cors = env.get("CORS_ORIGINS", "").strip()
    if "*" in cors:
        fail("CORS_ORIGINS cannot contain wildcards in production")
    elif cors:
        warn("CORS_ORIGINS is set; same-origin production traffic normally does not need CORS")
    else:
        ok("CORS_ORIGINS is empty for same-origin production traffic")

    if env.get("AUTH_ENABLED", "true").strip().lower() not in TRUE_VALUES:
        fail("AUTH_ENABLED must be true in production")
    if env.get("AUTO_LOGIN_EMAIL", "").strip():
        fail("AUTO_LOGIN_EMAIL must be empty in production; each visitor must sign in")
    if env.get("DEMO_AUTH_SHOW_OTP", "true").strip().lower() not in FALSE_VALUES:
        fail("DEMO_AUTH_SHOW_OTP must be false in production")
    if len(env.get("TRIVEN_SECRET_KEY", "").strip()) < 32:
        fail("TRIVEN_SECRET_KEY must contain at least 32 characters in production")
    else:
        ok("Session signing secret meets the minimum length")

    if not env.get("SMTP_HOST", "").strip() or not env.get("SMTP_FROM", "").strip():
        fail("SMTP_HOST and SMTP_FROM are required to deliver sign-in codes")
    elif env.get("SMTP_SECURITY", "starttls").strip().lower() not in {"starttls", "ssl"}:
        fail("SMTP_SECURITY must be starttls or ssl in production")
    else:
        ok("Encrypted SMTP delivery is configured")

    if env.get("ENABLE_SYNC_RENDER_ENDPOINTS", "true").strip().lower() not in FALSE_VALUES:
        fail("ENABLE_SYNC_RENDER_ENDPOINTS must be false in production")
    try:
        if int(env.get("JOB_WORKERS", "1")) != 1:
            fail("JOB_WORKERS must be 1 for this single-worker production deployment")
    except ValueError:
        fail("JOB_WORKERS must be the integer 1")

    billing_enabled = env.get("BILLING_ENABLED", "false").strip().lower() in TRUE_VALUES
    enforce_credits = env.get("BILLING_ENFORCE_CREDITS", "false").strip().lower() in TRUE_VALUES
    if enforce_credits and not billing_enabled:
        fail("BILLING_ENFORCE_CREDITS=true requires BILLING_ENABLED=true")


def resolved_compose_environment() -> dict[str, str] | None:
    """Use Compose's dotenv/interpolation semantics, never print its secret output."""
    if not shutil.which("docker"):
        fail("docker is not installed")
        return None
    if not command_ok("docker", "compose", "version"):
        fail("docker compose is unavailable")
        return None
    if not command_ok("docker", "info"):
        fail("Docker daemon is unavailable or the current user cannot access it")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "docker-compose.production.yml"),
             "config", "--format", "json"],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            fail("docker-compose.production.yml failed validation; check .env and Compose configuration")
            return None
        values = json.loads(result.stdout)["services"]["api"]["environment"]
        if not isinstance(values, dict):
            raise ValueError("Missing API environment mapping")
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        fail("Could not resolve the production API environment with Docker Compose")
        return None
    ok("docker-compose.production.yml validates; checking the effective API environment")
    return {key: str(value) if value is not None else "" for key, value in values.items()}


def main() -> int:
    ERRORS.clear()
    WARNINGS.clear()
    print("Triven Cinema Hostinger VPS production preflight")
    print(f"Project: {ROOT}")

    if sys.platform.startswith("linux"):
        ok("Linux host detected")
    else:
        warn(f"Current host is {sys.platform!r}; production target is a Hostinger Linux VPS")

    if not ENV_PATH.exists():
        fail(".env is missing. Copy .env.production.example to .env and add secrets.")
        env = {}
    else:
        env = read_env()
        mode = stat.S_IMODE(ENV_PATH.stat().st_mode)
        if mode & 0o077:
            warn(f".env permissions are {oct(mode)}; run: chmod 600 .env")
        else:
            ok(".env permissions are private")

    effective_env = resolved_compose_environment()
    if effective_env is not None:
        env = effective_env

    required = [
        "TRIVEN_DOMAIN",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "MODAL_APP_NAME",
        "MODAL_FUNCTION_NAME",
    ]
    for key in required:
        if env.get(key):
            ok(f"{key} configured")
        else:
            fail(f"{key} is missing")

    validate_production_settings(env)
    domain = env.get("TRIVEN_DOMAIN", "").strip()
    if domain == PRODUCTION_DOMAIN:
        if hostname_resolves(domain):
            ok(f"DNS resolves for {domain}")
        else:
            warn(f"DNS does not currently resolve for {domain}; Nginx/Certbot HTTPS cannot issue a public certificate yet")

    if env.get("VIDEO_PROVIDER") == "modal":
        ok("VIDEO_PROVIDER=modal")
    else:
        warn("VIDEO_PROVIDER is not modal")

    storage = ROOT / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    if os.access(storage, os.W_OK):
        ok("storage directory is writable")
    elif storage.stat().st_uid == 10001 and stat.S_IMODE(storage.stat().st_mode) & 0o300 == 0o300:
        # The image entrypoint hands storage to its unprivileged UID. The Docker
        # operator need not own it on later deployments; container readiness also
        # checks that the actual API user can write here.
        ok("storage is writable by the container user (UID 10001)")
    else:
        fail("storage directory is not writable by the deployment or container user")

    free_gb = shutil.disk_usage(storage).free / (1024**3)
    try:
        minimum = float(env.get("MINIMUM_FREE_DISK_GB", "10") or 10)
        if not math.isfinite(minimum) or minimum <= 0:
            raise ValueError("minimum must be finite and positive")
    except ValueError:
        fail("MINIMUM_FREE_DISK_GB must be a positive number")
        minimum = 10.0
    if free_gb >= minimum:
        ok(f"Disk free: {free_gb:.1f} GiB")
    else:
        fail(f"Only {free_gb:.1f} GiB free; configured minimum is {minimum:.1f} GiB")

    if env.get("GEMINI_API_KEY"):
        ok("GEMINI_API_KEY configured")
    else:
        warn("GEMINI_API_KEY is empty; multi-scene planning will use the local fallback")

    billing_enabled = env.get("BILLING_ENABLED", "false").strip().lower() in TRUE_VALUES
    if billing_enabled:
        for key in ("TRIVEN_SECRET_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
            if env.get(key):
                ok(f"{key} configured for billing")
            else:
                fail(f"{key} is required when BILLING_ENABLED=true")
        if any(env.get(key) for key in ("STRIPE_PRICE_STARTER", "STRIPE_PRICE_PRO", "STRIPE_PRICE_STUDIO")):
            ok("At least one Stripe Checkout price is configured")
        else:
            fail("Configure at least one Stripe price when BILLING_ENABLED=true")
    else:
        ok("Billing integration is feature-gated off")

    youtube_enabled = env.get("YOUTUBE_ENABLED", "false").strip().lower() in TRUE_VALUES
    if youtube_enabled:
        for key in ("TRIVEN_SECRET_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"):
            if env.get(key):
                ok(f"{key} configured for YouTube")
            else:
                fail(f"{key} is required when YOUTUBE_ENABLED=true")
        callback = env.get("YOUTUBE_REDIRECT_URI", "").strip() or (
            f"https://{domain}/api/v1/youtube/callback" if domain else ""
        )
        if callback:
            ok(f"YouTube OAuth callback: {callback}")
    else:
        ok("YouTube integration is feature-gated off")

    try:
        native_chunk = float(env.get("LTX_NATIVE_CHUNK_SECONDS", "10") or 10)
        max_1080 = float(env.get("MAX_1080P_SCENE_SECONDS", "30") or 30)
        max_4k = float(env.get("MAX_4K_SCENE_SECONDS", "15") or 15)
        if (
            not all(math.isfinite(value) for value in (native_chunk, max_1080, max_4k))
            or native_chunk <= 0
            or max_1080 < native_chunk
            or max_4k <= 0
        ):
            fail("Long-form duration profile is invalid")
        else:
            ok(f"Duration profiles configured: native chunk {native_chunk:g}s, 1080p {max_1080:g}s, 4K {max_4k:g}s")
    except ValueError:
        fail("Duration profile values must be numeric")

    if env.get("TRIVEN_LTX_REPO_REF", "main") == "main":
        warn("TRIVEN_LTX_REPO_REF=main is not reproducible; pin a validated commit/tag")
    else:
        ok("LTX repository revision is pinned")

    if (ROOT / ".git").exists():
        tracked = subprocess.run(
            ["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()
        if tracked:
            fail(".env is tracked by git")
        else:
            ok(".env is not tracked by git")

    nginx_template = ROOT / "deploy" / "hostinger" / "nginx.triven-cinema.conf"
    if nginx_template.exists():
        ok("Host Nginx reverse-proxy template is present")
    else:
        fail("deploy/hostinger/nginx.triven-cinema.conf is missing")

    for port in (80, 443):
        if port_in_use(port):
            if shutil.which("nginx"):
                ok(f"Port {port} is in use; host Nginx is expected to own public HTTP/HTTPS")
            else:
                warn(f"Port {port} is already in use; verify the owning reverse proxy")
        else:
            warn(f"Port {port} is not listening yet; enable Nginx/Certbot before public launch")

    if shutil.which("ufw"):
        ok("UFW command available")
    else:
        warn("ufw is not installed; configure Hostinger firewall or an equivalent host firewall")

    print(f"\nSummary: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(main())
