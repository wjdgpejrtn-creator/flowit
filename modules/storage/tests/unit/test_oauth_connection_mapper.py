"""OAuthConnectionMapper 단위 테스트 — access_token_expires_at round-trip (REQ-002 #452 ②).

토큰 만료시각 컬럼이 to_orm→to_domain 왕복에서 보존되어야 refresh 판정이 동작한다. 순수
엔티티↔ORM 변환만 검증하므로 DB 없이 실행된다.
"""
from datetime import UTC, datetime
from uuid import uuid4

from auth.domain.entities.oauth_connection import OAuthConnection
from storage.mappers.oauth_connection_mapper import OAuthConnectionMapper


def _conn(*, expires_at):
    return OAuthConnection(
        oauth_id=uuid4(),
        user_id=uuid4(),
        service="google",
        credential_id=uuid4(),
        access_token_encrypted=b"enc-access",
        refresh_token_encrypted=b"enc-refresh",
        scopes=["email"],
        access_token_expires_at=expires_at,
        connected_at=datetime.now(UTC),
    )


def test_expiry_round_trips():
    exp = datetime.now(UTC)
    back = OAuthConnectionMapper.to_domain(OAuthConnectionMapper.to_orm(_conn(expires_at=exp)))
    assert back.access_token_expires_at == exp


def test_null_expiry_round_trips():
    """레거시 connection(NULL) graceful."""
    back = OAuthConnectionMapper.to_domain(OAuthConnectionMapper.to_orm(_conn(expires_at=None)))
    assert back.access_token_expires_at is None
