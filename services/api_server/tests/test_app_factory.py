from __future__ import annotations

import pytest

from app.config import Settings
from app.main import create_app


def test_create_app_smoke(env_minimum: None) -> None:
    """app factory가 lifespan 없이도 import/등록 무결성 통과."""
    app = create_app()
    assert app.title == "Workflow Automation API"

    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in routes
    assert "/api/docs" in routes
    assert "/api/v1/openapi.json" in routes


def test_settings_iam_branch(env_iam: None) -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.use_iam() is True
    assert s.cloud_sql_instance == "test-project:asia-northeast3:test-instance"
    assert s.db_iam_user == "api-server-sa@test-project.iam"


def test_settings_dsn_fallback(env_minimum: None) -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.use_iam() is False


def test_cors_origin_list_empty(env_minimum: None) -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.cors_origin_list() == []


def test_cors_origin_list_csv(env_minimum: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test ,")
    s = Settings()  # type: ignore[call-arg]
    assert s.cors_origin_list() == ["http://a.test", "http://b.test"]
