from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "audit_dashboard"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    default_llm_provider: str = "anthropic"
    default_llm_model: str = "claude-opus-4-6"

    whisper_model: str = "whisper-1"
    max_file_size_mb: int = 100

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "audit-dashboard-files"
    r2_public_url: str = ""

    app_secret_key: str = "changeme"

    # Kept as str so pydantic-settings doesn't attempt JSON parsing.
    # Supports comma-separated values: "http://localhost:5173,https://prod.example.com"
    cors_origins: str = "http://localhost:5173"

    # Auth
    jwt_secret_key: str = "changeme-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168  # 7 days
    admin_username: str = "admin"
    admin_password: str = "changeme"

    def get_cors_origins(self) -> list[str]:
        """Parse cors_origins string into a list (comma-separated)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
