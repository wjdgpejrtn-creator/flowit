from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    # 환경 분기 — production이면 OpenAPI/docs 차단 + DSN fallback 금지
    environment: Literal["dev", "staging", "production"] = Field(default="dev", alias="ENVIRONMENT")

    # OAuth 콜백 후 브라우저를 돌려보낼 frontend 진입점 (ADR-0021). infra 2단계 apply로 채워진다.
    frontend_url: str = Field(default="/", alias="FRONTEND_URL")

    # REQ-011 infra 미구축 단계에서는 Optional — Phase F(Celery)에서 필수가 됨
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # Phase E에서 필수가 됨. 미구축 단계에서는 health가 "skipped" 응답
    orchestrator_url: str | None = Field(default=None, alias="ORCHESTRATOR_URL")
    orchestrator_timeout_s: float = Field(default=60.0, alias="ORCHESTRATOR_TIMEOUT_S")

    # Skills Builder Sub-Agent 직결 — SOP 문서→스킬 추출(extract) SSE 프록시 (REQ-010/013).
    # orchestrator(의도 분류)를 거치지 않는 결정적 추출 경로라 전용 클라이언트로 직접 호출.
    # 추출은 LLM 호출이라 길어 timeout 기본을 크게(290s, Cloud Run 300s 이내) 둔다.
    skills_builder_url: str | None = Field(default=None, alias="SKILLS_BUILDER_URL")
    skills_builder_timeout_s: float = Field(default=290.0, alias="SKILLS_BUILDER_TIMEOUT_S")

    cloud_sql_instance: str | None = Field(default=None, alias="CLOUD_SQL_INSTANCE")
    db_iam_user: str | None = Field(default=None, alias="DB_IAM_USER")
    db_name: str = Field(alias="DB_NAME")

    db_host: str | None = Field(default=None, alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_password: str | None = Field(default=None, alias="DB_PASSWORD")

    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="", alias="GOOGLE_REDIRECT_URI")

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def use_iam(self) -> bool:
        return bool(self.cloud_sql_instance and self.db_iam_user)

    def is_production(self) -> bool:
        return self.environment == "production"
