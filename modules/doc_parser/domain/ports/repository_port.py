"""
REQ-006 doc_parser — domain/ports/repository_port.py

DocumentRepositoryPort
파싱 결과 저장소 ABC 계약
구현체 위치: adapters/persistence/postgres_document_repo.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas.document import DocumentBlock

from doc_parser.domain.entities.chunk import Chunk
from doc_parser.domain.entities.quality import QualityGateResult


class DocumentRepositoryPort(ABC):
    """파싱 결과 저장소 Port (인터페이스 계약).

    구현체: adapters/persistence/PostgresDocumentRepository
    저장 테이블:
        parsed_documents  — 파일 메타, 파서 결과, 품질 상태
        document_chunks   — 청크 데이터, source_ref, 토큰 수
        parser_logs       — 파서 실행 이력, warnings, 처리 시간
        quality_gate_logs — 판단 기준값, 결과, quality_metrics
    """

    @abstractmethod
    def save(self, document: DocumentBlock) -> UUID:
        """DocumentBlock 저장 → document_id 반환.

        Args:
            document: 저장할 DocumentBlock

        Returns:
            UUID: 저장된 document_id
        """
        ...

    @abstractmethod
    def save_chunks(self, chunks: list[Chunk]) -> None:
        """Chunk 목록 저장.

        Args:
            chunks: 저장할 Chunk 목록
        """
        ...

    @abstractmethod
    def save_quality_log(
        self,
        result: QualityGateResult,
        document_id: UUID,
    ) -> None:
        """품질 게이트 결과 로그 저장.

        Args:
            result: QualityGateResult
            document_id: 연관된 document_id
        """
        ...