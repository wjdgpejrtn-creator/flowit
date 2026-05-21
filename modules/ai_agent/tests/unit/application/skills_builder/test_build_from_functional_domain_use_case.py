"""BuildFromFunctionalDomainUseCase unit test.

REQ-004 spec §2.2 확장 (2026-05-12 조장 합의로 추가).
활성 직무 영역 5종: customer_support / it_ops / document_data / hr / marketing.
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ai_agent.application.agents.skills_builder.build_from_functional_domain_use_case import (
    BuildFromFunctionalDomainUseCase,
)


# ----------------------------------------------------------------------
# Fakes
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


# ----------------------------------------------------------------------
# 5종 활성 직무 영역 정상 실행
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "domain_code",
    ["customer_support", "it_ops", "document_data", "hr", "marketing"],
)
async def test_execute_each_domain_upserts_all_skill_nodes(domain_code: str):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromFunctionalDomainUseCase(repo, embedder)

    user_id = uuid4()
    frames = [f async for f in use_case.execute(user_id, domain_code)]

    # 첫 프레임: load_functional_domain
    assert isinstance(frames[0], AgentNodeFrame)
    assert frames[0].agent_node_name == "skills_builder.load_functional_domain"

    # 마지막 프레임: ResultFrame
    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.intent == "build_skill"
    assert result.payload["source_type"] == "functional_domain"
    assert result.payload["domain_code"] == domain_code
    assert result.payload["upserted_count"] >= 5

    assert len(repo.store) == result.payload["upserted_count"]
    assert len(embedder.calls) == result.payload["upserted_count"]


# ----------------------------------------------------------------------
# NodeDefinition 필드 검증
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upserted_nodes_have_correct_fields():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromFunctionalDomainUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "customer_support")]

    for node_def in repo.store.values():
        assert node_def.node_type.startswith("customer_support_")
        assert node_def.category in {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}
        assert node_def.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.RESTRICTED)
        assert node_def.is_mvp is False
        assert isinstance(node_def.required_connections, list)
        assert node_def.embedding is not None
        assert len(node_def.embedding) == 768
        assert node_def.input_schema.get("type") == "object"
        assert node_def.output_schema.get("type") == "object"


# ----------------------------------------------------------------------
# uuid5 namespace 격리 (functional vs industry vs sop)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_functional_node_id_uses_functional_prefix_namespace():
    """uuid5(_NS, f'functional:{domain_code}:{node_type}') — industry/sop와 다른 namespace."""
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    _ = [f async for f in use_case.execute(uuid4(), "hr")]

    # 모든 functional 노드는 동일 NS, "functional:{domain_code}:{node_type}" 키 사용
    # 즉 같은 node_type이 다른 source(industry/sop)에 있어도 다른 node_id 발생
    for node_def in repo.store.values():
        assert node_def.node_type.startswith("hr_")


@pytest.mark.asyncio
async def test_execute_twice_is_idempotent():
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    _ = [f async for f in use_case.execute(uuid4(), "marketing")]
    count_after_first = len(repo.store)

    _ = [f async for f in use_case.execute(uuid4(), "marketing")]
    count_after_second = len(repo.store)

    assert count_after_first == count_after_second


# ----------------------------------------------------------------------
# 에러 처리
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_domain_yields_error_frame():
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    frames = [f async for f in use_case.execute(uuid4(), "unknown_domain")]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_DOMAIN_NOT_SUPPORTED"
    assert len(repo.store) == 0


@pytest.mark.asyncio
async def test_missing_seed_file_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder(), seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "hr")]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_SEED_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_json_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    (tmp_path / "hr.json").write_text("{invalid", encoding="utf-8")
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder(), seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "hr")]

    assert frames[0].code == "E_SEED_INVALID_JSON"


@pytest.mark.asyncio
async def test_seed_entry_missing_field_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    seed = {
        "domain_code": "hr",
        "domain_name": "인사",
        "skill_nodes": [
            {
                "node_type": "hr_test",
                "name": "테스트",
                "category": "action",
                # description / inputs / outputs / risk_level 누락
            }
        ],
    }
    (tmp_path / "hr.json").write_text(json.dumps(seed), encoding="utf-8")
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder(), seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "hr")]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames
    assert error_frames[0].code == "E_SEED_ENTRY_INVALID"


# ----------------------------------------------------------------------
# 진행 프레임 + 산업/직무 충돌 회피
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_frames_emitted_per_skill_node():
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    frames = [f async for f in use_case.execute(uuid4(), "marketing")]

    upsert_frames = [f for f in frames if isinstance(f, AgentNodeFrame) and "upsert" in f.agent_node_name]
    assert len(upsert_frames) >= 5


@pytest.mark.asyncio
async def test_functional_it_ops_no_clash_with_legacy_it_industry():
    """it_ops 직무 영역 prefix는 it 산업 (비활성)와 다름 — node_type 충돌 없음."""
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    _ = [f async for f in use_case.execute(uuid4(), "it_ops")]

    for node_def in repo.store.values():
        assert node_def.node_type.startswith("it_ops_")
        # 비활성 it 산업 prefix "it_" 와 명확히 구분
        assert not node_def.node_type.startswith("it_deploy")  # 비활성 it 산업 노드명 아님


# ----------------------------------------------------------------------
# 부분 실패 격리 정책 (PR #44 BuildFromIndustryDefaultUseCase 패턴 동일)
# ----------------------------------------------------------------------


class _FailingEmbedder(EmbedderPort):
    """N번째 호출에서 실패 — embed 격리 정책 검증용."""

    def __init__(self, fail_at: int = 2) -> None:
        self.calls = 0
        self.fail_at = fail_at

    async def embed(self, text: str) -> list[float]:
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError(f"embed simulated failure at call #{self.calls}")
        return [0.1] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in texts]


class _FailingRepo(NodeDefinitionRepository):
    """N번째 upsert에서 실패 — upsert 격리 정책 검증용."""

    def __init__(self, fail_at: int = 2) -> None:
        self.store: dict[UUID, NodeDefinition] = {}
        self.calls = 0
        self.fail_at = fail_at

    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError(f"upsert simulated failure at call #{self.calls}")
        self.store[definition.node_id] = definition
        return definition

    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        return list(self.store.values())

    async def get_by_id(self, node_id: UUID) -> NodeDefinition | None:
        return self.store.get(node_id)

    async def search_by_embedding(self, query_embedding: list[float], limit: int = 10) -> list[NodeDefinition]:
        return list(self.store.values())[:limit]


@pytest.mark.asyncio
async def test_embed_failure_isolates_single_node():
    """embed 실패 → 해당 노드만 스킵, 나머지 계속, failed_node_types 기록."""
    repo = _InMemoryRepo()
    embedder = _FailingEmbedder(fail_at=2)  # 2번째 노드 embed 실패
    use_case = BuildFromFunctionalDomainUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "hr")]
    result = frames[-1]

    assert isinstance(result, ResultFrame)
    assert result.payload["failed_count"] == 1
    assert len(result.payload["failed_node_types"]) == 1
    assert result.payload["failed_node_types"][0]["stage"] == "embed"
    # 다른 노드는 정상 upsert (5종 중 1개 실패 → 최소 4개 성공)
    assert result.payload["upserted_count"] >= 4

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert any(f.code == "E_EMBEDDING_FAILED" for f in error_frames)


@pytest.mark.asyncio
async def test_upsert_failure_isolates_single_node():
    """upsert 실패 → 해당 노드만 스킵, 나머지 계속, failed_node_types 기록."""
    repo = _FailingRepo(fail_at=3)  # 3번째 upsert 실패
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    frames = [f async for f in use_case.execute(uuid4(), "hr")]
    result = frames[-1]

    assert isinstance(result, ResultFrame)
    assert result.payload["failed_count"] == 1
    assert result.payload["failed_node_types"][0]["stage"] == "upsert"
    assert result.payload["upserted_count"] >= 4

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert any(f.code == "E_UPSERT_FAILED" for f in error_frames)


@pytest.mark.asyncio
async def test_result_frame_has_failed_fields_in_normal_case():
    """정상 케이스에도 failed_count + failed_node_types 필드 존재."""
    repo = _InMemoryRepo()
    use_case = BuildFromFunctionalDomainUseCase(repo, _FakeEmbedder())

    frames = [f async for f in use_case.execute(uuid4(), "marketing")]
    result = frames[-1]

    assert isinstance(result, ResultFrame)
    assert result.payload["failed_count"] == 0
    assert result.payload["failed_node_types"] == []


# ----------------------------------------------------------------------
# SkillDocument 생성 (ADR-0017 — seed instructions → skill_documents)
# ----------------------------------------------------------------------


def _write_seed(tmp_path: Path, domain_code: str = "hr", *, with_instructions: bool) -> Path:
    """instructions 필드를 선택적으로 포함하는 테스트 seed 생성."""
    node = {
        "node_type": "hr_onboarding_notify",
        "name": "온보딩 알림",
        "category": "action",
        "description": "신규 입사자 온보딩 알림 발송",
        "inputs": {"type": "object", "properties": {"employee_id": {"type": "string"}}},
        "outputs": {"type": "object", "properties": {"sent": {"type": "boolean"}}},
        "risk_level": "Low",
        "required_connections": ["slack"],
        "service_type": "slack",
    }
    if with_instructions:
        node["instructions"] = "## When to use\n신규 입사자 등록 시.\n## Steps\n1. 온보딩 체크리스트 발송"
    seed = {"domain_code": domain_code, "domain_name": "인사", "skill_nodes": [node]}
    (tmp_path / f"{domain_code}.json").write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_seed_instructions_included_in_skill_documents(tmp_path: Path):
    """seed에 instructions가 있으면 ResultFrame.payload['skill_documents']에 포함 (ADR-0017)."""
    seeds = _write_seed(tmp_path, "hr", with_instructions=True)
    use_case = BuildFromFunctionalDomainUseCase(_InMemoryRepo(), _FakeEmbedder(), seeds_dir=seeds)

    frames = [f async for f in use_case.execute(uuid4(), "hr")]
    result = frames[-1]

    docs = result.payload["skill_documents"]
    assert len(docs) == 1
    assert docs[0]["node_type"] == "hr_onboarding_notify"
    assert docs[0]["instructions"].startswith("## When to use")
    assert "name" in docs[0]
    assert "description" in docs[0]


@pytest.mark.asyncio
async def test_seed_without_instructions_empty_skill_documents(tmp_path: Path):
    """seed에 instructions 없으면 skill_documents 비어있음 (② 채우기 전 기존 동작 유지)."""
    seeds = _write_seed(tmp_path, "hr", with_instructions=False)
    use_case = BuildFromFunctionalDomainUseCase(_InMemoryRepo(), _FakeEmbedder(), seeds_dir=seeds)

    frames = [f async for f in use_case.execute(uuid4(), "hr")]
    result = frames[-1]

    assert result.payload["upserted_count"] == 1   # NodeDefinition은 정상 upsert
    assert result.payload["skill_documents"] == []  # instructions 없으니 SkillDocument 미생성


@pytest.mark.asyncio
async def test_real_seed_still_works_without_instructions():
    """실제 seed(instructions 미포함)도 깨지지 않음 — NodeDefinition upsert + skill_documents 비움."""
    use_case = BuildFromFunctionalDomainUseCase(_InMemoryRepo(), _FakeEmbedder())

    frames = [f async for f in use_case.execute(uuid4(), "customer_support")]
    result = frames[-1]

    assert result.payload["upserted_count"] >= 5
    assert result.payload["skill_documents"] == []  # 실제 seed엔 아직 instructions 없음 (② 후 채워짐)
