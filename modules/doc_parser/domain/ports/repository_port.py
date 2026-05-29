"""
REQ-006 doc_parser — domain/ports/repository_port.py

문서 저장소 ABC 계약.
구현체: modules/storage/repositories/pg_document_repository.py (PgDocumentRepository)
"""
from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas import Chunk, DocumentBlock, QualityGateResult


class DocumentRepositoryPort(ABC):
    @abstractmethod
    async def save(self, document: DocumentBlock) -> UUID:
        """upload 시점: `blocks=[]` 빈 DocumentBlock 저장 (file_meta + user_id만 채움).
        analyze 시점: 동일 `document_id`로 parsed blocks 채워 재호출 — 구현은 UPSERT.
        """
        ...

    @abstractmethod
    async def save_chunks(self, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    async def save_quality_log(self, result: QualityGateResult, document_id: UUID) -> None: ...

    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> DocumentBlock | None:
        """문서 단건 조회 — `GET /api/v1/documents/{id}` + analyze worker task가 사용.

        없으면 None 반환. 인가는 호출자가 `DocumentBlock.user_id` 비교로 수행 (Port는 read-only).
        """
        ...
