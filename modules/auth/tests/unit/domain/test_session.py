from datetime import UTC, datetime, timedelta
from uuid import uuid4

from auth.domain.entities.session import Session


def _make_session(**kwargs) -> Session:
    defaults = dict(
        session_id=uuid4(),
        user_id=uuid4(),
        session_hash="abc123",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    return Session(**{**defaults, **kwargs})


def test_valid_session_is_not_expired():
    session = _make_session()
    assert session.is_expired() is False


def test_expired_session_is_expired():
    session = _make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    assert session.is_expired() is True


def test_revoke_sets_is_revoked():
    session = _make_session()
    assert session.is_revoked is False
    session.revoke()
    assert session.is_revoked is True


def test_device_info_optional():
    session = _make_session()
    assert session.device_info is None
    session2 = _make_session(device_info="Chrome/MacOS")
    assert session2.device_info == "Chrome/MacOS"
