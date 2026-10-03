from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Triven Cinema API"
    app_env: str = "development"
    debug: bool = True

    frontend_url: str = "http://localhost:3000"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = 15.0
    gemini_thinking_level: str = "low"

    video_provider: str = "huggingface"
    hf_token: str = ""
    hf_ltx_space: str = "ChopperBlu/ltx-2-5-demo"

    modal_app_name: str = "triven-cinema-ltx"
    modal_function_name: str = "generate_video"

    # Keep these at 0 until you copy the current hourly rates from Modal.
    # They are used only for explicit cost estimates, never presented as billed cost.
    modal_gpu_hourly_usd_b200: float = 0.0
    modal_gpu_hourly_usd_h200: float = 0.0
    modal_gpu_hourly_usd_h100: float = 0.0

    default_render_quality: str = "preview"
    default_decoder: str = "conv"
    default_scene_duration_seconds: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
