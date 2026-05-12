"""BuildFromIndustryDefaultUseCase unit test.

REQ-004 spec §2.2: 산업 default seed → NodeDefinition upsert.
LLM 비의존이라 단위 테스트 가능 (NodeDefinitionRepository mock + Fake Embedder).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
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


# 실제 seed 디렉토리 (production data 사용)
_SEEDS_DIR = Path(__file__).resolve().parents[4] / "seeds" / "industry_defaults"


# ----------------------------------------------------------------------
# 각 산업 정상 실행
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("industry_code", ["manufacturing", "service", "wholesale_retail", "food", "it"])
async def test_execute_each_industry_upserts_all_skill_nodes(industry_code: str):
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
# 등록된 NodeDefinition 필드 검증
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upserted_nodes_have_correct_fields():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "manufacturing")]

    for node_def in repo.store.values():
        assert node_def.node_type.startswith("manufacturing_")
        assert node_def.category in {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}
        assert node_def.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.RESTRICTED)
        assert node_def.is_mvp is False  # 산업 default = MVP 아님
        assert isinstance(node_def.required_connections, list)
        assert node_def.embedding is not None
        assert len(node_def.embedding) == 768  # BGE-M3 차원
        assert node_def.input_schema.get("type") == "object"
        assert node_def.output_schema.get("type") == "object"


# ----------------------------------------------------------------------
# Idempotency (같은 input은 같은 node_id 생성 → upsert 덮어쓰기)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_twice_is_idempotent():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "it")]
    count_after_first = len(repo.store)

    _ = [f async for f in use_case.execute(uuid4(), "it")]
    count_after_second = len(repo.store)

    assert count_after_first == count_after_second, "uuid5 deterministic — 2회 호출 후에도 노드 수 동일"


# ----------------------------------------------------------------------
# 에러 처리
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_industry_yields_error_frame():
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
    # 비어있는 seeds 디렉토리 사용
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder, seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "manufacturing")]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_SEED_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_json_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    # 깨진 JSON 파일 생성
    (tmp_path / "manufacturing.json").write_text("{invalid json", encoding="utf-8")
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder, seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "manufacturing")]

    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "E_SEED_INVALID_JSON"


@pytest.mark.asyncio
async def test_seed_entry_missing_field_yields_error_frame(tmp_path: Path):
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    # 필수 필드 누락 entry
    seed = {
        "industry_code": "manufacturing",
        "industry_name": "제조",
        "skill_nodes": [
            {
                "node_type": "manufacturing_test",
                "name": "테스트",
                # description, inputs, outputs, risk_level 누락
                "category": "action",
            }
        ],
    }
    (tmp_path / "manufacturing.json").write_text(json.dumps(seed), encoding="utf-8")
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder, seeds_dir=tmp_path)

    frames = [f async for f in use_case.execute(uuid4(), "manufacturing")]

    # load 프레임 1개 + 에러 프레임 1개 (구현에 따라 다를 수 있음)
    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert error_frames, "필수 필드 누락 시 ErrorFrame 발생해야 함"
    assert error_frames[0].code == "E_SEED_ENTRY_INVALID"


# ----------------------------------------------------------------------
# 진행 프레임 (upsert별)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_frames_emitted_per_skill_node():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "food")]

    upsert_frames = [f for f in frames if isinstance(f, AgentNodeFrame) and "upsert" in f.agent_node_name]
    assert len(upsert_frames) >= 5  # food.json은 5개 SkillNode


# ----------------------------------------------------------------------
# Embedder 호출 확인
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embedder_called_with_description():
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    _ = [f async for f in use_case.execute(uuid4(), "service")]

    # 각 SkillNode description으로 embedder 호출
    assert len(embedder.calls) == len(repo.store)
    # 호출된 텍스트가 비어있지 않음
    for text in embedder.calls:
        assert text
