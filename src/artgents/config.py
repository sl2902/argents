from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    gcp_project: str
    gcp_location: str = "us-central1"
    gemini_api_key: str = ""
    parallel_web_api_key: str = ""
    parallel_search_max_results: int = 3
    model_fast: str = "gemini-2.5-flash"
    model_pro: str = "gemini-2.5-pro"

    # CORS: comma-separated list of allowed origins.
    # Default "*" is permissive for local dev; set to the actual frontend
    # origin in production (e.g. "https://artgents.vercel.app").
    cors_allowed_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

settings = Settings()