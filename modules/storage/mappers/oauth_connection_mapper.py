from __future__ import annotations

from auth.domain.entities.oauth_connection import OAuthConnection

from ..orm.oauth_connection_model import OAuthConnectionModel


class OAuthConnectionMapper:
    @staticmethod
    def to_domain(orm: OAuthConnectionModel) -> OAuthConnection:
        return OAuthConnection(
            oauth_id=orm.oauth_id,
            user_id=orm.user_id,
            service=orm.service,
            credential_id=orm.credential_id,
            access_token_encrypted=orm.access_token_encrypted,
            refresh_token_encrypted=orm.refresh_token_encrypted,
            scopes=list(orm.scopes),
            is_active=orm.is_active,
            connected_at=orm.connected_at,
            last_refreshed_at=orm.last_refreshed_at,
        )

    @staticmethod
    def to_orm(entity: OAuthConnection) -> OAuthConnectionModel:
        return OAuthConnectionModel(
            oauth_id=entity.oauth_id,
            user_id=entity.user_id,
            service=entity.service,
            credential_id=entity.credential_id,
            access_token_encrypted=entity.access_token_encrypted,
            refresh_token_encrypted=entity.refresh_token_encrypted,
            scopes=list(entity.scopes),
            is_active=entity.is_active,
            connected_at=entity.connected_at,
            last_refreshed_at=entity.last_refreshed_at,
        )
