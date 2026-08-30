from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JurisIA API"
    environment: str = "development"
    database_url: str = "sqlite:///./jurisia_dev.db"
    cors_origins: str = "http://localhost:5500"

    datajud_api_key: str = ""
    datajud_tjmt_url: str = "https://api-publica.datajud.cnj.jus.br/api_publica_tjmt/_search"

    auth_required: bool = False
    google_client_id: str = ""
    allowed_emails: str = ""
    allowed_email_domains: str = ""

    ai_provider: str = "gemini"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_email_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_emails.split(",") if item.strip()}

    @property
    def allowed_domain_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_email_domains.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
