from __future__ import annotations

from ..domain.entities.storage_object import StorageObject
from ..orm.storage_object_model import StorageObjectModel


class StorageObjectMapper:
    @staticmethod
    def to_domain(orm: StorageObjectModel) -> StorageObject:
        return StorageObject(
            object_id=orm.object_id,
            bucket=orm.bucket,
            key=orm.key,
            size=orm.size,
            content_type=orm.content_type,
            metadata=orm.metadata_json,
            uploaded_at=orm.uploaded_at,
            expires_at=orm.expires_at,
            owner_id=orm.owner_id,
        )

    @staticmethod
    def to_orm(entity: StorageObject) -> StorageObjectModel:
        return StorageObjectModel(
            object_id=entity.object_id,
            bucket=entity.bucket,
            key=entity.key,
            size=entity.size,
            content_type=entity.content_type,
            metadata_json=entity.metadata,
            uploaded_at=entity.uploaded_at,
            expires_at=entity.expires_at,
            owner_id=entity.owner_id,
        )
