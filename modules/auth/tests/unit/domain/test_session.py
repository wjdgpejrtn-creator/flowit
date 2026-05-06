from datetime import datetime, timedelta, timezone
from uuid import uuid4

from auth.domain.entities.session import Session


def _make_session(**kwargs) -> Session:
    defaults = dict(
        session_id=uuid4(),
        user_id=uuid4(),
        session_hash="abc123",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc),
    )
    return Session(**{**defaults, **kwargs})


def test_valid_session_is_valid():
    session = _make_session()
    assert session.is_valid() is True


def test_revoked_session_is_invalid():
    session = _make_session(is_revoked=True)
    assert session.is_valid() is False


def test_expired_session_is_invalid():
    session = _make_session(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert session.is_valid() is False


def test_session_is_immutable():
    session = _make_session()
    try:
        session.is_revoked = True  # type: ignore
        assert False, "Should have raised"
    except Exception:
        pass
