"""Documents 라우터 단위 테스트 (REQ-006/009).

라우트는 인증·요청 검증·Port 위임만 담당 — repo/object_storage/celery는 mock으로
교체하여 호출 인자 + 응답 매핑 + 도메인 예외→HTTP 변환만 검증한다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_document_repository
from app.dependencies.storage import get_documents_object_storage
from app.main import create_app
from common_schemas import DocumentBlock, FileMeta, PermissionSource
from fastapi.testclient import TestClient

_OWNER_ID = uuid4()


@pytest.fixture
def app(env_minimum: None, monkeypatch: pytest.MonkeyPatch):
    # Celery dispatch 라우트가 settings.redis_url로 client init — TestClient 환경에서도
    # broker가 살아있도록 mock 주입. 실제 send_task는 dependency override로 fake.
    monkeypatch.setenv("REDIS_URL", "redis://test")
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app, user_id=_OWNER_ID) -> PermissionSource:
    fake_permission = PermissionSource(
        user_id=user_id,
        role="User",  # type: ignore[arg-type]
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: fake_permission
    return fake_permission


def _bearer_token() -> str:
    now = datetime.now(UTC)
    return pyjwt.encode(
        {
            "sub": str(uuid4()),
            "session_hash": "dummy-hash",
            "type": "access",
            "exp": now + timedelta(seconds=3600),
            "iat": now,
        },
        "",
        algorithm="HS256",
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_bearer_token()}"}


def _doc(document_id, *, user_id=_OWNER_ID, blocks=None, name="report.pdf") -> DocumentBlock:
    return DocumentBlock(
        document_id=document_id,
        user_id=user_id,
        file_meta=FileMeta(
            file_name=name,
            file_type=name.split(".")[-1] if "." in name else "unknown",
            mime_type="application/pdf",
            file_size=1234,
        ),
        blocks=blocks or [],
    )


# ── upload ───────────────────────────────────────────────────────────────────


def test_upload_writes_to_gcs_and_db(app) -> None:
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="gs://test-bucket/documents/abc/report.pdf")
    repo = MagicMock()
    saved_id = uuid4()
    repo.save = AsyncMock(return_value=saved_id)

    app.dependency_overrides[get_documents_object_storage] = lambda: storage
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("report.pdf", BytesIO(b"hello"), "application/pdf")},
        headers=_headers(),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["file_name"] == "report.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["file_size"] == 5
    assert body["is_analyzed"] is False
    assert body["gcs_uri"].startswith("gs://")

    # GCS upload 호출 — key 패턴 검증
    upload_call = storage.upload.await_args
    assert upload_call is not None
    key_arg = upload_call.args[0] if upload_call.args else upload_call.kwargs["key"]
    assert key_arg.startswith("documents/") and key_arg.endswith("/report.pdf")
    # repo.save 호출 — DocumentBlock(blocks=[], user_id=actor)
    saved_doc = repo.save.await_args.args[0]
    assert isinstance(saved_doc, DocumentBlock)
    assert saved_doc.user_id == _OWNER_ID
    assert saved_doc.blocks == []
    app.dependency_overrides.clear()


def test_upload_rejects_oversized_file_with_413(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """크기 한도 초과 시 413 — `_MAX_UPLOAD_BYTES` 가드 (Cloud Run OOM 방지)."""
    # 한도를 작게 override(8 bytes)해 10바이트 페이로드로 트리거. 동적 read이므로 module re-import 필요 X.
    monkeypatch.setattr("app.routers.documents._MAX_UPLOAD_BYTES", 8)

    storage = MagicMock()
    storage.upload = AsyncMock()
    repo = MagicMock()
    repo.save = AsyncMock()
    app.dependency_overrides[get_documents_object_storage] = lambda: storage
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("big.bin", BytesIO(b"0123456789"), "application/octet-stream")},
        headers=_headers(),
    )

    assert resp.status_code == 413
    assert "max" in resp.json()["detail"].lower()
    storage.upload.assert_not_awaited()
    repo.save.assert_not_awaited()
    app.dependency_overrides.clear()


def test_upload_rejects_empty_filename(app) -> None:
    storage = MagicMock()
    storage.upload = AsyncMock()
    repo = MagicMock()
    repo.save = AsyncMock()
    app.dependency_overrides[get_documents_object_storage] = lambda: storage
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)

    client = TestClient(app)
    # FastAPI multipart는 filename 없으면 422 (UploadFile required field — but raw bytes 보냄)
    # filename 검증은 빈 문자열 케이스 — files dict에 빈 문자열 filename
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("", BytesIO(b"x"), "application/octet-stream")},
        headers=_headers(),
    )
    # filename이 비면 400(우리 검증) 또는 422(FastAPI 검증). 둘 다 거부.
    assert resp.status_code in (400, 422)
    storage.upload.assert_not_awaited()
    repo.save.assert_not_awaited()
    app.dependency_overrides.clear()


# ── GET ──────────────────────────────────────────────────────────────────────


def test_get_document_owner_pass_through(app) -> None:
    document_id = uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_doc(document_id))
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/documents/{document_id}", headers=_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == str(document_id)
    assert body["is_analyzed"] is False
    app.dependency_overrides.clear()


def test_get_document_non_owner_returns_403(app) -> None:
    document_id = uuid4()
    other_user = uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_doc(document_id, user_id=other_user))
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)  # actor != owner

    client = TestClient(app)
    resp = client.get(f"/api/v1/documents/{document_id}", headers=_headers())
    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_get_document_not_found_returns_404(app) -> None:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/documents/{uuid4()}", headers=_headers())
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_get_document_is_analyzed_true_when_blocks_present(app) -> None:
    from common_schemas import ContentBlock
    document_id = uuid4()
    block = ContentBlock(
        block_id=uuid4(),
        block_type="text",
        content="hello",
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_doc(document_id, blocks=[block]))
    app.dependency_overrides[get_document_repository] = lambda: repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/documents/{document_id}", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["is_analyzed"] is True
    app.dependency_overrides.clear()


def test_get_download_url_returns_presigned(app) -> None:
    document_id = uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_doc(document_id))
    storage = MagicMock()
    storage.presign = AsyncMock(return_value="https://signed.example/abc?sig=x")
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_documents_object_storage] = lambda: storage
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/documents/{document_id}/download", headers=_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["download_url"] == "https://signed.example/abc?sig=x"
    assert body["expires_in"] == 3600
    storage.presign.assert_awaited_once()
    app.dependency_overrides.clear()


# ── analyze ──────────────────────────────────────────────────────────────────


def test_analyze_dispatches_celery_task(app) -> None:
    document_id = uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_doc(document_id))
    celery = MagicMock()
    fake_async = MagicMock()
    fake_async.id = "task-id-xyz"
    celery.send_task.return_value = fake_async
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_celery] = lambda: celery
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(f"/api/v1/documents/{document_id}/analyze", headers=_headers())

    assert resp.status_code == 202
    body = resp.json()
    assert body == {
        "document_id": str(document_id),
        "task_id": "task-id-xyz",
        "action": "analyze",
    }
    celery.send_task.assert_called_once()
    task_name = celery.send_task.call_args.args[0]
    assert task_name == "execution_engine.analyze_document"
    args = celery.send_task.call_args.kwargs.get("args") or celery.send_task.call_args.args[1]
    assert args == [str(document_id)]
    app.dependency_overrides.clear()


def test_analyze_non_owner_returns_403(app) -> None:
    document_id = uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_doc(document_id, user_id=uuid4()))
    celery = MagicMock()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_celery] = lambda: celery
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(f"/api/v1/documents/{document_id}/analyze", headers=_headers())
    assert resp.status_code == 403
    celery.send_task.assert_not_called()
    app.dependency_overrides.clear()


def test_analyze_not_found_returns_404(app) -> None:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    celery = MagicMock()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_celery] = lambda: celery
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(f"/api/v1/documents/{uuid4()}/analyze", headers=_headers())
    assert resp.status_code == 404
    celery.send_task.assert_not_called()
    app.dependency_overrides.clear()


# ── auth gate ─────────────────────────────────────────────────────────────────


def test_documents_routes_require_bearer(app) -> None:
    client = TestClient(app)
    did = uuid4()
    upload_resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("x", BytesIO(b"x"), "text/plain")},
    )
    assert upload_resp.status_code == 401
    assert client.get(f"/api/v1/documents/{did}").status_code == 401
    assert client.get(f"/api/v1/documents/{did}/download").status_code == 401
    assert client.post(f"/api/v1/documents/{did}/analyze").status_code == 401
