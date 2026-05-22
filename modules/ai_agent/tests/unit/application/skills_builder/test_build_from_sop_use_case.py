"""BuildFromSOPUseCase — wizard extract_draft / confirm 단위 테스트 (ADR-0020 ③-a).

wizard 1차(Q8): SOP → LLM 추출 → 사용자 검토·수정(extract_draft, 저장 X) → 확정(confirm).
confirm이 CreateDraftSkillUseCase로 personal DRAFT 생성 (Option B — NodeDefinition은 publish 시점).
LLM/CreateDraftSkill Mock으로 단위 테스트.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from common_schemas import ContentBlock, DocumentBlock, FileMeta, ParserMeta
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame
from nodes_graph.domain.ports.embedder_port import EmbedderPort

from ai_agent.application.agents.skills_builder.build_from_sop_use_case import (
    BuildFromSOPUseCase,
    _ExtractedSkillNode,
    _ExtractedSkillNodeList,
)
from ai_agent.domain.ports.llm_port import LLMPort

# ----------------------------------------------------------------------
# Fakes (inline 헬퍼 — conftest 미사용 정책)
# ----------------------------------------------------------------------


class _FakeCreateDraftSkill:
    """CreateDraftSkillUseCase mock — confirm이 호출하는 DRAFT 생성 use case."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, **kwargs: Any) -> UUID:
        self.calls.append(kwargs)
        return uuid4()


class _FakeEmbedder(EmbedderPort):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [[0.1] * 768 for _ in texts]


class _FakeLLM(LLMPort):
    def __init__(self, structured_response: Any = None, raise_on_call: Exception | None = None) -> None:
        self._structured_response = structured_response
        self._raise_on_call = raise_on_call
        self.received_prompts: list[str] = []
        self.received_schemas: list[type] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.received_prompts.append(prompt)
        return "stub"

    async def generate_structured(self, prompt: str, schema: type) -> Any:
        self.received_prompts.append(prompt)
        self.received_schemas.append(schema)
        if self._raise_on_call:
            raise self._raise_on_call
        return self._structured_response


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _make_document(blocks: list[ContentBlock] | None = None) -> DocumentBlock:
    if blocks is None:
        blocks = [
            ContentBlock(block_id=uuid4(), block_type="heading", content="고객 응대 SOP", page=1),
            ContentBlock(
                block_id=uuid4(), block_type="text",
                content="1. 고객 문의 접수 시 Slack 알림 발송. 2. 1시간 내 미응답이면 매니저 에스컬레이션.",
                page=1,
            ),
        ]
    return DocumentBlock(
        document_id=uuid4(),
        file_meta=FileMeta(
            file_name="customer_support_sop.pdf", file_type="pdf",
            mime_type="application/pdf", file_size=2048, page_count=1,
        ),
        parser=ParserMeta(parser_name="pdfplumber", parser_version="0.10.0"),
        blocks=blocks,
    )


def _make_extracted(
    *,
    node_type: str = "sop_customer_inquiry_slack_alert",
    name: str = "고객 문의 Slack 알림",
    category: str = "action",
    risk_level: str = "Medium",
    required_connections: list[str] | None = None,
    service_type: str | None = "slack",
    instructions: str = "## When to use\n고객 문의 접수 시.\n## Steps\n1. Slack 채널 확인\n2. 알림 발송",
) -> _ExtractedSkillNode:
    return _ExtractedSkillNode(
        node_type=node_type, name=name,
        description="고객 문의 접수 시 Slack 채널로 알림 메시지 발송",
        category=category, risk_level=risk_level,
        inputs={"type": "object", "properties": {"channel": {"type": "string"}}, "required": ["channel"]},
        outputs={"type": "object", "properties": {"ts": {"type": "string"}}},
        required_connections=required_connections or ["slack"],
        service_type=service_type, instructions=instructions,
    )


def _make_uc(llm: _FakeLLM | None = None, draft: _FakeCreateDraftSkill | None = None,
             embedder: _FakeEmbedder | None = None) -> BuildFromSOPUseCase:
    return BuildFromSOPUseCase(
        create_draft_skill=draft or _FakeCreateDraftSkill(),
        embedder=embedder or _FakeEmbedder(),
        llm=llm or _FakeLLM(),
    )


# ----------------------------------------------------------------------
# extract_draft — 추출만, 저장 안 함 (wizard 1단계)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_draft_returns_skills_without_save():
    draft = _FakeCreateDraftSkill()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    uc = _make_uc(llm=llm, draft=draft)

    frames = [f async for f in uc.extract_draft(uuid4(), _make_document())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.intent == "build_skill"
    assert result.payload["source_type"] == "sop"
    skills = result.payload["skills"]
    assert len(skills) == 1
    assert skills[0]["name"] == "고객 문의 Slack 알림"
    assert skills[0]["instructions"].startswith("## When to use")
    # staging = NodeSpecStaging 필드 (NodeDefinition 미생성)
    assert skills[0]["staging"]["category"] == "action"
    assert skills[0]["staging"]["risk_level"] == "Medium"
    assert skills[0]["staging"]["service_type"] == "slack"
    # ⚠️ 저장 안 함 (사용자 편집 전)
    assert draft.calls == []


@pytest.mark.asyncio
async def test_extract_draft_progress_frames():
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    frames = [f async for f in _make_uc(llm=llm).extract_draft(uuid4(), _make_document())]
    names = {f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)}
    assert "skills_builder.sop.parse_document" in names
    assert "skills_builder.sop.llm_extract" in names


@pytest.mark.asyncio
async def test_extract_draft_empty_document_yields_error():
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[]))
    doc = _make_document(blocks=[])
    frames = [f async for f in _make_uc(llm=llm).extract_draft(uuid4(), doc)]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_DOCUMENT_EMPTY" for f in frames)


# ----------------------------------------------------------------------
# confirm — 편집 결과 → CreateDraftSkill DRAFT (wizard 2단계)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_creates_draft_skills():
    draft = _FakeCreateDraftSkill()
    embedder = _FakeEmbedder()
    uc = _make_uc(draft=draft, embedder=embedder)
    user_id = uuid4()
    skills = [{
        "node_type": "sop_x", "name": "편집된 스킬", "description": "사용자가 수정한 설명",
        "instructions": "## When to use\n...",
        "staging": {
            "category": "action", "input_schema": {"x": 1}, "output_schema": {},
            "risk_level": "Low", "required_connections": ["slack"], "service_type": "slack",
        },
    }]

    frames = [f async for f in uc.confirm(user_id, skills)]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert len(result.payload["skill_ids"]) == 1
    # CreateDraftSkillUseCase 호출 — 편집된 값 + embed
    assert len(draft.calls) == 1
    call = draft.calls[0]
    assert call["owner_user_id"] == user_id
    assert call["name"] == "편집된 스킬"
    assert call["description"] == "사용자가 수정한 설명"
    assert call["node_spec_staging"].category == "action"
    assert call["node_spec_staging"].required_connections == ["slack"]
    assert call["embedding"] == [0.1] * 768
    assert len(embedder.calls) == 1


@pytest.mark.asyncio
async def test_confirm_empty_skills_yields_error():
    frames = [f async for f in _make_uc().confirm(uuid4(), [])]
    assert any(isinstance(f, ErrorFrame) for f in frames)
