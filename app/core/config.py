from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-only-change-me"
DEFAULT_ADMIN_PASSWORD = "change-me-now"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./iammendexmendle.db"
    redis_url: str = ""
    secret_key: str = DEFAULT_SECRET
    admin_username: str = "admin"
    admin_password: str = DEFAULT_ADMIN_PASSWORD
    admin_full_name: str = "Owner"
    admin_email: str = ""
    https_only: bool = False
    business_name: str = "MENDEX CLOUD SOFTS · KENYA"
    whatsapp_number: str = "254708337199"
    whatsapp_channel_url: str = "https://whatsapp.com/channel/0029Va593zA0G0XbY71owm2z"
    contact_email: str = "mendexbackup072@gmail.com"
    public_base_url: str = "http://127.0.0.1:8000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_admin_email: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


settings = Settings()


def check_production_settings() -> None:
    """Refuse to start in production with development defaults."""
    if not settings.is_production:
        return
    problems = []
    if settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32:
        problems.append("SECRET_KEY must be a random string of at least 32 characters")
    if settings.admin_password == DEFAULT_ADMIN_PASSWORD or len(settings.admin_password) < 12:
        problems.append("ADMIN_PASSWORD must be changed and at least 12 characters")
    if not settings.https_only:
        problems.append("HTTPS_ONLY must be true")
    if settings.debug:
        problems.append("DEBUG must be false")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
