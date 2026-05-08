from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ...domain.entities.storage_event import StorageEvent
from ...domain.ports.object_storage_port import ObjectStoragePort
from ...domain.ports.storage_event_port import StorageEventPort


class DeleteFileUseCase:
    def __init__(self, storage: ObjectStoragePort, event_publisher: StorageEventPort) -> None:
        self._storage = storage
        self._event_publisher = event_publisher

    async def execute(self, key: str, object_id: UUID, actor_id: UUID | None = None) -> None:
        await self._storage.delete(key)
        await self._event_publisher.emit(
            StorageEvent(
                event_type="deleted",
                object_id=object_id,
                timestamp=datetime.now(timezone.utc),
                actor_id=actor_id,
            )
        )
