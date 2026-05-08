from __future__ import annotations

from auth.domain.entities.session import Session

from ..orm.session_model import SessionModel


class SessionMapper:
    @staticmethod
    def to_domain(orm: SessionModel) -> Session:
        return Session(
            session_id=orm.session_id,
            user_id=orm.user_id,
            session_hash=orm.session_hash,
            expires_at=orm.expires_at,
            is_revoked=orm.is_revoked,
            created_at=orm.created_at,
            device_info=orm.device_info,
        )

    @staticmethod
    def to_orm(entity: Session) -> SessionModel:
        return SessionModel(
            session_id=entity.session_id,
            user_id=entity.user_id,
            session_hash=entity.session_hash,
            expires_at=entity.expires_at,
            is_revoked=entity.is_revoked,
            created_at=entity.created_at,
            device_info=entity.device_info,
        )
