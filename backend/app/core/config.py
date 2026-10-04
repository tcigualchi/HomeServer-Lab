from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Homelab Control"
    app_env: str = "development"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    secret_key: str
    database_url: str = "sqlite:///./data/homelab.db"
    session_cookie_name: str = "homelab_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 12
    admin_username: str = "admin"
    admin_password_hash: str | None = None
    log_level: str = "INFO"
    allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    media_web_url: str = "http://192.168.1.50:8889"
    media_hls_url: str = "http://192.168.1.50:8888"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
