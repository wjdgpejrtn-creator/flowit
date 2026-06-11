"""PgDocumentRepository.get_chunks 단위 테스트 — ORM(document_chunks) → 도메인 Chunk 복원.

SOP→스킬 추출(REQ-004 옵션 C map-reduce/RAG)이 읽는 경로. AsyncSession을 mock해 SQL 없이
복원 로직(block_data JSONB→ContentBlock, embedding vector→list, chunk_index 정렬 위임)만 검증한다.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_schemas import Chunk

from storage.repositories.pg_document_repository import PgDocumentRepository


def _orm_row(*, content: str, idx: int, doc_id, embedding=None) -> SimpleNamespace:
    # DocumentChunkModel 대용 — 실제 컬럼명만 채운다(token_count/chunk_type 컬럼 없음).
    return SimpleNamespace(
        chunk_id=uuid4(),
        parent_document_id=doc_id,
        chunk_index=idx,
        block_data={"block_id": str(uuid4()), "block_type": "text", "content": content, "page": 1},
        importance_score=None,
        embedding=embedding,
    )


def _session_returning(rows: list) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_get_chunks_reconstructs_domain_chunks():
    doc_id = uuid4()
    rows = [
        _orm_row(content="Slack 알림 발송", idx=0, doc_id=doc_id, embedding=[0.1] * 768),
        _orm_row(content="에스컬레이션", idx=1, doc_id=doc_id, embedding=None),
    ]
    repo = PgDocumentRepository(_session_returning(rows))

    chunks = await repo.get_chunks(doc_id)

    assert len(chunks) == 2
    assert all(isinstance(c, Chunk) for c in chunks)
    assert chunks[0].block.content == "Slack 알림 발송"
    assert chunks[0].block.block_type == "text"
    assert chunks[0].parent_document_id == doc_id
    assert chunks[0].embedding == [0.1] * 768
    # 임베딩 없는 청크도 안전 복원(None).
    assert chunks[1].embedding is None
    # 미저장 컬럼은 기본값으로 복원(호출자는 content 길이로 토큰 추정).
    assert chunks[0].token_count == 0


@pytest.mark.asyncio
async def test_get_chunks_empty_returns_empty_list():
    repo = PgDocumentRepository(_session_returning([]))
    assert await repo.get_chunks(uuid4()) == []
