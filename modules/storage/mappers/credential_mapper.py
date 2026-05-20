from __future__ import annotations

from auth.domain.entities.credential import Credential

from ..orm.credential_model import CredentialModel


class CredentialMapper:
    @staticmethod
    def to_domain(orm: CredentialModel) -> Credential:
        return Credential(
            credential_id=orm.credential_id,
            user_id=orm.user_id,
            name=orm.name,
            credential_kind=orm.credential_kind,  # type: ignore[arg-type]
            encrypted_data=bytes(orm.encrypted_data),
            metadata=orm.credential_metadata,
            is_active=orm.is_active,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def to_orm(entity: Credential) -> CredentialModel:
        return CredentialModel(
            credential_id=entity.credential_id,
            user_id=entity.user_id,
            name=entity.name,
            credential_kind=entity.credential_kind,
            encrypted_data=entity.encrypted_data,
            credential_metadata=entity.metadata,
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
