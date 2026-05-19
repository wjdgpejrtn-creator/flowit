from __future__ import annotations

import pytest


@pytest.fixture
def env_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings 부팅에 필요한 최소 환경변수 (DSN fallback 경로).

    REDIS_URL / ORCHESTRATOR_URL은 Phase A 단계(REQ-011 infra 미구축)에서는 Optional —
    Phase F(Celery)/Phase E(orchestrator) 시점에 필수화. 본 fixture는 graceful skip 검증용.
    """
    monkeypatch.setenv("DB_NAME", "test_db")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("ORCHESTRATOR_URL", raising=False)
    monkeypatch.delenv("CLOUD_SQL_INSTANCE", raising=False)
    monkeypatch.delenv("DB_IAM_USER", raising=False)


@pytest.fixture
def env_iam(monkeypatch: pytest.MonkeyPatch, env_minimum: None) -> None:
    """IAM 분기 검증용 — staging/prod 패턴."""
    monkeypatch.setenv("CLOUD_SQL_INSTANCE", "test-project:asia-northeast3:test-instance")
    monkeypatch.setenv("DB_IAM_USER", "api-server-sa@test-project.iam")
