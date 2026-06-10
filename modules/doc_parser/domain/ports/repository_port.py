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
    async def get_chunks(self, document_id: UUID) -> list[Chunk]:
        """문서의 청킹 결과를 chunk_index 오름차순으로 조회 — SOP→스킬 추출(REQ-004 map-reduce)이 사용.

        분석 워커가 `save_chunks`로 영속한 청크(`document_chunks`, 임베딩 포함)를 읽는다. 청크가
        없으면(구 문서/미분석) 빈 리스트. `token_count`/`chunk_type`은 테이블에 없어 기본값으로
        복원된다(호출자는 block.content 길이로 토큰을 추정). 인가는 호출자가 수행 (Port는 read-only).
        """
        ...

    @abstractmethod
    async def save_quality_log(self, result: QualityGateResult, document_id: UUID) -> None: ...

    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> DocumentBlock | None:
        """문서 단건 조회 — `GET /api/v1/documents/{id}` + analyze worker task가 사용.

        없으면 None 반환. 인가는 호출자가 `DocumentBlock.user_id` 비교로 수행 (Port는 read-only).
        """
        ...

    @abstractmethod
    async def list_by_owner(self, user_id: UUID) -> list[DocumentBlock]:
        """소유자 기준 문서 목록 조회 (최신순) — `GET /api/v1/documents`가 사용.

        owner 본인 문서만 반환. 인가 필터(`user_id`)는 호출자가 전달 (Port는 read-only).
        """
        ...

    @abstractmethod
    async def delete(self, document_id: UUID) -> bool:
        """문서 hard delete — DB row 영구 삭제. `DELETE /api/v1/documents/{id}`가 사용.

        딸린 chunks(`document_chunks`) / quality_log(`quality_logs`)도 함께 제거한다
        (FK ON DELETE CASCADE 유무와 무관하게 구현체가 명시적으로 정리 — 고아 데이터 방지).
        GCS 원본 파일 삭제는 라우터(api_server)가 object_storage로 별도 수행(Port는 DB만).

        삭제 성공 시 True, 대상 미존재 시 False 반환. 인가(owner 비교)는 호출자가 수행.
        """
        ...
