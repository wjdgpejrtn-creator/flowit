from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    # REQ-011 infra 미구축 단계에서는 Optional — Phase F(Celery)에서 필수가 됨
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # Phase E에서 필수가 됨. 미구축 단계에서는 health가 "skipped" 응답
    orchestrator_url: str | None = Field(default=None, alias="ORCHESTRATOR_URL")
    orchestrator_timeout_s: float = Field(default=60.0, alias="ORCHESTRATOR_TIMEOUT_S")

    cloud_sql_instance: str | None = Field(default=None, alias="CLOUD_SQL_INSTANCE")
    db_iam_user: str | None = Field(default=None, alias="DB_IAM_USER")
    db_name: str = Field(alias="DB_NAME")

    db_host: str | None = Field(default=None, alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_password: str | None = Field(default=None, alias="DB_PASSWORD")

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def use_iam(self) -> bool:
        return bool(self.cloud_sql_instance and self.db_iam_user)
