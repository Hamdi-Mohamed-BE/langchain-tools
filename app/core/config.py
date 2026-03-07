from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Gym Coach Chatbot"
    debug: bool = True

    database_url: str = "sqlite:///./ai_gym.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "ANYTHING_RANDOM_AND_SECRET"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    google_api_key: str = ""
    youtube_api_key: str = ""
    youtube_api_base_url: str = "https://www.googleapis.com/youtube/v3"
    youtube_region_code: str = "US"
    # Keep compatibility with the user's current key name typo.
    gemini_model: str = "gemini-2.5-flash"
    gemeni_model: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_gemini_model(self) -> str:
        return self.gemeni_model or self.gemini_model


settings = Settings()
