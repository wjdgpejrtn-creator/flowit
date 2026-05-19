from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from storage.domain.entities.retention_policy import RetentionPolicy
from storage.domain.entities.scan_result import ScanResult
from storage.domain.entities.storage_event import StorageEvent
from storage.domain.entities.storage_object import StorageObject
from storage.domain.entities.upload_policy import UploadPolicy


class TestStorageObject:
    def test_create(self) -> None:
        obj = StorageObject(
            object_id=uuid4(),
            bucket="test-bucket",
            key="uploads/file.pdf",
            size=1024,
            content_type="application/pdf",
            metadata={"author": "test"},
            uploaded_at=datetime.now(timezone.utc),
        )
        assert obj.size == 1024
        assert obj.expires_at is None

    def test_frozen(self) -> None:
        obj = StorageObject(
            object_id=uuid4(),
            bucket="b",
            key="k",
            size=1,
            content_type="text/plain",
            metadata={},
            uploaded_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ValidationError):
            obj.size = 999


class TestUploadPolicy:
    def test_defaults(self) -> None:
        policy = UploadPolicy(max_size=10_000_000, allowed_types=["application/pdf"])
        assert policy.virus_scan_required is True


class TestStorageEvent:
    def test_create(self) -> None:
        event = StorageEvent(
            event_type="uploaded",
            object_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
        )
        assert event.actor_id is None


class TestRetentionPolicy:
    def test_optional_fields(self) -> None:
        policy = RetentionPolicy()
        assert policy.ttl_days is None
        assert policy.archive_after_days is None


class TestScanResult:
    def test_clean(self) -> None:
        result = ScanResult(clean=True, scanned_at=datetime.now(timezone.utc))
        assert result.threat_name is None

    def test_threat(self) -> None:
        result = ScanResult(clean=False, threat_name="Eicar", scanned_at=datetime.now(timezone.utc))
        assert not result.clean
