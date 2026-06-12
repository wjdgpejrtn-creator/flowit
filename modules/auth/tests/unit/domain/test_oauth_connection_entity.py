"""OAuthConnection 도메인 엔티티 — access token 만료/갱신 판정 (REQ-002 #452 ②)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from auth.domain.entities.oauth_connection import OAuthConnection


def _conn(*, expires_at, refresh=b"refresh"):
    return OAuthConnection(
        oauth_id=uuid4(),
        user_id=uuid4(),
        service="google",
        credential_id=uuid4(),
        access_token_encrypted=b"enc",
        refresh_token_encrypted=refresh,
        scopes=["email"],
        access_token_expires_at=expires_at,
        connected_at=datetime.now(UTC),
    )


def test_valid_token_does_not_need_refresh():
    now = datetime.now(UTC)
    conn = _conn(expires_at=now + timedelta(hours=1))
    assert conn.needs_token_refresh(now) is False


def test_expired_token_needs_refresh():
    now = datetime.now(UTC)
    conn = _conn(expires_at=now - timedelta(minutes=1))
    assert conn.needs_token_refresh(now) is True


def test_within_skew_needs_refresh():
    now = datetime.now(UTC)
    conn = _conn(expires_at=now + timedelta(seconds=30))
    assert conn.needs_token_refresh(now, skew_seconds=60) is True


def test_legacy_null_expiry_needs_refresh():
    """expires_at NULL(레거시) → best-effort 갱신 대상."""
    now = datetime.now(UTC)
    conn = _conn(expires_at=None)
    assert conn.needs_token_refresh(now) is True


def test_no_refresh_token_cannot_refresh():
    """refresh_token이 없으면 갱신 불가 → 만료여도 False (갱신할 수단 없음)."""
    now = datetime.now(UTC)
    conn = _conn(expires_at=now - timedelta(minutes=1), refresh=None)
    assert conn.needs_token_refresh(now) is False
