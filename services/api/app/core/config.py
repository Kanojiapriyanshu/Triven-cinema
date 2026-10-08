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
    gemini_timeout_seconds: float = 20.0
    gemini_thinking_level: str = "low"
    gemini_fallback_models: str = "gemini-3.7-flash,gemini-3.6-flash"
    # Image model used for start frames. Empty = pick the best image-capable model the key can use.
    gemini_image_model: str = ""
    hero_frame_timeout_seconds: float = 120.0
    gemini_max_attempts_per_model: int = 3
    gemini_retry_backoff_seconds: float = 0.8

    video_provider: str = "huggingface"
    hf_token: str = ""
    hf_ltx_space: str = "ChopperBlu/ltx-2-5-demo"

    modal_app_name: str = "triven-cinema-ltx"
    modal_function_name: str = "generate_video"
    triven_modal_gpu: str = "B200"
    triven_ltx_repo_ref: str = "v1.4.2"

    # Keep these at 0 until you copy the current hourly rates from Modal.
    # They are used only for explicit cost estimates, never presented as billed cost.
    modal_gpu_hourly_usd_b200: float = 0.0
    modal_gpu_hourly_usd_h200: float = 0.0
    modal_gpu_hourly_usd_h100: float = 0.0

    default_render_quality: str = "preview"
    default_decoder: str = "conv"
    default_scene_duration_seconds: float = 20.0

    # LTX-2.5's native duration head is designed around clips up to 20 seconds.
    # Factory keeps 15-20s as the conservative range, while the creator profile
    # may expose user-selected 1080p scene lengths through the 30s B200/DFR ceiling.
    # Final runtime is independent and may span multiple continuity-locked scenes.
    ltx_native_chunk_seconds: float = 20.0
    max_preview_scene_seconds: float = 20.0
    max_1080p_scene_seconds: float = 30.0
    max_4k_scene_seconds: float = 15.0
    max_factory_duration_seconds: int = 300
    factory_min_scene_seconds: float = 15.0
    factory_standard_max_scene_seconds: float = 20.0
    factory_enable_30s_1080p_single_pass: bool = True
    factory_experimental_1080p_scene_seconds: float = 30.0
    factory_allow_fallback_final: bool = False

    # Enterprise reusable Elements. References are workspace-scoped and immutable
    # version manifests are bound into jobs so later edits cannot silently change
    # an already-rendered project. The Ingredients IC-LoRA is the multi-element
    # identity path; first-frame mode remains available for exact image animation.
    element_max_stored_per_workspace: int = 100
    element_max_assets_per_element: int = 8
    element_max_active_per_scene: int = 6
    element_max_characters_per_scene: int = 3
    element_max_props_per_scene: int = 3
    element_max_locations_per_scene: int = 1
    element_max_styles_per_scene: int = 1
    element_max_upload_mb: int = 15
    # Signed, asset-scoped preview URLs let <img> tags work even when local
    # development uses a split web/API origin. They never expose the workspace token.
    element_asset_url_ttl_seconds: int = 21600
    element_reference_sheet_width: int = 768
    element_reference_sheet_height: int = 448
    element_ingredients_enabled: bool = True
    element_ingredients_strength: float = 1.0
    # Ingredients was trained at 121 frames. The Modal worker keeps longer creator
    # shots in one output while streaming 121-frame overlapping temporal windows,
    # so the explicit 30s 1080p creator profile can retain reference conditioning.
    element_ingredients_max_scene_seconds: float = 30.0

    # Final-render audio guard. Gemini inspects rendered audio for gibberish or
    # unintended speech; Modal can repair failed audio via LTX Retake while keeping
    # the picture frozen.
    factory_audio_qc_enabled: bool = True
    factory_audio_retake_enabled: bool = True
    factory_audio_qc_strict_final: bool = True
    # External QC is advisory infrastructure. A provider outage / 429 / timeout must
    # never discard an already rendered LTX clip. Real QC failures still remain strict.
    factory_qc_fail_open_on_unavailable: bool = True
    # Deliver a reviewable file after genuine QC rejection, too. Failed QC stays
    # visible as qc_passed=False and prevents automatic YouTube publishing.
    # Set false to retain the legacy strict behavior (delete/reject on QC failure).
    factory_preserve_on_qc_failure: bool = True

    # Frozen-still guard. A render whose sampled frames barely change (a held reference image
    # with audio on top) is treated as a failed attempt and retried with a looser reference.
    # Average grey-level change between sampled frames below this value counts as "frozen".
    factory_motion_guard_enabled: bool = True
    motion_guard_min_mean_diff: float = 0.8

    # Continuity/cardinality guard. "auto" requests use this visual QC gate when
    # Gemini is configured; QC failures can trigger a bounded regeneration before
    # a scene is accepted into the factory timeline.
    continuity_vision_qc_enabled: bool = True
    continuity_qc_timeout_seconds: float = 12.0
    continuity_qc_max_frames: int = 5

    # Demo account login. The current devansh.info demo intentionally returns the
    # generated OTP to the browser so testers can sign in without an email provider.
    # Set DEMO_AUTH_SHOW_OTP=false before treating this as production authentication.
    auth_enabled: bool = True
    demo_auth_show_otp: bool = True
    auth_otp_ttl_seconds: int = 600
    auth_otp_max_attempts: int = 5
    auth_session_days: int = 30
    # Open access: when set, nobody signs in. Every visitor is the one account with this email and lands
    # straight in the studio. They all share one workspace (elements, projects, renders) and anyone who can
    # reach the URL can spend GPU credits. Leave empty to require the email sign-in.
    auto_login_email: str = ""
    # Real sign-in email delivery. Without SMTP the only way in is demo mode, which shows the code
    # in the browser and is not acceptable for a public deployment.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_timeout_seconds: float = 15.0
    # Minimum gap between two codes for the same address when email is really sent (anti-spam).
    auth_otp_cooldown_seconds: int = 30

    # Account-owned Studio history. Browser localStorage is only a cache; the
    # canonical previous-chat list lives in SQLite and follows the signed-in user.
    chat_history_limit: int = 100
    chat_workspace_max_bytes: int = 1_500_000

    # Workspace/session signing. Required when billing or YouTube integrations
    # are enabled in production. Never commit the production value.
    triven_secret_key: str = ""

    # Stripe Checkout + credit ledger. Billing can be wired and tested while
    # enforcement stays off; turn BILLING_ENFORCE_CREDITS=true only after the
    # live webhook has been verified end-to-end.
    billing_enabled: bool = False
    billing_enforce_credits: bool = False
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_studio: str = ""
    stripe_starter_seconds: int = 300
    stripe_pro_seconds: int = 1800
    stripe_studio_seconds: int = 7200

    # YouTube Data API OAuth. The server stores refresh tokens encrypted at
    # rest with a key derived from TRIVEN_SECRET_KEY.
    youtube_enabled: bool = False
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = ""
    youtube_allow_public: bool = False

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
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from.strip())

    def production_problems(self) -> tuple[list[str], list[str]]:
        """(blockers, warnings) for a public deployment. Blockers stop the API from starting."""
        errors: list[str] = []
        warnings: list[str] = []
        if not self.triven_secret_key.strip():
            errors.append("TRIVEN_SECRET_KEY is required: it signs login sessions and workspace cookies.")
        elif len(self.triven_secret_key.strip()) < 24:
            warnings.append("TRIVEN_SECRET_KEY is short; use at least 32 random characters.")
        if self.debug:
            errors.append("DEBUG must be false in production (it exposes internal error text).")
        if self.auth_enabled and not self.auto_login_email.strip() and not self.demo_auth_show_otp and not self.smtp_configured:
            errors.append(
                "Login is enabled but there is no way to deliver sign-in codes: set SMTP_HOST and SMTP_FROM "
                "(or, for a private demo only, DEMO_AUTH_SHOW_OTP=true)."
            )
        if not self.auth_enabled:
            warnings.append("AUTH_ENABLED=false leaves every Studio API open without a login.")
        if self.auth_enabled and self.auto_login_email.strip():
            warnings.append(
                "AUTO_LOGIN_EMAIL is set: there is no sign-in. Anyone who can reach this URL uses the same shared "
                "workspace and can spend GPU credits. Put it behind a VPN/IP allow-list or basic auth, or clear it."
            )
        if self.demo_auth_show_otp:
            warnings.append("DEMO_AUTH_SHOW_OTP=true shows the sign-in code in the browser: anyone can sign in as any email.")
        if self.enable_sync_render_endpoints:
            warnings.append("ENABLE_SYNC_RENDER_ENDPOINTS=true bypasses the bounded render queue; set it to false.")
        if "*" in self.cors_origin_list:
            warnings.append("CORS_ORIGINS contains '*'; list the exact origins or leave it empty for same-origin traffic.")
        if self.billing_enabled and not (self.stripe_secret_key and self.stripe_webhook_secret):
            errors.append("BILLING_ENABLED=true needs STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET.")
        if not self.gemini_api_key:
            warnings.append("GEMINI_API_KEY is empty: start frames, AI Director and quality checks are unavailable.")
        return errors, warnings

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def youtube_callback_url(self) -> str:
        if self.youtube_redirect_uri.strip():
            return self.youtube_redirect_uri.strip()
        return f"{self.frontend_url.rstrip('/')}" + "/api/v1/youtube/callback"

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
