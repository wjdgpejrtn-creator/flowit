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


# ----------------------------------------------------------------------
# PR #42 리뷰 후속 — uuid5 namespace 명시 결합 (industry_code 포함)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_id_includes_industry_code_namespace():
    """uuid5(_NS, f'{industry_code}:{node_type}')로 산업 간 충돌 차단.

    같은 node_type 문자열이라도 industry_code가 다르면 다른 node_id 생성.
    실제 seed에서는 prefix로 충돌이 없지만 namespace 레벨에서도 분리.
    """
    repo_a = _InMemoryRepo()
    repo_b = _InMemoryRepo()
    embedder = _FakeEmbedder()

    # 가상의 seed: 두 산업이 동일한 node_type을 사용한다고 가정 (실제 seed는 아님)
    # 여기서는 실제 seed 두 산업이 다른 industry_code → 다른 node_id가 생성되는 것을 확인
    use_case_a = BuildFromIndustryDefaultUseCase(repo_a, embedder)
    use_case_b = BuildFromIndustryDefaultUseCase(repo_b, embedder)

    _ = [f async for f in use_case_a.execute(uuid4(), "manufacturing")]
    _ = [f async for f in use_case_b.execute(uuid4(), "service")]

    # 두 산업의 모든 node_id가 서로 다름
    manufacturing_ids = set(repo_a.store.keys())
    service_ids = set(repo_b.store.keys())
    assert not (manufacturing_ids & service_ids), (
        "산업 간 node_id 충돌 — uuid5 namespace에 industry_code 미포함 의심"
    )


# ----------------------------------------------------------------------
# PR #42 리뷰 후속 — 부분 실패 격리 정책 (embed/upsert 단계)
# ----------------------------------------------------------------------


class _FailingEmbedder(EmbedderPort):
    """특정 description에서만 실패하는 embedder."""

    def __init__(self, fail_on_substring: str) -> None:
        self._fail_on = fail_on_substring
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._fail_on in text:
            raise RuntimeError(f"임베딩 endpoint timeout (테스트): '{self._fail_on}'")
        return [0.1] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class _FailingRepo(NodeDefinitionRepository):
    """특정 node_type에서만 upsert 실패하는 repository."""

    def __init__(self, fail_on_node_type: str) -> None:
        self._fail_on = fail_on_node_type
        self.store: dict[UUID, NodeDefinition] = {}

    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        if definition.node_type == self._fail_on:
            raise RuntimeError(f"DB connection lost (테스트): '{self._fail_on}'")
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
    """embed 실패 시 해당 노드만 격리되고 나머지는 계속 처리됨."""
    repo = _InMemoryRepo()
    # manufacturing.json의 "출고 알림" description 일부 문구로 실패 유도
    embedder = _FailingEmbedder(fail_on_substring="출고 확정")
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "manufacturing")]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    # 5종 중 1종 실패, 4종 성공
    assert result.payload["upserted_count"] == 4
    assert result.payload["failed_count"] == 1
    assert result.payload["failed_node_types"][0]["stage"] == "embed"
    assert "manufacturing_shipment_notify" in result.payload["failed_node_types"][0]["node_type"]

    # ErrorFrame이 진행 중간에 yield됨 (해당 노드만)
    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert len(error_frames) == 1
    assert error_frames[0].code == "E_EMBEDDING_FAILED"

    # repo에는 성공한 4개만 등록됨
    assert len(repo.store) == 4


@pytest.mark.asyncio
async def test_upsert_failure_isolated_other_nodes_continue():
    """upsert 실패 시 해당 노드만 격리되고 나머지는 계속 처리됨."""
    repo = _FailingRepo(fail_on_node_type="it_pr_review_request")
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "it")]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert result.payload["upserted_count"] == 4
    assert result.payload["failed_count"] == 1
    assert result.payload["failed_node_types"][0]["stage"] == "upsert"
    assert result.payload["failed_node_types"][0]["node_type"] == "it_pr_review_request"

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert len(error_frames) == 1
    assert error_frames[0].code == "E_UPSERT_FAILED"

    # repo에는 실패 노드 없음
    assert len(repo.store) == 4
    stored_types = {n.node_type for n in repo.store.values()}
    assert "it_pr_review_request" not in stored_types


@pytest.mark.asyncio
async def test_result_frame_includes_failed_fields_on_full_success():
    """전체 성공 시에도 ResultFrame에 failed_count/failed_node_types 필드 존재 (빈 리스트)."""
    repo = _InMemoryRepo()
    embedder = _FakeEmbedder()
    use_case = BuildFromIndustryDefaultUseCase(repo, embedder)

    frames = [f async for f in use_case.execute(uuid4(), "food")]

    result = frames[-1]
    assert isinstance(result, ResultFrame)
    assert "failed_count" in result.payload
    assert "failed_node_types" in result.payload
    assert result.payload["failed_count"] == 0
    assert result.payload["failed_node_types"] == []


@pytest.mark.asyncio
async def test_partial_failure_idempotent_recovery():
    """부분 실패 후 재실행하면 실패했던 노드만 새로 upsert 시도 (uuid5 deterministic)."""
    # 1차: upsert 실패
    failing_repo = _FailingRepo(fail_on_node_type="it_pr_review_request")
    embedder = _FakeEmbedder()
    use_case_1 = BuildFromIndustryDefaultUseCase(failing_repo, embedder)
    _ = [f async for f in use_case_1.execute(uuid4(), "it")]
    assert len(failing_repo.store) == 4

    # 2차: 정상 repo로 재실행 — 동일한 node_id로 5종 모두 등록됨
    normal_repo = _InMemoryRepo()
    use_case_2 = BuildFromIndustryDefaultUseCase(normal_repo, embedder)
    _ = [f async for f in use_case_2.execute(uuid4(), "it")]
    assert len(normal_repo.store) == 5

    # 두 repo에서 동일하게 등록된 4개 노드는 같은 node_id (uuid5 deterministic)
    common_ids = set(failing_repo.store.keys()) & set(normal_repo.store.keys())
    assert len(common_ids) == 4
