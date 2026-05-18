from __future__ import annotations

import pytest


@pytest.fixture
def env_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings 부팅에 필요한 최소 환경변수 (DSN fallback 경로)."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("ORCHESTRATOR_URL", "https://orchestrator.example/")
    monkeypatch.setenv("DB_NAME", "test_db")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.delenv("CLOUD_SQL_INSTANCE", raising=False)
    monkeypatch.delenv("DB_IAM_USER", raising=False)


@pytest.fixture
def env_iam(monkeypatch: pytest.MonkeyPatch, env_minimum: None) -> None:
    """IAM 분기 검증용 — staging/prod 패턴."""
    monkeypatch.setenv("CLOUD_SQL_INSTANCE", "test-project:asia-northeast3:test-instance")
    monkeypatch.setenv("DB_IAM_USER", "api-server-sa@test-project.iam")
