from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from auth.domain.entities import User, UserRole
from auth.domain.ports import UserRepository


def _now() -> datetime:
    return datetime.now(UTC)


class TestUserEntity:
    def test_default_role_and_active(self) -> None:
        u = User(
            user_id=uuid4(),
            email="alice@example.com",
            name="Alice",
            created_at=_now(),
            updated_at=_now(),
        )
        assert u.role == "User"
        assert u.is_active is True
        assert u.department_id is None

    def test_admin_role(self) -> None:
        u = User(
            user_id=uuid4(),
            email="admin@example.com",
            name="Admin",
            role="Admin",
            created_at=_now(),
            updated_at=_now(),
        )
        assert u.role == "Admin"

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            User(  # type: ignore[arg-type]
                user_id=uuid4(),
                email="x@example.com",
                name="X",
                role="Superuser",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_with_department(self) -> None:
        dept_id = uuid4()
        u = User(
            user_id=uuid4(),
            email="dev@example.com",
            name="Dev",
            department_id=dept_id,
            created_at=_now(),
            updated_at=_now(),
        )
        assert u.department_id == dept_id


class TestUserRepositoryPort:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            UserRepository()  # type: ignore[abstract]
