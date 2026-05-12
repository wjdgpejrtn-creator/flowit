"""Skills Builder — 산업 표준 default seed → NodeDefinition upsert.

REQ-004 spec §2.2 BuildFromIndustryDefaultUseCase.
Sprint 3 v1: seed 5개 산업 하드코딩. v2(Sprint 4+): LLM 자유 생성.

flow:
    industry_code (manufacturing/service/wholesale_retail/food/it)
      → modules/ai_agent/seeds/industry_defaults/{code}.json 로드
      → 각 항목을 SkillNode로 검증
      → NodeDefinition으로 변환 (embedding 포함)
      → NodeDefinitionRepository.upsert() 호출
      → SSE 프레임으로 진행 상황 yield
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID, uuid5

from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame, SSEFrame
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ....domain.entities.skill_node import SkillNode


# uuid5 namespace for skills builder generated nodes (industry default).
# 같은 industry_code + node_type 조합은 항상 같은 node_id 생성 (idempotent upsert).
_SKILLS_BUILDER_NS = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "workflow-automation.skills_builder")

_DEFAULT_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds" / "industry_defaults"

_SUPPORTED_INDUSTRIES = {"manufacturing", "service", "wholesale_retail", "food", "it"}


class BuildFromIndustryDefaultUseCase:
    """산업 default seed → nodes_graph 카탈로그 upsert 일괄 처리.

    Sprint 3 v1: 5개 산업 하드코딩 (manufacturing/service/wholesale_retail/food/it).
    """

    def __init__(
        self,
        node_def_repo: NodeDefinitionRepository,
        embedder: EmbedderPort,
        seeds_dir: Path | None = None,
    ) -> None:
        self._repo = node_def_repo
        self._embedder = embedder
        self._seeds_dir = seeds_dir or _DEFAULT_SEEDS_DIR

    async def execute(
        self,
        user_id: UUID,
        industry_code: str,
    ) -> AsyncGenerator[SSEFrame, None]:
        """seed JSON 로드 → SkillNode 검증 → NodeDefinition upsert."""
        # 1. industry_code 검증
        if industry_code not in _SUPPORTED_INDUSTRIES:
            yield ErrorFrame(
                code="E_INDUSTRY_NOT_SUPPORTED",
                message=f"산업 코드 '{industry_code}'는 지원하지 않습니다. 가능: {sorted(_SUPPORTED_INDUSTRIES)}",
            )
            return

        # 2. seed JSON 로드
        seed_path = self._seeds_dir / f"{industry_code}.json"
        if not seed_path.exists():
            yield ErrorFrame(
                code="E_SEED_NOT_FOUND",
                message=f"산업 default seed 파일 없음: {seed_path}",
            )
            return

        try:
            with seed_path.open(encoding="utf-8") as f:
                seed = json.load(f)
        except json.JSONDecodeError as e:
            yield ErrorFrame(code="E_SEED_INVALID_JSON", message=f"seed JSON 파싱 실패: {e}")
            return

        yield AgentNodeFrame(agent_node_name="skills_builder.load_industry_default")

        # 3. 각 항목 처리
        version = seed.get("version", "1.0.0")
        skill_nodes_data = seed.get("skill_nodes", [])
        upserted_node_types: list[str] = []

        for entry in skill_nodes_data:
            try:
                node_def = self._convert_entry_to_node_definition(entry, industry_code, version)
            except (KeyError, ValueError) as e:
                yield ErrorFrame(
                    code="E_SEED_ENTRY_INVALID",
                    message=f"seed 항목 변환 실패 ({entry.get('node_type', '?')}): {e}",
                )
                return

            # description 임베딩
            node_def.embedding = await self._embedder.embed(node_def.description)

            yield AgentNodeFrame(agent_node_name=f"skills_builder.upsert.{node_def.node_type}")

            await self._repo.upsert(node_def)
            upserted_node_types.append(node_def.node_type)

        # 4. 결과 프레임
        yield ResultFrame(
            intent="build_skill",
            payload={
                "industry_code": industry_code,
                "industry_name": seed.get("industry_name", ""),
                "upserted_count": len(upserted_node_types),
                "node_types": upserted_node_types,
                "user_id": str(user_id),
            },
        )

    @staticmethod
    def _convert_entry_to_node_definition(
        entry: dict,
        industry_code: str,
        version: str,
    ) -> NodeDefinition:
        """seed JSON 항목을 SkillNode로 1차 검증 → NodeDefinition으로 변환.

        SkillNode 검증을 거치는 이유: source_type/source_id를 명시적으로 부여하고
        risk_level/inputs/outputs/description 필드 존재를 도메인 단에서 보장.
        """
        # SkillNode 검증 (Pydantic 자동 validate)
        SkillNode(
            source_type="industry_default",
            source_id=industry_code,
            name=entry["name"],
            description=entry["description"],
            inputs=entry["inputs"],
            outputs=entry["outputs"],
            risk_level=RiskLevel(entry["risk_level"]),
        )

        # NodeDefinition 변환
        node_type = entry["node_type"]
        return NodeDefinition(
            node_id=uuid5(_SKILLS_BUILDER_NS, node_type),
            node_type=node_type,
            name=entry["name"],
            category=entry["category"],
            version=version,
            input_schema=entry["inputs"],
            output_schema=entry["outputs"],
            parameter_schema={},
            risk_level=RiskLevel(entry["risk_level"]),
            required_connections=entry.get("required_connections", []),
            description=entry["description"],
            is_mvp=False,  # 산업 default = 사용자 도메인 노드, MVP 카탈로그 아님
            service_type=entry.get("service_type"),
            embedding=None,  # 호출자가 embedder로 채움
        )
