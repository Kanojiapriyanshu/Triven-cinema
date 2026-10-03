from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Triven Cinema API"
    app_env: str = "development"
    debug: bool = True

    frontend_url: str = "http://localhost:3000"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    video_provider: str = "huggingface"
    hf_token: str = ""
    hf_ltx_space: str = "ChopperBlu/ltx-2-5-demo"

    modal_app_name: str = "triven-cinema-ltx"
    modal_function_name: str = "generate_video"

    default_render_quality: str = "preview"
    default_decoder: str = "conv"
    default_scene_duration_seconds: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
