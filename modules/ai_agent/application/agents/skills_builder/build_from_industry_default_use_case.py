"""Skills Builder — 산업 표준 default seed → NodeDefinition upsert.

REQ-004 spec §2.2 BuildFromIndustryDefaultUseCase.

활성 산업 (2026-05-12 조장 합의):
  ecommerce — 데모 baseline. LG헬로비전 사내 자동화 시장 리서치 결과
              직무 영역(CS/IT Ops/Document/HR/Marketing) 중심 + 산업은 e-commerce
              한 축으로 baseline 구성.

비활성 산업 (deprecated, 호출 막힘 / seed JSON 파일은 보존):
  manufacturing / service / wholesale_retail / food / it
  → Sprint 3 v1 베타로 작성된 5종. 데모 baseline에서는 제외.
  → seed JSON 파일은 modules/ai_agent/seeds/industry_defaults/에 유지 (히스토리/복원용).
  → execute() 호출 시 E_INDUSTRY_DEACTIVATED 에러 반환.

flow:
    industry_code (ecommerce only — active)
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

from common_schemas import SkillDocument
from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame, SSEFrame
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ....domain.entities.skill_node import SkillNode

# uuid5 namespace for skills builder generated nodes (industry default).
# node_id = uuid5(_NS, f"{industry_code}:{node_type}") — industry_code를 명시 결합해서
# 산업 간 node_type 우연 충돌을 namespace 레벨에서 차단 (PR #42 리뷰 후속, 견고성).
# 같은 (industry_code, node_type) 조합은 항상 같은 node_id 생성 → idempotent upsert.
_SKILLS_BUILDER_NS = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "workflow-automation.skills_builder")

_DEFAULT_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds" / "industry_defaults"

# 활성 산업 — 데모 baseline (2026-05-12 조장 합의)
_ACTIVE_INDUSTRIES = {"ecommerce"}

# 비활성 산업 — Sprint 3 v1 베타 5종. seed 파일 보존, 호출 막힘
_DEPRECATED_INDUSTRIES = {"manufacturing", "service", "wholesale_retail", "food", "it"}


class BuildFromIndustryDefaultUseCase:
    """산업 default seed → nodes_graph 카탈로그 upsert 일괄 처리.

    Sprint 3 baseline: ecommerce 1종 활성. 기존 5종은 deprecated.
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
        # 1. industry_code 검증 — 활성/비활성/미지원 3분기
        if industry_code in _DEPRECATED_INDUSTRIES:
            yield ErrorFrame(
                code="E_INDUSTRY_DEACTIVATED",
                message=(
                    f"산업 코드 '{industry_code}'는 비활성화 상태입니다 (Sprint 3 v1 베타, "
                    f"2026-05-12 조장 결정으로 데모 baseline에서 제외). "
                    f"활성 산업: {sorted(_ACTIVE_INDUSTRIES)}. "
                    f"seed JSON 파일은 modules/ai_agent/seeds/industry_defaults/에 보존됨"
                ),
            )
            return

        if industry_code not in _ACTIVE_INDUSTRIES:
            yield ErrorFrame(
                code="E_INDUSTRY_NOT_SUPPORTED",
                message=f"산업 코드 '{industry_code}'는 지원하지 않습니다. 활성: {sorted(_ACTIVE_INDUSTRIES)}",
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
        #
        # 부분 실패 정책 (PR #42 리뷰 후속):
        # - convert 실패 (seed JSON 항목 깨짐): 전체 중단 (E_SEED_ENTRY_INVALID).
        #   seed 파일 자체가 broken이면 다음 항목도 동일 위험이라 fail-fast.
        # - embed/upsert 실패 (런타임 외부 의존성 오류): 해당 노드만 격리,
        #   다른 노드 계속 진행. ResultFrame.failed_node_types에 기록.
        # - uuid5 deterministic이라 부분 실패 후 재실행 안전 (이미 upsert된 노드는
        #   덮어쓰기 = idempotent. 실패 노드만 새로 시도).
        version = seed.get("version", "1.0.0")
        skill_nodes_data = seed.get("skill_nodes", [])
        upserted_node_types: list[str] = []
        skill_documents: list[SkillDocument] = []
        failed_node_types: list[dict] = []

        for entry in skill_nodes_data:
            try:
                node_def = self._convert_entry_to_node_definition(entry, industry_code, version)
            except (KeyError, ValueError) as e:
                # seed JSON 항목 자체가 깨짐 → 전체 중단
                yield ErrorFrame(
                    code="E_SEED_ENTRY_INVALID",
                    message=f"seed 항목 변환 실패 ({entry.get('node_type', '?')}): {e}",
                )
                return

            # description 임베딩 (외부 의존성 — 격리 처리)
            try:
                node_def.embedding = await self._embedder.embed(node_def.description)
            except Exception as e:
                failed_node_types.append({
                    "node_type": node_def.node_type,
                    "stage": "embed",
                    "error": str(e),
                })
                yield ErrorFrame(
                    code="E_EMBEDDING_FAILED",
                    message=f"임베딩 실패 ({node_def.node_type}): {e}",
                )
                continue

            yield AgentNodeFrame(agent_node_name=f"skills_builder.upsert.{node_def.node_type}")

            # upsert (외부 의존성 — 격리 처리)
            try:
                await self._repo.upsert(node_def)
            except Exception as e:
                failed_node_types.append({
                    "node_type": node_def.node_type,
                    "stage": "upsert",
                    "error": str(e),
                })
                yield ErrorFrame(
                    code="E_UPSERT_FAILED",
                    message=f"upsert 실패 ({node_def.node_type}): {e}",
                )
                continue

            upserted_node_types.append(node_def.node_type)
            # ADR-0017/0024: seed에 instructions(SKILL.md) 또는 composer_instructions(COMPOSER.md)가
            # 있으면 SkillDocument 수집 (선택 — ② seed 채우기 전엔 미수집). common_schemas.SkillDocument
            # 객체 (type-safe). SkillDocument≠Node라 node_type 없이 skill_id로 NodeDefinition 연결
            # (조장 PR #106/#113). composer_instructions = ADR-0024 2-md 중 COMPOSER.md 본문 — drafter가
            # 워크플로우 생성 시 주입(#372 결함 A 해소). 둘 다 optional이라 하나라도 있으면 방출.
            instructions = entry.get("instructions") or ""
            composer_instructions = entry.get("composer_instructions") or ""
            if instructions or composer_instructions:
                skill_documents.append(SkillDocument(
                    skill_id=node_def.node_id,
                    name=node_def.name,
                    description=node_def.description,
                    instructions=instructions,
                    composer_instructions=composer_instructions,
                ))

        # 4. 결과 프레임
        yield ResultFrame(
            intent="build_skill",
            payload={
                "industry_code": industry_code,
                "industry_name": seed.get("industry_name", ""),
                "upserted_count": len(upserted_node_types),
                "failed_count": len(failed_node_types),
                "node_types": upserted_node_types,
                "skill_documents": [doc.model_dump(mode="json") for doc in skill_documents],
                "failed_node_types": failed_node_types,
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
            node_id=uuid5(_SKILLS_BUILDER_NS, f"{industry_code}:{node_type}"),
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
