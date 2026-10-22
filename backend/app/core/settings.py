from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    secret_key: str = "dev-secret-change-me"
    # Через запятую. "*" не используем: cookie требуют явного origin.
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    session_max_age_seconds: int = 7 * 24 * 3600
    bureau_available: bool = True
    # Служебные эндпоинты /api/demo/* (сброс данных, выключение бюро).
    # По умолчанию выключены: они не требуют авторизации, поэтому включать их
    # можно только в отдельном тестовом окружении. На общем сервере сброс
    # выполняется административной командой scripts/demo_reset.py.
    demo_tools_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
