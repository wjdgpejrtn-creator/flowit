from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

# 스킬빌더 T1 `search_user_documents` 검색 결과 VO (ADR-0028 D1).
#
# 발화 → BGE-M3 임베딩 → `document_chunks`(vector(768), HNSW) 코사인 유사 chunk 검색 →
# **문서별 집계** → 후보 문서 리스트. 검색 어댑터(storage)는 chunk-level hit를 돌려주고,
# use case가 parent_document_id로 묶어 문서 단위 후보(`DocumentHit`)로 집계한다 — "어느
# 문서가 발화와 가장 관련 있나"를 빌더가 사용자에게 제시(또는 T2 parse 대상 선택)하기 위함.
#
# 순수 도메인 VO — node_id/임베딩 원본은 담지 않는다(검색 식별·랭킹에 필요한 최소만).


@dataclass(frozen=True)
class DocumentChunkHit:
    """검색 어댑터가 반환하는 chunk 단위 적중 (포트 출력 — 집계 전 원자료).

    Attributes:
        document_id: 적중 chunk의 부모 문서(`document_chunks.parent_document_id`).
        file_name: 부모 문서 파일명(`documents.file_meta.file_name`) — 어댑터가 join해 채움.
        distance: 쿼리 임베딩과의 코사인 거리(0=동일, 작을수록 유사). HNSW `vector_cosine_ops`.
        chunk_index: 문서 내 chunk 순번(관측·디버깅용).
    """

    document_id: UUID
    file_name: str
    distance: float
    chunk_index: int


@dataclass(frozen=True)
class DocumentHit:
    """문서 단위로 집계된 검색 후보 (use case 출력 — `DocumentChunkHit` 집계 결과).

    Attributes:
        document_id: 후보 문서.
        file_name: 문서 파일명.
        chunk_hit_count: 이 문서에서 임계 내로 적중한 chunk 수(많을수록 발화와 폭넓게 관련).
        best_distance: 적중 chunk 중 최소 코사인 거리(가장 가까운 chunk — 1차 랭킹 키).
    """

    document_id: UUID
    file_name: str
    chunk_hit_count: int
    best_distance: float
