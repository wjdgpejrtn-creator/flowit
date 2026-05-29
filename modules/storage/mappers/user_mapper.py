from __future__ import annotations

from auth.domain.entities.user import User, UserRole

from ..orm.user_model import UserModel


class UserMapper:
    @staticmethod
    def to_domain(orm: UserModel) -> User:
        return User(
            user_id=orm.user_id,
            email=orm.email,
            name=orm.name,
            role=orm.role,  # type: ignore[arg-type]
            department_id=orm.department_id,
            is_active=orm.is_active,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def to_orm(entity: User) -> UserModel:
        return UserModel(
            user_id=entity.user_id,
            email=entity.email,
            name=entity.name,
            role=entity.role,
            department_id=entity.department_id,
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
