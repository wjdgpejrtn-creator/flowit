"""BuildFromSOPUseCase skeleton unit test.

REQ-004 spec §2.2: SOP DocumentBlock → LLM → SkillNode → NodeDefinition upsert.
LLM 의존 작업의 skeleton — LLM Mock으로 단위 테스트 가능.
실제 LLM endpoint(`llm-base` Modal) 배포 후 wiring만 하면 production-ready.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from common_schemas import ContentBlock, DocumentBlock, FileMeta, ParserMeta
from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ai_agent.application.agents.skills_builder.build_from_sop_use_case import (
    BuildFromSOPUseCase,
    _ExtractedSkillNode,
    _ExtractedSkillNodeList,
)
from common_schemas import MemoryEntry

from ai_agent.domain.ports.llm_port import LLMPort


# ----------------------------------------------------------------------
# Fakes (inline 헬퍼 — conftest 미사용 정책)
# ----------------------------------------------------------------------


class _InMemoryRepo(NodeDefinitionRepository):
    def __init__(self) -> None:
        self.store: dict[UUID, NodeDefinition] = {}

    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        self.store[definition.node_id] = definition
        return definition

    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        return list(self.store.values())

    async def get_by_id(self, node_id: UUID) -> NodeDefinition | None:
        return self.store.get(node_id)

    async def search_by_embedding(self, query_embedding: list[float], limit: int = 10) -> list[NodeDefinition]:
        return list(self.store.values())[:limit]


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
    """반환값을 미리 설정하는 LLM mock."""

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
    """테스트용 DocumentBlock 생성."""
    if blocks is None:
        blocks = [
            ContentBlock(
                block_id=uuid4(),
                block_type="heading",
                content="고객 응대 SOP",
                page=1,
            ),
            ContentBlock(
                block_id=uuid4(),
                block_type="text",
                content="1. 고객 문의 접수 시 Slack 알림 발송. 2. 1시간 내 미응답이면 매니저에게 에스컬레이션.",
                page=1,
            ),
        ]
    return DocumentBlock(
        document_id=uuid4(),
        file_meta=FileMeta(
            file_name="customer_support_sop.pdf",
            file_type="pdf",
            mime_type="application/pdf",
            file_size=2048,
            page_count=1,
        ),
        parser=ParserMeta(parser_name="pdfplumber", parser_version="0.10.0"),
        blocks=blocks,
    )


def _make_extracted(
    *,
    node_type: str = "sop_customer_inquiry_slack_alert",
    category: str = "action",
    risk_level: str = "Medium",
    required_connections: list[str] | None = None,
    service_type: str | None = "slack",
    instructions: str = "## When to use\n고객 문의 접수 시.\n## Steps\n1. Slack 채널 확인\n2. 알림 발송",
) -> _ExtractedSkillNode:
    """LLM이 추출한 가상 SkillNode 1건."""
    return _ExtractedSkillNode(
        node_type=node_type,
        name="고객 문의 Slack 알림",
        description="고객 문의 접수 시 Slack 채널로 알림 메시지 발송",
        category=category,
        risk_level=risk_level,
        inputs={
            "type": "object",
            "properties": {"channel": {"type": "string"}, "message": {"type": "string"}},
            "required": ["channel", "message"],
        },
        outputs={
            "type": "object",
            "properties": {"ts": {"type": "string"}},
        },
        required_connections=required_connections or ["slack"],
        service_type=service_type,
        instructions=instructions,
    )


# ----------------------------------------------------------------------
# 정상 흐름
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_upserts_all_extracted_skill_nodes():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(
        skill_nodes=[
            _make_extracted(node_type="sop_alert_slack"),
            _make_extracted(node_type="sop_escalate_manager", service_type="google_workspace", required_connections=["google"]),
        ],
    ))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    document = _make_document()
    frames = [f async for f in use_case.execute(uuid4(), document)]

    # ResultFrame 최종
    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.intent == "build_skill"
    assert result.payload["source_type"] == "sop"
    assert result.payload["document_id"] == str(document.document_id)
    assert result.payload["upserted_count"] == 2
    assert result.payload["failed_count"] == 0
    assert len(repo.store) == 2
    assert len(embedder.calls) == 2


@pytest.mark.asyncio
async def test_progress_frames_emitted():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(
        skill_nodes=[_make_extracted()],
    ))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    agent_node_frames = [f for f in frames if isinstance(f, AgentNodeFrame)]
    names = {f.agent_node_name for f in agent_node_frames}
    assert "skills_builder.sop.parse_document" in names
    assert "skills_builder.sop.llm_extract" in names
    assert any(n.startswith("skills_builder.sop.upsert.") for n in names)


# ----------------------------------------------------------------------
# NodeDefinition 필드 검증
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upserted_nodes_have_correct_fields():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(
        skill_nodes=[_make_extracted()],
    ))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    _ = [f async for f in use_case.execute(uuid4(), _make_document())]

    node_def = next(iter(repo.store.values()))
    assert node_def.node_type == "sop_customer_inquiry_slack_alert"
    assert node_def.category == "action"
    assert node_def.risk_level == RiskLevel.MEDIUM
    assert node_def.is_mvp is False
    assert node_def.required_connections == ["slack"]
    assert node_def.service_type == "slack"
    assert node_def.embedding is not None
    assert len(node_def.embedding) == 768


@pytest.mark.asyncio
async def test_node_id_includes_document_id_namespace():
    """uuid5(_NS, f'sop:{document_id}:{node_type}') — 다른 문서면 다른 node_id."""
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()

    doc_a = _make_document()
    doc_b = _make_document()  # 다른 document_id
    extracted = _ExtractedSkillNodeList(skill_nodes=[_make_extracted(node_type="sop_same_name")])

    use_case = BuildFromSOPUseCase(repo, embedder, _FakeLLM(structured_response=extracted))
    _ = [f async for f in use_case.execute(uuid4(), doc_a)]

    repo_b = _InMemoryRepo()
    use_case_b = BuildFromSOPUseCase(repo_b, _FakeEmbedder(), _FakeLLM(structured_response=extracted))
    _ = [f async for f in use_case_b.execute(uuid4(), doc_b)]

    a_ids = set(repo.store.keys())
    b_ids = set(repo_b.store.keys())
    assert not (a_ids & b_ids), "같은 node_type이라도 다른 SOP면 다른 node_id 생성"


# ----------------------------------------------------------------------
# 에러 처리
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_document_yields_error():
    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    document = _make_document(blocks=[])
    frames = [f async for f in use_case.execute(uuid4(), document)]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_DOCUMENT_EMPTY"


@pytest.mark.asyncio
async def test_llm_failure_yields_error():
    repo = _InMemoryRepo()
    llm = _FakeLLM(raise_on_call=RuntimeError("Modal LLM endpoint timeout"))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames
    assert error_frames[0].code == "E_LLM_GENERATION_FAILED"


@pytest.mark.asyncio
async def test_llm_returns_wrong_type_yields_error():
    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response="not a SkillNodeList")  # str 반환
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames
    assert error_frames[0].code == "E_LLM_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_llm_returns_empty_skills_yields_error():
    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames
    assert error_frames[0].code == "E_NO_SKILLS_EXTRACTED"


@pytest.mark.asyncio
async def test_invalid_category_in_llm_response_yields_error():
    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(
        skill_nodes=[_make_extracted(category="invalid_category")],
    ))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames
    assert error_frames[0].code == "E_LLM_RESPONSE_INVALID"
    assert "category" in error_frames[0].message


@pytest.mark.asyncio
async def test_invalid_risk_level_in_llm_response_yields_error():
    """Pydantic SkillNode validation 실패 → ValueError → E_LLM_RESPONSE_INVALID."""
    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(
        skill_nodes=[_make_extracted(risk_level="InvalidLevel")],
    ))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames
    assert error_frames[0].code == "E_LLM_RESPONSE_INVALID"


# ----------------------------------------------------------------------
# 부분 실패 격리 (embed/upsert 단계)
# ----------------------------------------------------------------------


class _FailingEmbedder(EmbedderPort):
    def __init__(self, fail_on_substring: str) -> None:
        self._fail_on = fail_on_substring
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._fail_on in text:
            raise RuntimeError("BGE-M3 endpoint timeout (테스트)")
        return [0.1] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class _FailingRepo(NodeDefinitionRepository):
    def __init__(self, fail_on_node_type: str) -> None:
        self._fail_on = fail_on_node_type
        self.store: dict[UUID, NodeDefinition] = {}

    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        if definition.node_type == self._fail_on:
            raise RuntimeError("DB connection lost (테스트)")
        self.store[definition.node_id] = definition
        return definition

    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        return list(self.store.values())

    async def get_by_id(self, node_id: UUID) -> NodeDefinition | None:
        return self.store.get(node_id)

    async def search_by_embedding(self, query_embedding: list[float], limit: int = 10) -> list[NodeDefinition]:
        return list(self.store.values())[:limit]


@pytest.mark.asyncio
async def test_embedder_failure_isolated_other_nodes_continue():
    repo = _InMemoryRepo()
    embedder = _FailingEmbedder(fail_on_substring="에스컬레이션")
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[
        _make_extracted(node_type="sop_normal_alert"),  # 정상
        _ExtractedSkillNode(  # 실패 유도 (description에 "에스컬레이션")
            node_type="sop_manager_escalate",
            name="매니저 에스컬레이션",
            description="1시간 미응답 시 매니저 에스컬레이션 처리",
            category="action",
            risk_level="High",
            inputs={"type": "object", "properties": {}},
            outputs={"type": "object", "properties": {}},
            required_connections=["slack"],
            service_type="slack",
            instructions="## When to use\n1시간 미응답 시.\n## Steps\n1. 매니저에게 에스컬레이션",
        ),
    ]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.payload["upserted_count"] == 1
    assert result.payload["failed_count"] == 1
    assert result.payload["failed_node_types"][0]["stage"] == "embed"
    assert result.payload["failed_node_types"][0]["node_type"] == "sop_manager_escalate"


@pytest.mark.asyncio
async def test_upsert_failure_isolated_other_nodes_continue():
    repo = _FailingRepo(fail_on_node_type="sop_fail_target")
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[
        _make_extracted(node_type="sop_normal_a"),
        _make_extracted(node_type="sop_fail_target"),
        _make_extracted(node_type="sop_normal_b"),
    ]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.payload["upserted_count"] == 2
    assert result.payload["failed_count"] == 1
    assert result.payload["failed_node_types"][0]["stage"] == "upsert"
    assert result.payload["failed_node_types"][0]["node_type"] == "sop_fail_target"


# ----------------------------------------------------------------------
# JSON 프롬프트 + personal_memory 포함
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_includes_document_blocks_and_personal_memory_as_json():
    """LLM 프롬프트는 JSON 형식이어야 함 (XML 금지 — 메모리 룰)."""
    import json as _json

    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    document = _make_document()
    personal_memory = [
        MemoryEntry(
            user_id=uuid4(),
            memory_type="workflow_pattern",
            content="사용자는 Slack 알림을 선호함",
        ),
    ]

    _ = [f async for f in use_case.execute(uuid4(), document, personal_memory=personal_memory)]

    # LLM이 받은 prompt가 valid JSON이어야 함 (XML 금지 룰)
    assert len(llm.received_prompts) == 1
    prompt_text = llm.received_prompts[0]

    parsed = _json.loads(prompt_text)
    assert "instruction" in parsed
    assert "personal_memory" in parsed
    assert "document" in parsed
    assert len(parsed["personal_memory"]) == 1
    assert parsed["personal_memory"][0]["memory_type"] == "workflow_pattern"
    assert parsed["document"]["file_name"] == document.file_meta.file_name

    # XML 사용 금지 검증
    assert "<?xml" not in prompt_text
    assert "<skill_nodes>" not in prompt_text


@pytest.mark.asyncio
async def test_prompt_filters_blocks_to_text_heading_table_only():
    """이미지/코드 블록은 프롬프트에서 제외 (LLM이 의미 추출 못 함)."""
    import json as _json

    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    document = _make_document(blocks=[
        ContentBlock(block_id=uuid4(), block_type="heading", content="title"),
        ContentBlock(block_id=uuid4(), block_type="text", content="body"),
        ContentBlock(block_id=uuid4(), block_type="table", table=[["a", "b"], ["1", "2"]]),
        ContentBlock(block_id=uuid4(), block_type="image"),  # 제외 대상
        ContentBlock(block_id=uuid4(), block_type="code", content="print()"),  # 제외 대상
    ])

    _ = [f async for f in use_case.execute(uuid4(), document)]

    prompt = llm.received_prompts[0]
    parsed = _json.loads(prompt)
    block_types_in_prompt = [b["block_type"] for b in parsed["document"]["blocks"]]
    assert block_types_in_prompt == ["heading", "text", "table"]
    assert "image" not in block_types_in_prompt
    assert "code" not in block_types_in_prompt


@pytest.mark.asyncio
async def test_schema_passed_to_llm_is_extracted_skill_node_list():
    """LLM에 _ExtractedSkillNodeList 스키마 전달 확인."""
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    _ = [f async for f in use_case.execute(uuid4(), _make_document())]

    assert len(llm.received_schemas) == 1
    assert llm.received_schemas[0] is _ExtractedSkillNodeList


# ----------------------------------------------------------------------
# personal_memory 옵션
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_without_personal_memory_works():
    """personal_memory=None일 때도 빈 list로 처리되어 정상 실행."""
    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.payload["upserted_count"] == 1


# ----------------------------------------------------------------------
# 프롬프트 강화 — few-shot 예시 + 명시적 출력 스키마
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_includes_few_shot_example():
    """LLM 응답 품질 향상을 위한 few-shot 예시 1건 포함 (action + condition 카테고리 다양성)."""
    import json as _json

    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    _ = [f async for f in use_case.execute(uuid4(), _make_document())]

    parsed = _json.loads(llm.received_prompts[0])
    assert "few_shot_example" in parsed
    example = parsed["few_shot_example"]
    assert "input_sop_snippet" in example
    assert "expected_output" in example
    assert "skill_nodes" in example["expected_output"]

    # 예시 SkillNode 2개 이상 (다양한 카테고리 시연)
    example_nodes = example["expected_output"]["skill_nodes"]
    assert len(example_nodes) >= 2
    example_categories = {n["category"] for n in example_nodes}
    assert len(example_categories) >= 2, "few-shot 예시는 카테고리 다양성 보여야 함"


@pytest.mark.asyncio
async def test_prompt_includes_explicit_output_schema():
    """output_schema가 LLM grammar-level 강제와 호환되도록 완전 명세 포함."""
    import json as _json

    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    _ = [f async for f in use_case.execute(uuid4(), _make_document())]

    parsed = _json.loads(llm.received_prompts[0])
    assert "output_schema" in parsed

    schema = parsed["output_schema"]
    assert schema["type"] == "object"
    assert "skill_nodes" in schema["properties"]

    # SkillNode items 스키마가 모든 필수 필드 명시
    item_schema = schema["properties"]["skill_nodes"]["items"]
    expected_fields = {"node_type", "name", "description", "category", "risk_level", "inputs", "outputs", "required_connections"}
    assert set(item_schema["properties"].keys()) >= expected_fields, (
        f"output_schema의 SkillNode 필드 누락: {expected_fields - set(item_schema['properties'].keys())}"
    )

    # category enum이 DB CHECK 8영문과 일치
    assert set(item_schema["properties"]["category"]["enum"]) == {
        "trigger", "action", "condition", "transform", "ai", "integration", "utility", "output",
    }

    # risk_level enum이 RiskLevel과 일치
    assert set(item_schema["properties"]["risk_level"]["enum"]) == {"Low", "Medium", "High", "Restricted"}


@pytest.mark.asyncio
async def test_few_shot_example_categories_are_valid():
    """few-shot 예시의 category는 DB CHECK 8영문 안에 있어야 함 (LLM이 잘못 학습 안 하도록)."""
    import json as _json

    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    _ = [f async for f in use_case.execute(uuid4(), _make_document())]

    parsed = _json.loads(llm.received_prompts[0])
    allowed = {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}

    for example_node in parsed["few_shot_example"]["expected_output"]["skill_nodes"]:
        assert example_node["category"] in allowed
        assert example_node["risk_level"] in {"Low", "Medium", "High", "Restricted"}


# ----------------------------------------------------------------------
# SkillDocument 생성 (ADR-0017 — LLM이 instructions(SKILL.md) 동시 생성)
# ----------------------------------------------------------------------


def test_extracted_skill_node_has_instructions_field():
    """_ExtractedSkillNode에 instructions(SKILL.md markdown body) 필드 존재 (ADR-0017)."""
    ext = _make_extracted(instructions="## When to use\n환불 요청 시.\n## Steps\n1. 검증")
    assert ext.instructions == "## When to use\n환불 요청 시.\n## Steps\n1. 검증"


@pytest.mark.asyncio
async def test_prompt_requests_skill_document_instructions():
    """프롬프트가 LLM에 instructions(markdown 지침서) 생성을 요청 (ADR-0017 이중 저장)."""
    import json as _json

    repo = _InMemoryRepo()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[_make_extracted()]))
    use_case = BuildFromSOPUseCase(repo, _FakeEmbedder(), llm)

    _ = [f async for f in use_case.execute(uuid4(), _make_document())]

    parsed = _json.loads(llm.received_prompts[0])
    # output_schema의 SkillNode item에 instructions 필드 명시
    item_schema = parsed["output_schema"]["properties"]["skill_nodes"]["items"]
    assert "instructions" in item_schema["properties"]
    assert "instructions" in item_schema["required"]
    # instruction 텍스트에 지침서/SKILL.md 생성 지시 포함
    instruction_text = parsed["instruction"]
    assert "instructions" in instruction_text or "지침서" in instruction_text or "SKILL.md" in instruction_text


@pytest.mark.asyncio
async def test_result_payload_includes_skill_documents():
    """ResultFrame.payload['skill_documents']에 upsert 성공 노드의 SkillDocument 데이터 (ADR-0017)."""
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[
        _make_extracted(node_type="sop_alert", instructions="## When to use\nA\n## Steps\n1. x"),
        _make_extracted(node_type="sop_escalate", instructions="## When to use\nB"),
    ]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    docs = result.payload["skill_documents"]
    assert len(docs) == 2
    # SkillDocument 객체(model_dump) — node_type 없음(SkillDocument≠Node, 조장 결정), skill_id로 식별
    for d in docs:
        assert {"skill_id", "name", "description", "instructions"} <= d.keys()
        assert "node_type" not in d
    instructions_set = {d["instructions"] for d in docs}
    assert "## When to use\nA\n## Steps\n1. x" in instructions_set
    assert "## When to use\nB" in instructions_set


@pytest.mark.asyncio
async def test_skill_documents_exclude_failed_nodes():
    """upsert 실패 노드는 skill_documents에서 제외 (NodeDefinition 저장 실패 = 스킬 미성립)."""
    repo = _FailingRepo(fail_on_node_type="sop_fail")
    embedder = _FakeEmbedder()
    llm = _FakeLLM(structured_response=_ExtractedSkillNodeList(skill_nodes=[
        _make_extracted(node_type="sop_ok"),
        _make_extracted(node_type="sop_fail"),
    ]))
    use_case = BuildFromSOPUseCase(repo, embedder, llm)

    frames = [f async for f in use_case.execute(uuid4(), _make_document())]

    result = frames[-1]
    docs = result.payload["skill_documents"]
    # sop_fail upsert 실패 → SkillDocument 제외, sop_ok만 남음 (성공분만 수집)
    assert len(docs) == 1
    assert "node_type" not in docs[0]
    assert {"skill_id", "name", "description", "instructions"} <= docs[0].keys()
