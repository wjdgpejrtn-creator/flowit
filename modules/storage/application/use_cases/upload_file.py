from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from common_schemas.exceptions import ValidationError

from ...domain.entities.scan_result import ScanResult
from ...domain.entities.storage_event import StorageEvent
from ...domain.entities.storage_object import StorageObject
from ...domain.entities.upload_policy import UploadPolicy
from ...domain.ports.object_storage_port import ObjectStoragePort
from ...domain.ports.storage_event_port import StorageEventPort
from ...domain.ports.virus_scan_port import VirusScanPort


class UploadFileUseCase:
    def __init__(
        self,
        storage: ObjectStoragePort,
        virus_scanner: VirusScanPort,
        event_publisher: StorageEventPort,
    ) -> None:
        self._storage = storage
        self._virus_scanner = virus_scanner
        self._event_publisher = event_publisher

    async def execute(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str],
        policy: UploadPolicy,
        actor_id: UUID | None = None,
    ) -> StorageObject:
        if len(data) > policy.max_size:
            raise ValidationError(f"File size {len(data)} exceeds limit {policy.max_size}", code="E-STORAGE-002")

        if content_type not in policy.allowed_types:
            raise ValidationError(f"Content type {content_type} not allowed", code="E-STORAGE-003")

        if policy.virus_scan_required:
            scan_result: ScanResult = await self._virus_scanner.scan(data)
            if not scan_result.clean:
                raise ValidationError(f"Virus detected: {scan_result.threat_name}", code="E-STORAGE-004")

        url = await self._storage.upload(key, data, metadata)
        now = datetime.now(timezone.utc)

        obj = StorageObject(
            object_id=uuid4(),
            bucket=url.split("://")[1].split("/")[0] if "://" in url else "local",
            key=key,
            size=len(data),
            content_type=content_type,
            metadata=metadata,
            uploaded_at=now,
            owner_id=actor_id,
        )

        await self._event_publisher.emit(
            StorageEvent(event_type="uploaded", object_id=obj.object_id, timestamp=now, actor_id=actor_id)
        )

        return obj
