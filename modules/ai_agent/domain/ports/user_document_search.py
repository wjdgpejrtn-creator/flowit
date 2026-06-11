from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..value_objects.document_hit import DocumentChunkHit

# 스킬빌더 T1 `search_user_documents` 검색 포트 (ADR-0028 D1).
#
# 소비자(ai_agent skills builder)가 소유하는 포트 — 구현 어댑터는 storage(`document_chunks`
# pgvector HNSW 쿼리)에 둔다(AgentMemoryRepository·SkillRepository와 동일: ai_agent 포트 →
# storage 구현). 임베딩 인프라(BGE-M3 EmbedderPort, vector(768) HNSW 인덱스)는 기존 것을
# 재사용하고, 본 포트는 "쿼리 임베딩으로 사용자 문서 chunk를 유사도 검색"하는 read 계약만 추가한다.


class UserDocumentSearchPort(ABC):
    """사용자 문서 chunk를 쿼리 임베딩으로 유사도 검색 (스킬빌더 T1)."""

    @abstractmethod
    async def search_chunks_by_embedding(
        self,
        query_embedding: list[float],
        user_id: UUID,
        limit: int = 20,
    ) -> list[DocumentChunkHit]:
        """`user_id` 소유 문서의 chunk를 코사인 거리 오름차순 top-k로 반환.

        인가: `user_id` 소유 문서로 **반드시 스코프**한다(documents.user_id 필터 — IDOR 차단,
        `DocumentRepositoryPort.list_by_owner`와 동일 원칙). 구현은 `document_chunks`를 HNSW
        (`vector_cosine_ops`)로 검색하고 `documents`를 join해 `file_name`을 채운다. 임베딩이
        없는(분석 미완) chunk는 제외. 집계(문서 단위)는 호출 use case가 수행하므로 포트는
        chunk-level 적중을 거리순으로 그대로 돌려준다.
        """
        ...
