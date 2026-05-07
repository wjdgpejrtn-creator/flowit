from __future__ import annotations

from datetime import datetime, timezone

import pytest

from storage.domain.entities.scan_result import ScanResult
from storage.domain.entities.storage_event import StorageEvent
from storage.domain.ports.object_storage_port import ObjectStoragePort
from storage.domain.ports.storage_event_port import StorageEventPort
from storage.domain.ports.virus_scan_port import VirusScanPort


class InMemoryObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    async def upload(self, key: str, data: bytes, metadata: dict[str, str]) -> str:
        self._store[key] = data
        self._metadata[key] = metadata
        return f"mem://{key}"

    async def download(self, key: str) -> bytes:
        if key not in self._store:
            from common_schemas.exceptions import NotFoundError

            raise NotFoundError(f"File not found: {key}", code="E-STORAGE-001")
        return self._store[key]

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._metadata.pop(key, None)

    async def presign(self, key: str, ttl: int = 3600) -> str:
        return f"mem://{key}?ttl={ttl}"


class FakeVirusScanner(VirusScanPort):
    def __init__(self, *, always_clean: bool = True) -> None:
        self._always_clean = always_clean

    async def scan(self, data: bytes) -> ScanResult:
        return ScanResult(
            clean=self._always_clean,
            threat_name=None if self._always_clean else "TestVirus",
            scanned_at=datetime.now(timezone.utc),
        )


class InMemoryEventPublisher(StorageEventPort):
    def __init__(self) -> None:
        self.events: list[StorageEvent] = []

    async def emit(self, event: StorageEvent) -> None:
        self.events.append(event)


@pytest.fixture
def object_storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


@pytest.fixture
def virus_scanner() -> FakeVirusScanner:
    return FakeVirusScanner()


@pytest.fixture
def virus_scanner_dirty() -> FakeVirusScanner:
    return FakeVirusScanner(always_clean=False)


@pytest.fixture
def event_publisher() -> InMemoryEventPublisher:
    return InMemoryEventPublisher()
