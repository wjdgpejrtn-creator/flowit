"""SearchUserDocumentsUseCase 단위 테스트 (ADR-0028 T1 `search_user_documents`).

발화 → 임베딩 → document_chunks 검색(포트) → 문서별 집계. EmbedderPort/검색 포트 Fake로
임베딩 위임·인가 스코프·chunk 집계·랭킹·관련성 컷을 검증한다(inline 헬퍼, conftest 미사용).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from nodes_graph.domain.ports.embedder_port import EmbedderPort

from ai_agent.application.agents.skills_builder.search_user_documents_use_case import (
    SearchUserDocumentsUseCase,
)
from ai_agent.domain.ports.user_document_search import UserDocumentSearchPort
from ai_agent.domain.value_objects.document_hit import DocumentChunkHit


class _FakeEmbedder(EmbedderPort):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.5] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] * 768 for _ in texts]


class _FakeSearchPort(UserDocumentSearchPort):
    def __init__(self, hits: list[DocumentChunkHit]) -> None:
        self._hits = hits
        self.calls: list[dict] = []

    async def search_chunks_by_embedding(
        self, query_embedding: list[float], user_id: UUID, limit: int = 20
    ) -> list[DocumentChunkHit]:
        self.calls.append(
            {"embedding": query_embedding, "user_id": user_id, "limit": limit}
        )
        return self._hits


def _hit(doc_id: UUID, distance: float, chunk_index: int = 0, file_name: str = "a.pdf") -> DocumentChunkHit:
    return DocumentChunkHit(
        document_id=doc_id, file_name=file_name, distance=distance, chunk_index=chunk_index
    )


def _make_uc(hits: list[DocumentChunkHit], embedder: _FakeEmbedder | None = None):
    port = _FakeSearchPort(hits)
    return SearchUserDocumentsUseCase(port, embedder or _FakeEmbedder()), port


# ----------------------------------------------------------------------
# 임베딩 위임 + 인가 스코프
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embeds_query_and_passes_user_scope_to_port():
    embedder = _FakeEmbedder()
    uc, port = _make_uc([_hit(uuid4(), 0.1)], embedder=embedder)
    user_id = uuid4()

    await uc.execute("환불 처리 스킬 만들어줘", user_id, chunk_limit=15)

    assert embedder.calls == ["환불 처리 스킬 만들어줘"]   # 발화를 임베딩에 위임
    assert len(port.calls) == 1
    assert port.calls[0]["user_id"] == user_id            # 인가 스코프 전달(IDOR 차단)
    assert port.calls[0]["limit"] == 15
    assert len(port.calls[0]["embedding"]) == 768


# ----------------------------------------------------------------------
# chunk → 문서 집계
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregates_chunks_of_same_document():
    doc = uuid4()
    hits = [_hit(doc, 0.30, 0), _hit(doc, 0.10, 1), _hit(doc, 0.40, 2)]
    uc, _ = _make_uc(hits)

    result = await uc.execute("q", uuid4())

    assert len(result) == 1                       # 같은 문서 chunk 3개 → 후보 1건
    assert result[0].document_id == doc
    assert result[0].chunk_hit_count == 3
    assert result[0].best_distance == 0.10        # 가장 가까운 chunk 거리


@pytest.mark.asyncio
async def test_ranks_by_best_distance_then_hit_count():
    near = uuid4()       # best_distance 작음 → 1순위
    far = uuid4()
    many = uuid4()       # near와 동률 거리지만 hit 많음 → 동률 시 우선
    hits = [
        _hit(far, 0.50, 0),
        _hit(near, 0.05, 0),
        _hit(many, 0.05, 0),
        _hit(many, 0.20, 1),
    ]
    uc, _ = _make_uc(hits)

    result = await uc.execute("q", uuid4())

    assert [r.document_id for r in result] == [many, near, far]


@pytest.mark.asyncio
async def test_respects_document_limit():
    hits = [_hit(uuid4(), 0.1 * i) for i in range(1, 6)]
    uc, _ = _make_uc(hits)

    result = await uc.execute("q", uuid4(), document_limit=2)

    assert len(result) == 2
    assert result[0].best_distance == pytest.approx(0.1)
    assert result[1].best_distance == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_max_distance_filters_irrelevant_documents():
    close = uuid4()
    distant = uuid4()
    hits = [_hit(close, 0.15), _hit(distant, 0.80)]
    uc, _ = _make_uc(hits)

    result = await uc.execute("q", uuid4(), max_distance=0.5)

    assert [r.document_id for r in result] == [close]   # 0.80 > 0.5 컷


@pytest.mark.asyncio
async def test_empty_hits_returns_empty_list():
    uc, _ = _make_uc([])
    assert await uc.execute("q", uuid4()) == []
