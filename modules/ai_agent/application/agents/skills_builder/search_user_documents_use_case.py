from __future__ import annotations

from uuid import UUID

from nodes_graph.domain.ports.embedder_port import EmbedderPort

from ....domain.ports.user_document_search import UserDocumentSearchPort
from ....domain.value_objects.document_hit import DocumentChunkHit, DocumentHit

# 스킬빌더 T1 `search_user_documents` use case (ADR-0028 D1, 빌드순서 ②).
#
# 발화 → BGE-M3 임베딩 → `document_chunks` HNSW 코사인 검색(포트) → **문서별 집계** → 후보
# 문서 리스트. 임베딩 인프라(EmbedderPort)·HNSW 인덱스는 기존 재사용, 검색 use case만 신설.
# 에이전트 루프(T1~T5 tool-calling) wrap은 O1(프레임 결정) 후 — 본 use case는 콜러블 툴.


class SearchUserDocumentsUseCase:
    """발화로 사용자 문서를 의미 검색해 후보 문서 리스트를 돌려준다 (스킬빌더 T1).

    검색 어댑터(`UserDocumentSearchPort`, storage 구현)는 chunk-level 적중을 거리순으로
    돌려주고, 본 use case가 `parent_document_id`로 묶어 문서 단위 후보(`DocumentHit`)로
    집계한다 — 한 문서의 여러 chunk가 적중해도 후보는 문서 1건으로 합치고, 가장 가까운
    chunk 거리를 1차 랭킹 키로 쓴다. embedding 생성은 EmbedderPort에 위임(인프라 재사용).
    """

    def __init__(self, search_port: UserDocumentSearchPort, embedder: EmbedderPort) -> None:
        self._search_port = search_port
        self._embedder = embedder

    async def execute(
        self,
        query: str,
        user_id: UUID,
        chunk_limit: int = 20,
        document_limit: int = 5,
        max_distance: float | None = None,
    ) -> list[DocumentHit]:
        """`user_id`의 문서를 `query` 임베딩으로 검색해 상위 `document_limit`개 문서 후보 반환.

        Args:
            query: 사용자 발화(스킬 의도) — 임베딩해서 chunk 유사도 검색에 사용.
            user_id: 검색 스코프(소유자) — 포트가 documents.user_id로 필터(IDOR 차단).
            chunk_limit: 포트에서 받아올 chunk 적중 상한(집계 전). 문서당 chunk가 여럿이라
                document_limit보다 넉넉히 둔다.
            document_limit: 집계 후 돌려줄 문서 후보 상한.
            max_distance: 코사인 거리 상한(관련성 컷). 지정 시 best_distance가 이를 넘는 문서
                제외. None이면 거리 필터 없이 top-k.

        Returns:
            관련성 순(best_distance 오름차순, 동률 시 chunk_hit_count 내림차순) DocumentHit 목록.
            적중 chunk가 없으면 빈 리스트.
        """
        query_embedding = await self._embedder.embed(query)
        chunk_hits = await self._search_port.search_chunks_by_embedding(
            query_embedding, user_id, chunk_limit
        )
        return self._aggregate(chunk_hits, document_limit, max_distance)

    @staticmethod
    def _aggregate(
        chunk_hits: list[DocumentChunkHit],
        document_limit: int,
        max_distance: float | None,
    ) -> list[DocumentHit]:
        """chunk 적중을 문서 단위로 집계 — 등장 순서 무관, best_distance·hit_count 산출."""
        by_doc: dict[UUID, DocumentHit] = {}
        for hit in chunk_hits:
            if max_distance is not None and hit.distance > max_distance:
                continue
            current = by_doc.get(hit.document_id)
            if current is None:
                by_doc[hit.document_id] = DocumentHit(
                    document_id=hit.document_id,
                    file_name=hit.file_name,
                    chunk_hit_count=1,
                    best_distance=hit.distance,
                )
            else:
                by_doc[hit.document_id] = DocumentHit(
                    document_id=current.document_id,
                    file_name=current.file_name,
                    chunk_hit_count=current.chunk_hit_count + 1,
                    best_distance=min(current.best_distance, hit.distance),
                )

        ranked = sorted(
            by_doc.values(),
            key=lambda d: (d.best_distance, -d.chunk_hit_count),
        )
        return ranked[:document_limit]
