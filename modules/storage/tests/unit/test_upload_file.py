from __future__ import annotations

from uuid import uuid4

import pytest

from storage.application.use_cases.upload_file import UploadFileUseCase
from storage.domain.entities.upload_policy import UploadPolicy


@pytest.fixture
def policy() -> UploadPolicy:
    return UploadPolicy(max_size=1_000_000, allowed_types=["application/pdf", "image/png"])


@pytest.fixture
def use_case(object_storage, virus_scanner, event_publisher) -> UploadFileUseCase:
    return UploadFileUseCase(object_storage, virus_scanner, event_publisher)


@pytest.mark.asyncio
async def test_upload_success(use_case, event_publisher, policy) -> None:
    result = await use_case.execute(
        key="test/file.pdf",
        data=b"pdf_content",
        content_type="application/pdf",
        metadata={"source": "test"},
        policy=policy,
    )
    assert result.key == "test/file.pdf"
    assert result.size == 11
    assert len(event_publisher.events) == 1
    assert event_publisher.events[0].event_type == "uploaded"


@pytest.mark.asyncio
async def test_upload_size_exceeds(use_case, policy) -> None:
    from common_schemas.exceptions import ValidationError

    with pytest.raises(ValidationError, match="exceeds limit"):
        await use_case.execute(
            key="big.pdf",
            data=b"x" * 2_000_000,
            content_type="application/pdf",
            metadata={},
            policy=policy,
        )


@pytest.mark.asyncio
async def test_upload_disallowed_type(use_case, policy) -> None:
    from common_schemas.exceptions import ValidationError

    with pytest.raises(ValidationError, match="not allowed"):
        await use_case.execute(
            key="script.exe",
            data=b"binary",
            content_type="application/x-msdownload",
            metadata={},
            policy=policy,
        )


@pytest.mark.asyncio
async def test_upload_virus_detected(object_storage, virus_scanner_dirty, event_publisher, policy) -> None:
    from common_schemas.exceptions import ValidationError

    use_case = UploadFileUseCase(object_storage, virus_scanner_dirty, event_publisher)
    with pytest.raises(ValidationError, match="Virus detected"):
        await use_case.execute(
            key="infected.pdf",
            data=b"malware",
            content_type="application/pdf",
            metadata={},
            policy=policy,
        )
