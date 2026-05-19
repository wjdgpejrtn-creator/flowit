"""Unit tests for services.common.gcp_secrets — Modal Secret 마이그레이션 헬퍼."""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import pytest


def _install_fake_google_modules(monkeypatch, *, fake_client_cls=None, fake_auth_default=None):
    """google.cloud.secretmanager / google.auth를 import 시점에 가짜로 대체.

    실제 GCP SDK가 dev 환경에 없을 수 있으므로 lazy import 시점에 stub 주입.
    헬퍼는 함수 내부에서 import하므로 sys.modules에 미리 fake 등록만 하면 됨.
    """
    google_pkg = types.ModuleType("google")
    google_cloud_pkg = types.ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []
    secretmanager_mod = types.ModuleType("google.cloud.secretmanager")
    if fake_client_cls is not None:
        secretmanager_mod.SecretManagerServiceClient = fake_client_cls

    google_auth_mod = types.ModuleType("google.auth")
    if fake_auth_default is not None:
        google_auth_mod.default = fake_auth_default

    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud_pkg)
    monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", secretmanager_mod)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth_mod)


def test_load_secrets_to_env_pulls_and_injects(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-proj")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    fake_client = MagicMock()

    def access(name):
        payload = MagicMock()
        # 각 secret name마다 다른 값 반환
        if "llm-base-url" in name:
            payload.payload.data = b"https://example.modal.run"
        elif "db-name" in name:
            payload.payload.data = b"workflow_automation"
        else:
            payload.payload.data = b"?"
        return payload

    fake_client.access_secret_version.side_effect = access

    _install_fake_google_modules(monkeypatch, fake_client_cls=MagicMock(return_value=fake_client))

    from services.common.gcp_secrets import load_secrets_to_env

    load_secrets_to_env({"llm-base-url": "LLM_BASE_URL", "db-name": "DB_NAME"})

    assert os.environ["LLM_BASE_URL"] == "https://example.modal.run"
    assert os.environ["DB_NAME"] == "workflow_automation"

    # 두 secret 모두 latest 버전으로 호출됐는지
    called_names = [c.kwargs.get("name") or c.args[0] for c in fake_client.access_secret_version.call_args_list]
    assert "projects/test-proj/secrets/llm-base-url/versions/latest" in called_names
    assert "projects/test-proj/secrets/db-name/versions/latest" in called_names


def test_load_secrets_to_env_empty_mapping_is_noop(monkeypatch):
    # client 호출되지 않아야 함 — google.cloud.secretmanager import 자체도 skip
    fake_client_cls = MagicMock()
    _install_fake_google_modules(monkeypatch, fake_client_cls=fake_client_cls)

    from services.common.gcp_secrets import load_secrets_to_env

    load_secrets_to_env({})
    fake_client_cls.assert_not_called()


def test_load_secrets_to_env_explicit_project_overrides_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "wrong-proj")

    fake_client = MagicMock()
    response = MagicMock()
    response.payload.data = b"ok"
    fake_client.access_secret_version.return_value = response

    _install_fake_google_modules(monkeypatch, fake_client_cls=MagicMock(return_value=fake_client))

    from services.common.gcp_secrets import load_secrets_to_env

    load_secrets_to_env({"foo": "FOO"}, project_id="right-proj")

    name = fake_client.access_secret_version.call_args.kwargs.get("name") or fake_client.access_secret_version.call_args.args[0]
    assert name == "projects/right-proj/secrets/foo/versions/latest"


def test_load_secrets_to_env_uses_version_argument(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")

    fake_client = MagicMock()
    response = MagicMock()
    response.payload.data = b"v"
    fake_client.access_secret_version.return_value = response

    _install_fake_google_modules(monkeypatch, fake_client_cls=MagicMock(return_value=fake_client))

    from services.common.gcp_secrets import load_secrets_to_env

    load_secrets_to_env({"foo": "FOO"}, version="3")

    name = fake_client.access_secret_version.call_args.kwargs.get("name") or fake_client.access_secret_version.call_args.args[0]
    assert name.endswith("/versions/3")


def test_load_secrets_to_env_missing_project_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    # ADC default도 None 반환
    fake_auth_default = MagicMock(return_value=(MagicMock(), None))
    _install_fake_google_modules(monkeypatch, fake_auth_default=fake_auth_default)

    from services.common.gcp_secrets import load_secrets_to_env

    with pytest.raises(RuntimeError, match="project_id"):
        load_secrets_to_env({"foo": "FOO"})


def test_load_secrets_to_env_falls_back_to_adc_project(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    fake_client = MagicMock()
    response = MagicMock()
    response.payload.data = b"v"
    fake_client.access_secret_version.return_value = response

    fake_auth_default = MagicMock(return_value=(MagicMock(), "adc-proj"))
    _install_fake_google_modules(
        monkeypatch,
        fake_client_cls=MagicMock(return_value=fake_client),
        fake_auth_default=fake_auth_default,
    )

    from services.common.gcp_secrets import load_secrets_to_env

    load_secrets_to_env({"foo": "FOO"})

    name = fake_client.access_secret_version.call_args.kwargs.get("name") or fake_client.access_secret_version.call_args.args[0]
    assert name.startswith("projects/adc-proj/secrets/")


