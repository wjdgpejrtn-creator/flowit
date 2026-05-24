"""
REQ-006 doc_parser — domain/ports/repository_port.py

문서 저장소 ABC 계약.
구현체: adapters/persistence/postgres_document_repo.py (PostgresDocumentRepository)
"""
from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas import Chunk, DocumentBlock, QualityGateResult


class DocumentRepositoryPort(ABC):
    @abstractmethod
    async def save(self, document: DocumentBlock) -> UUID: ...

    @abstractmethod
    async def save_chunks(self, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    async def save_quality_log(self, result: QualityGateResult, document_id: UUID) -> None: ...
