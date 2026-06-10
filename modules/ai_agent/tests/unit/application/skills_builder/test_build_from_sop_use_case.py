"""BuildFromSOPUseCase 단위 테스트 (ADR-0020 ③-a, 옵션 1 2단계 분리).

wizard 1차(Q8): SOP → LLM 메타 추출 → 사용자 선택 → LLM detail 추출 → 사용자 검토·수정 → 확정.
extract_metadata + extract_detail 분리(옵션 1)는 응답당 토큰을 줄여 LLM JSON 잘림(EOF) 해소.
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
    _ExtractedSkillNodeDetail,
    _ExtractedSkillNodeMeta,
    _ExtractedSkillNodeMetaList,
)
from ai_agent.domain.ports.llm_port import LLMPort

# ----------------------------------------------------------------------
# Fakes (inline 헬퍼 — conftest 미사용 정책)
# ----------------------------------------------------------------------


class _FakeCreateDraftSkill:
    """CreateDraftSkillUseCase mock — confirm이 호출하는 DRAFT 생성 use case."""

    def __init__(self, raise_on_call: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._raise = raise_on_call

    async def execute(self, **kwargs: Any) -> UUID:
        self.calls.append(kwargs)
        if self._raise:
            raise self._raise
        return uuid4()


class _FakeEmbedder(EmbedderPort):
    def __init__(self, raise_on_call: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._raise = raise_on_call

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._raise:
            raise self._raise
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
        self.received_max_tokens: list[int | None] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.received_prompts.append(prompt)
        return "stub"

    async def generate_structured(self, prompt: str, schema: type, max_tokens: int | None = None) -> Any:
        self.received_prompts.append(prompt)
        self.received_schemas.append(schema)
        self.received_max_tokens.append(max_tokens)
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


def _make_meta(
    *,
    node_type: str = "sop_customer_inquiry_slack_alert",
    name: str = "고객 문의 Slack 알림",
    category: str = "action",
    risk_level: str = "Medium",
) -> _ExtractedSkillNodeMeta:
    return _ExtractedSkillNodeMeta(
        node_type=node_type, name=name,
        description="고객 문의 접수 시 Slack 채널로 알림 메시지 발송",
        category=category, risk_level=risk_level,
    )


def _make_detail(
    *,
    required_connections: list[str] | None = None,
    service_type: str | None = "slack",
    instructions: str = "## When to use\n고객 문의 접수 시.\n## Steps\n1. Slack 채널 확인\n2. 알림 발송",
    composer_instructions: str = "## 필수 노드\n이 스킬은 LLM 노드 + Slack 노드를 함께 배치해 엮어야 한다.",
) -> _ExtractedSkillNodeDetail:
    return _ExtractedSkillNodeDetail(
        inputs={"type": "object", "properties": {"channel": {"type": "string"}}, "required": ["channel"]},
        outputs={"type": "object", "properties": {"ts": {"type": "string"}}},
        required_connections=required_connections or ["slack"],
        service_type=service_type, instructions=instructions,
        composer_instructions=composer_instructions,
    )


def _make_uc(llm: _FakeLLM | None = None, draft: _FakeCreateDraftSkill | None = None,
             embedder: _FakeEmbedder | None = None) -> BuildFromSOPUseCase:
    return BuildFromSOPUseCase(
        create_draft_skill=draft or _FakeCreateDraftSkill(),
        embedder=embedder or _FakeEmbedder(),
        llm=llm or _FakeLLM(),
    )


# ----------------------------------------------------------------------
# extract_metadata — 메타 5필드만, 저장 안 함 (wizard 1단계)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_metadata_returns_metas_without_save():
    draft = _FakeCreateDraftSkill()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeMetaList(skill_node_metas=[_make_meta()]))
    uc = _make_uc(llm=llm, draft=draft)

    frames = [f async for f in uc.extract_metadata(uuid4(), _make_document())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.intent == "build_skill"
    assert result.payload["source_type"] == "sop"
    metas = result.payload["skill_metas"]
    assert len(metas) == 1
    assert metas[0]["name"] == "고객 문의 Slack 알림"
    assert metas[0]["category"] == "action"
    assert metas[0]["risk_level"] == "Medium"
    # 메타에는 detail 필드가 없어야 함 (토큰 절감)
    assert "instructions" not in metas[0]
    assert "inputs" not in metas[0]
    assert "staging" not in metas[0]
    # ⚠️ 저장 안 함 (사용자 편집 전)
    assert draft.calls == []


@pytest.mark.asyncio
async def test_extract_metadata_progress_frames():
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeMetaList(skill_node_metas=[_make_meta()]))
    frames = [f async for f in _make_uc(llm=llm).extract_metadata(uuid4(), _make_document())]
    names = {f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)}
    assert "skills_builder.sop.parse_document" in names
    assert "skills_builder.sop.llm_extract_metadata" in names


@pytest.mark.asyncio
async def test_extract_metadata_empty_document_yields_error():
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeMetaList(skill_node_metas=[]))
    doc = _make_document(blocks=[])
    frames = [f async for f in _make_uc(llm=llm).extract_metadata(uuid4(), doc)]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_DOCUMENT_EMPTY" for f in frames)


@pytest.mark.asyncio
async def test_extract_metadata_llm_generation_failed():
    llm = _FakeLLM(raise_on_call=RuntimeError("modal timeout"))
    frames = [f async for f in _make_uc(llm=llm).extract_metadata(uuid4(), _make_document())]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_LLM_GENERATION_FAILED" for f in frames)


@pytest.mark.asyncio
async def test_extract_metadata_llm_response_invalid():
    # LLM이 _ExtractedSkillNodeMetaList가 아닌 타입 반환
    llm = _FakeLLM(structured_response={"not": "a model"})
    frames = [f async for f in _make_uc(llm=llm).extract_metadata(uuid4(), _make_document())]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_LLM_RESPONSE_INVALID" for f in frames)


@pytest.mark.asyncio
async def test_extract_metadata_bad_category_yields_error():
    bad_meta = _make_meta(category="not_a_category")
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeMetaList(skill_node_metas=[bad_meta]))
    frames = [f async for f in _make_uc(llm=llm).extract_metadata(uuid4(), _make_document())]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_LLM_RESPONSE_INVALID" for f in frames)


# ----------------------------------------------------------------------
# extract_detail — 선택된 메타의 detail 5필드 + staging (wizard 1.5단계)
# ----------------------------------------------------------------------


def _meta_dict() -> dict:
    return {
        "node_type": "sop_customer_inquiry_slack_alert",
        "name": "고객 문의 Slack 알림",
        "description": "고객 문의 접수 시 Slack 채널로 알림 메시지 발송",
        "category": "action",
        "risk_level": "Medium",
    }


@pytest.mark.asyncio
async def test_extract_detail_returns_detail_with_staging():
    llm = _FakeLLM(structured_response=_make_detail())
    uc = _make_uc(llm=llm)

    frames = [f async for f in uc.extract_detail(uuid4(), _make_document(), _meta_dict())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.intent == "build_skill"
    detail = result.payload["skill_detail"]
    # 메타 식별용 echo
    assert detail["node_type"] == "sop_customer_inquiry_slack_alert"
    # detail 필드
    assert detail["instructions"].startswith("## When to use")
    assert detail["inputs"]["properties"]["channel"]["type"] == "string"
    assert detail["outputs"]["properties"]["ts"]["type"] == "string"
    assert detail["required_connections"] == ["slack"]
    assert detail["service_type"] == "slack"
    # staging = 메타 category/risk_level + detail input/output
    assert detail["staging"]["category"] == "action"
    assert detail["staging"]["risk_level"] == "Medium"
    assert detail["staging"]["service_type"] == "slack"


@pytest.mark.asyncio
async def test_extract_detail_returns_composer_instructions():
    # ADR-0024 D3: detail 응답에 COMPOSER.md(composer_instructions) 포함 — drafter 노드구성 주입(#372 결함 A)
    llm = _FakeLLM(structured_response=_make_detail())
    frames = [f async for f in _make_uc(llm=llm).extract_detail(uuid4(), _make_document(), _meta_dict())]
    detail = frames[-1].payload["skill_detail"]
    assert detail["composer_instructions"].startswith("## 필수 노드")


def test_build_prompt_detail_requests_composer_instructions():
    # 프롬프트가 COMPOSER.md(composer_instructions) 합성을 요청 — 2-md 추출 계약(ADR-0024 D3)
    prompt = BuildFromSOPUseCase._build_prompt_detail(_make_document(), [], _make_meta())
    assert "composer_instructions" in prompt
    assert "COMPOSER.md" in prompt


# ----------------------------------------------------------------------
# extract_detail — T4/T5 결정적 스켈레톤 조립 (ADR-0028 D2/D3/D4)
# ----------------------------------------------------------------------


def _skeleton_meta_dict() -> dict:
    # 발화 어휘(매주/구글 시트/요약/슬랙)가 메타에 들어가 scheduled_pipeline에 결정적 매칭
    return {
        "node_type": "weekly_sales_summary_slack",
        "name": "주간 매출 요약 슬랙 발송",
        "description": "매주 구글 시트에서 매출 데이터를 읽어 요약해서 슬랙으로 보낸다",
        "category": "action",
        "risk_level": "Low",
    }


@pytest.mark.asyncio
async def test_extract_detail_skeleton_match_overrides_composer_instructions():
    # 스켈레톤 매칭 시 COMPOSER.md는 LLM 자유추출이 아니라 결정적 조립에서 나온다(D3 §6.6)
    llm = _FakeLLM(structured_response=_make_detail(
        composer_instructions="## 필수 노드\nLLM이 자유 생성한 (무시돼야 할) 지침",
    ))
    frames = [f async for f in _make_uc(llm=llm).extract_detail(
        uuid4(), _make_document(), _skeleton_meta_dict()
    )]
    detail = frames[-1].payload["skill_detail"]
    # 결정적 스켈레톤 산출 — LLM 자유 지침은 대체됨
    assert "LLM이 자유 생성한" not in detail["composer_instructions"]
    assert "scheduled_pipeline" in detail["composer_instructions"]
    assert detail["skeleton_name"] == "scheduled_pipeline"
    # 정밀 BINDS — 발화 도메인 노드가 결정적으로 포함
    assert "google_sheets_read" in detail["bound_node_types"]
    assert "slack_post_message" in detail["bound_node_types"]
    assert "anthropic_chat" in detail["bound_node_types"]


@pytest.mark.asyncio
async def test_extract_detail_skeleton_match_emits_assemble_frame():
    llm = _FakeLLM(structured_response=_make_detail())
    frames = [f async for f in _make_uc(llm=llm).extract_detail(
        uuid4(), _make_document(), _skeleton_meta_dict()
    )]
    names = {f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)}
    assert "skills_builder.sop.search_skeleton" in names
    assert any(n.startswith("skills_builder.sop.assemble_skill.") for n in names)


@pytest.mark.asyncio
async def test_extract_detail_no_skeleton_match_falls_back_to_llm_composer():
    # 스켈레톤 미매칭(고객 응대 SOP — sink-only) → LLM composer_instructions 폴백, BINDS 없음
    llm = _FakeLLM(structured_response=_make_detail(
        composer_instructions="## 필수 노드\nLLM 폴백 지침",
    ))
    frames = [f async for f in _make_uc(llm=llm).extract_detail(
        uuid4(), _make_document(), _meta_dict()
    )]
    detail = frames[-1].payload["skill_detail"]
    assert detail["composer_instructions"] == "## 필수 노드\nLLM 폴백 지침"
    assert detail["skeleton_name"] is None
    assert detail["bound_node_types"] == []


def test_build_skill_utterance_combines_meta_and_document():
    meta = _make_meta(name="주간 요약", node_type="weekly")
    utterance = BuildFromSOPUseCase._build_skill_utterance(meta, _make_document())
    assert "주간 요약" in utterance                     # 메타 name
    assert "Slack 채널로 알림" in utterance              # 메타 description
    assert "고객 문의 접수 시 Slack 알림" in utterance   # 문서 본문 블록


@pytest.mark.asyncio
async def test_extract_detail_progress_frames():
    llm = _FakeLLM(structured_response=_make_detail())
    frames = [f async for f in _make_uc(llm=llm).extract_detail(uuid4(), _make_document(), _meta_dict())]
    names = {f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)}
    assert "skills_builder.sop.parse_document" in names
    # detail 노드명에 node_type 포함 (관측성)
    assert any(n.startswith("skills_builder.sop.llm_extract_detail.") for n in names)


@pytest.mark.asyncio
async def test_extract_detail_empty_document_yields_error():
    llm = _FakeLLM(structured_response=_make_detail())
    doc = _make_document(blocks=[])
    frames = [f async for f in _make_uc(llm=llm).extract_detail(uuid4(), doc, _meta_dict())]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_DOCUMENT_EMPTY" for f in frames)


@pytest.mark.asyncio
async def test_extract_detail_meta_missing_field_yields_error():
    # frontend가 보낸 meta dict에 필수 필드 누락 (예: name)
    bad_meta = {"node_type": "x", "description": "y", "category": "action", "risk_level": "Low"}
    frames = [f async for f in _make_uc().extract_detail(uuid4(), _make_document(), bad_meta)]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_META_INVALID" for f in frames)


@pytest.mark.asyncio
async def test_extract_detail_meta_bad_category_yields_error():
    bad_meta = _meta_dict()
    bad_meta["category"] = "not_a_category"
    frames = [f async for f in _make_uc().extract_detail(uuid4(), _make_document(), bad_meta)]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_META_INVALID" for f in frames)


@pytest.mark.asyncio
async def test_extract_detail_llm_generation_failed():
    llm = _FakeLLM(raise_on_call=RuntimeError("modal timeout"))
    frames = [f async for f in _make_uc(llm=llm).extract_detail(uuid4(), _make_document(), _meta_dict())]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_LLM_GENERATION_FAILED" for f in frames)


@pytest.mark.asyncio
async def test_extract_detail_llm_response_invalid():
    llm = _FakeLLM(structured_response={"not": "a model"})
    frames = [f async for f in _make_uc(llm=llm).extract_detail(uuid4(), _make_document(), _meta_dict())]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_LLM_RESPONSE_INVALID" for f in frames)


# ----------------------------------------------------------------------
# confirm — 편집 결과 → CreateDraftSkill DRAFT (wizard 2단계, 변경 없음)
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
    assert call["instructions"] == "## When to use\n..."  # ADR-0017 — SKILL.md 본문 전달
    assert len(embedder.calls) == 1


@pytest.mark.asyncio
async def test_confirm_passes_composer_instructions():
    # ADR-0024 D3: 편집된 composer_instructions(COMPOSER.md)를 CreateDraftSkill에 전달 → GCS 2-md 저장
    draft = _FakeCreateDraftSkill()
    skill = _valid_skill()
    skill["composer_instructions"] = "## 필수 노드\nLLM 노드 + Email 노드 필수"
    frames = [f async for f in _make_uc(draft=draft).confirm(uuid4(), [skill])]
    assert frames[-1].payload["created_count"] == 1
    assert draft.calls[0]["composer_instructions"] == "## 필수 노드\nLLM 노드 + Email 노드 필수"


@pytest.mark.asyncio
async def test_confirm_missing_composer_passes_none():
    # composer_instructions 누락 시 None 전달 (역호환 — 노드 지침만 있는 스킬)
    draft = _FakeCreateDraftSkill()
    _ = [f async for f in _make_uc(draft=draft).confirm(uuid4(), [_valid_skill()])]
    assert draft.calls[0]["composer_instructions"] is None


@pytest.mark.asyncio
async def test_confirm_empty_skills_yields_error():
    frames = [f async for f in _make_uc().confirm(uuid4(), [])]
    assert any(isinstance(f, ErrorFrame) for f in frames)


@pytest.mark.asyncio
async def test_confirm_missing_instructions_passes_none():
    # 신뢰 경계: instructions 누락(편집으로 제거)돼도 DRAFT는 생성, instructions=None 전달(문서 미저장)
    draft = _FakeCreateDraftSkill()
    skills = [{
        "node_type": "sop_x", "name": "스킬", "description": "설명",
        "staging": {
            "category": "action", "input_schema": {}, "output_schema": {},
            "risk_level": "Low", "required_connections": [], "service_type": None,
        },
    }]

    frames = [f async for f in _make_uc(draft=draft).confirm(uuid4(), skills)]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert len(result.payload["skill_ids"]) == 1
    assert draft.calls[0]["instructions"] is None


def _valid_skill() -> dict:
    return {
        "node_type": "sop_x", "name": "스킬", "description": "설명",
        "instructions": "## When to use\n...",
        "staging": {
            "category": "action", "input_schema": {}, "output_schema": {},
            "risk_level": "Low", "required_connections": [], "service_type": None,
        },
    }


@pytest.mark.asyncio
async def test_confirm_malformed_skill_isolated():
    # confirm = 신뢰 경계: staging 키 누락 → E_SKILL_INVALID 격리, 유효 스킬은 계속 처리
    draft = _FakeCreateDraftSkill()
    bad = {"node_type": "bad", "name": "x", "description": "y"}  # staging 키 없음
    skills = [bad, _valid_skill()]

    frames = [f async for f in _make_uc(draft=draft).confirm(uuid4(), skills)]

    assert any(isinstance(f, ErrorFrame) and f.code == "E_SKILL_INVALID" for f in frames)
    result = frames[-1]
    assert result.payload["created_count"] == 1   # 유효 1건만 생성
    assert result.payload["failed_count"] == 1
    assert len(draft.calls) == 1


@pytest.mark.asyncio
async def test_confirm_bad_category_isolated():
    # 사용자가 category를 DB CHECK 8영문 밖 값으로 편집 → E_SKILL_INVALID (extract와 동일 검증)
    draft = _FakeCreateDraftSkill()
    bad = _valid_skill()
    bad["staging"]["category"] = "not_a_category"
    frames = [f async for f in _make_uc(draft=draft).confirm(uuid4(), [bad])]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_SKILL_INVALID" for f in frames)
    assert draft.calls == []   # 검증 실패 → 생성 안 함


@pytest.mark.asyncio
async def test_confirm_embed_failure_isolated():
    embedder = _FakeEmbedder(raise_on_call=RuntimeError("embed down"))
    draft = _FakeCreateDraftSkill()
    frames = [f async for f in _make_uc(draft=draft, embedder=embedder).confirm(uuid4(), [_valid_skill()])]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_EMBEDDING_FAILED" for f in frames)
    assert frames[-1].payload["created_count"] == 0
    assert draft.calls == []   # embed 실패 → create_draft 미호출


@pytest.mark.asyncio
async def test_confirm_create_draft_failure_isolated():
    draft = _FakeCreateDraftSkill(raise_on_call=RuntimeError("db down"))
    frames = [f async for f in _make_uc(draft=draft).confirm(uuid4(), [_valid_skill()])]
    assert any(isinstance(f, ErrorFrame) and f.code == "E_CREATE_DRAFT_FAILED" for f in frames)
    assert frames[-1].payload["failed_count"] == 1
