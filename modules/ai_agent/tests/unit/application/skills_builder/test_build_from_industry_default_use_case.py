"""BuildFromIndustryDefaultUseCase unit test.

REQ-004 spec §2.2: 산업 default seed → NodeDefinition upsert.
LLM 비의존이라 단위 테스트 가능 (NodeDefinitionRepository mock + Fake Embedder).

활성 산업: ecommerce (2026-05-12 조장 합의)
비활성: manufacturing/service/wholesale_retail/food/it (seed 파일 보존, 호출 막힘)
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

from ai_agent.application.agents.skills_builder.build_from_industry_default_use_case import (
    BuildFromIndustryDefaultUseCase,
)


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
        nodes = list(self.store.values())
        return [n for n in nodes if n.is_mvp] if mvp_only else nodes

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


_SEEDS_DIR = Path(__file__).resolve().parents[4] / "seeds" / "industry_defaults"


# ----------------------------------------------------------------------
# 활성 산업 (ecommerce) 정상 실행
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("industry_code", ["ecommerce"])
async def test_execute_active_industry_upserts_all_skill_nodes(industry_code: str):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    user_id = uuid4()
    frames = [f async for f in use_case.execute(user_id, industry_code)]

    # 첫 프레임: load_industry_default
    assert isinstance(frames[0], AgentNodeFrame)
    assert frames[0].agent_node_name == "skills_builder.load_industry_default"

    # 마지막 프레임: ResultFrame
    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.intent == "build_skill"
    assert result.payload["industry_code"] == industry_code
    assert result.payload["upserted_count"] >= 5

    # 모든 노드가 upsert됨
    assert len(repo.store) == result.payload["upserted_count"]
    assert len(embedder.calls) == result.payload["upserted_count"]


# ----------------------------------------------------------------------
# 비활성 산업 (deprecated 5종) — E_INDUSTRY_DEACTIVATED
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "industry_code",
    ["manufacturing", "service", "wholesale_retail", "food", "it"],
)
async def test_deprecated_industries_yield_deactivated_error(industry_code: str):
    """Sprint 3 v1 베타 5종은 비활성. 호출 시 E_INDUSTRY_DEACTIVATED. seed 파일은 유지."""
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), industry_code)]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_INDUSTRY_DEACTIVATED"
    assert industry_code in frames[0].message
    assert "ecommerce" in frames[0].message  # 활성 산업 안내
    # repo에 upsert 없음
    assert len(repo.store) == 0
    # embedder 호출 없음
    assert len(embedder.calls) == 0


@pytest.mark.parametrize(
    "industry_code",
    ["manufacturing", "service", "wholesale_retail", "food", "it"],
)
def test_deprecated_seed_files_still_exist_on_disk(industry_code: str):
    """비활성 산업 seed JSON은 삭제하지 않음 (히스토리/복원용)."""
    path = _SEEDS_DIR / f"{industry_code}.json"
    assert path.exists(), f"비활성 산업 seed 파일도 보존되어야 함: {path}"


# ----------------------------------------------------------------------
# 등록된 NodeDefinition 필드 검증
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upserted_nodes_have_correct_fields():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "ecommerce")]

    for node_def in repo.store.values():
        assert node_def.node_type.startswith("ecommerce_")
        assert node_def.category in {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}
        assert node_def.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.RESTRICTED)
        assert node_def.is_mvp is False
        assert isinstance(node_def.required_connections, list)
        assert node_def.embedding is not None
        assert len(node_def.embedding) == 768
        assert node_def.input_schema.get("type") == "object"
        assert node_def.output_schema.get("type") == "object"


# ----------------------------------------------------------------------
# Idempotency
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_twice_is_idempotent():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "ecommerce")]
    count_after_first = len(repo.store)

    _ = [f async for f in use_case.execute(uuid4(), "ecommerce")]
    count_after_second = len(repo.store)

    assert count_after_first == count_after_second, "uuid5 deterministic — 2회 호출 후에도 노드 수 동일"


# ----------------------------------------------------------------------
# 에러 처리 — 미지원 / 파일 누락 / JSON 파싱 / 항목 검증
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_industry_yields_error_frame():
    """deprecated도 아닌 완전 미등록 코드 → E_INDUSTRY_NOT_SUPPORTED."""
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "unknown_industry")]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_INDUSTRY_NOT_SUPPORTED"
    assert len(repo.store) == 0


@pytest.mark.asyncio
async def test_missing_seed_file_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder, seeds_dir=tmp_path)

    # 활성 산업이라도 파일 없으면 E_SEED_NOT_FOUND
    frames = [f async for f in use_case.execute(uuid4(), "ecommerce")]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_SEED_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_json_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    (tmp_path / "ecommerce.json").write_text("{invalid json", encoding="utf-8")
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder, seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "ecommerce")]

    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_SEED_INVALID_JSON"


@pytest.mark.asyncio
async def test_seed_entry_missing_field_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    seed = {
        "industry_code": "ecommerce",
        "industry_name": "이커머스",
        "skill_nodes": [
            {
                "node_type": "ecommerce_test",
                "name": "테스트",
                # description, inputs, outputs, risk_level 누락
                "category": "action",
            }
        ],
    }
    (tmp_path / "ecommerce.json").write_text(json.dumps(seed), encoding="utf-8")
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder, seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "ecommerce")]

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames, "필수 필드 누락 시 ErrorFrame 발생해야 함"
    assert error_frames[0].code == "E_SEED_ENTRY_INVALID"


# ----------------------------------------------------------------------
# 진행 프레임 + Embedder 호출
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_frames_emitted_per_skill_node():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "ecommerce")]

    upsert_frames = [f for f in frames if isinstance(f, AgentNodeFrame) and "upsert" in f.agent_node_name]
    assert len(upsert_frames) >= 5  # ecommerce.json은 5개 SkillNode


@pytest.mark.asyncio
async def test_embedder_called_with_description():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "ecommerce")]

    assert len(embedder.calls) == len(repo.store)
    for text in embedder.calls:
        assert text
