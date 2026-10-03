from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "Triven Cinema API"
    app_env: str = "development"
    debug: bool = True

    # Browser access. In production the Next.js app proxies /api and /media to the
    # loopback-only API, so CORS can stay disabled/empty.
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = 12.0
    gemini_thinking_level: str = "low"

    video_provider: str = "huggingface"
    hf_token: str = ""
    hf_ltx_space: str = "ChopperBlu/ltx-2-5-demo"

    modal_app_name: str = "triven-cinema-ltx"
    modal_function_name: str = "generate_video"
    triven_ltx_repo_ref: str = "main"

    # Keep these at 0 until you copy the current hourly rates from Modal.
    # They are used only for explicit cost estimates, never presented as billed cost.
    modal_gpu_hourly_usd_b200: float = 0.0
    modal_gpu_hourly_usd_h200: float = 0.0
    modal_gpu_hourly_usd_h100: float = 0.0

    default_render_quality: str = "preview"
    default_decoder: str = "conv"
    default_scene_duration_seconds: float = 1.0

    # Single-VPS production safety. One worker avoids duplicate in-memory queues
    # and prevents accidental parallel paid GPU renders.
    job_workers: int = 1
    job_max_pending: int = 3
    job_retention_days: int = 14

    # Keep VPS local storage bounded. Preview clips should age out quickly;
    # final renders are kept longer by default.
    preview_retention_days: int = 3
    final_retention_days: int = 30
    minimum_free_disk_gb: float = 10.0
    metrics_max_bytes: int = 10 * 1024 * 1024
    log_max_bytes: int = 20 * 1024 * 1024
    ffmpeg_timeout_seconds: int = 900
    ffprobe_timeout_seconds: int = 30

    # Expensive synchronous render endpoints are convenient for local smoke tests
    # but bypass the bounded production job queue. Disable them on the public server.
    enable_sync_render_endpoints: bool = True
    enable_metrics_endpoint: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            item.strip().rstrip("/")
            for item in self.cors_origins.split(",")
            if item.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
