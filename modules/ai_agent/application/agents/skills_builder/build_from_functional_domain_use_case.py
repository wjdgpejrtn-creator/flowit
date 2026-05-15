"""Skills Builder — 직무 영역 default seed → NodeDefinition upsert.

REQ-004 spec §2.2 확장 — 2026-05-12 조장 합의로 추가된 직무 영역 baseline.

활성 직무 영역 (PR #47 beta):
    customer_support   — VOC 접수·챗봇·CSAT·KB 검색·SLA
    it_ops             — 배포 승인·권한 요청·장애 페이저·비밀번호·미팅룸
    document_data      — OCR·양식 파싱·요약·번역·아카이브
    hr                 — 온보딩·휴가·평가 알림·기념일·퇴사
    marketing          — 캠페인 스케줄·리드 스코어링·A/B·이벤트·리포트

flow:
    domain_code → modules/ai_agent/seeds/functional_domain_defaults/{code}.json 로드
      → SkillNode(source_type="functional_domain") 검증
      → NodeDefinition 변환 (embedding 포함)
      → NodeDefinitionRepository.upsert() 호출
      → SSE 프레임으로 진행 상황 yield

uuid5 namespace:
    `f"functional:{domain_code}:{node_type}"` — industry_default / sop 와 다른 namespace
    로 충돌 방지. 같은 (domain_code, node_type) 조합은 deterministic → idempotent upsert.
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


_SKILLS_BUILDER_NS = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "workflow-automation.skills_builder")

_DEFAULT_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds" / "functional_domain_defaults"

_ACTIVE_DOMAINS = {"customer_support", "it_ops", "document_data", "hr", "marketing"}


class BuildFromFunctionalDomainUseCase:
    """직무 영역 default seed → nodes_graph 카탈로그 upsert 일괄 처리.

    Industry default와 동일 패턴이지만:
    - source_type="functional_domain"
    - uuid5 namespace에 "functional:" prefix
    - seed 디렉토리: modules/ai_agent/seeds/functional_domain_defaults/
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
        domain_code: str,
    ) -> AsyncGenerator[SSEFrame, None]:
        """seed JSON 로드 → SkillNode 검증 → NodeDefinition upsert."""
        # 1. domain_code 검증
        if domain_code not in _ACTIVE_DOMAINS:
            yield ErrorFrame(
                code="E_DOMAIN_NOT_SUPPORTED",
                message=f"직무 영역 코드 '{domain_code}'는 지원하지 않습니다. 활성: {sorted(_ACTIVE_DOMAINS)}",
            )
            return

        # 2. seed JSON 로드
        seed_path = self._seeds_dir / f"{domain_code}.json"
        if not seed_path.exists():
            yield ErrorFrame(
                code="E_SEED_NOT_FOUND",
                message=f"직무 영역 default seed 파일 없음: {seed_path}",
            )
            return

        try:
            with seed_path.open(encoding="utf-8") as f:
                seed = json.load(f)
        except json.JSONDecodeError as e:
            yield ErrorFrame(code="E_SEED_INVALID_JSON", message=f"seed JSON 파싱 실패: {e}")
            return

        yield AgentNodeFrame(agent_node_name="skills_builder.load_functional_domain")

        # 3. 각 항목 처리
        #
        # 부분 실패 정책 (PR #44 BuildFromIndustryDefaultUseCase 패턴 동일 적용):
        # - convert 실패 (seed JSON 항목 깨짐): 전체 중단 (E_SEED_ENTRY_INVALID).
        #   seed 파일 자체가 broken이면 다음 항목도 동일 위험이라 fail-fast.
        # - embed/upsert 실패 (런타임 외부 의존성 오류): 해당 노드만 격리,
        #   다른 노드 계속 진행. ResultFrame.failed_node_types에 기록.
        # - uuid5 deterministic이라 부분 실패 후 재실행 안전 (이미 upsert된 노드는
        #   덮어쓰기 = idempotent. 실패 노드만 새로 시도).
        version = seed.get("version", "1.0.0")
        skill_nodes_data = seed.get("skill_nodes", [])
        upserted_node_types: list[str] = []
        failed_node_types: list[dict] = []

        for entry in skill_nodes_data:
            try:
                node_def = self._convert_entry_to_node_definition(entry, domain_code, version)
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

        # 4. 결과 프레임
        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "functional_domain",
                "domain_code": domain_code,
                "domain_name": seed.get("domain_name", ""),
                "upserted_count": len(upserted_node_types),
                "failed_count": len(failed_node_types),
                "node_types": upserted_node_types,
                "failed_node_types": failed_node_types,
                "user_id": str(user_id),
            },
        )

    @staticmethod
    def _convert_entry_to_node_definition(
        entry: dict,
        domain_code: str,
        version: str,
    ) -> NodeDefinition:
        """seed JSON 항목 → SkillNode 검증 → NodeDefinition 변환."""
        SkillNode(
            source_type="functional_domain",
            source_id=domain_code,
            name=entry["name"],
            description=entry["description"],
            inputs=entry["inputs"],
            outputs=entry["outputs"],
            risk_level=RiskLevel(entry["risk_level"]),
        )

        node_type = entry["node_type"]
        return NodeDefinition(
            node_id=uuid5(_SKILLS_BUILDER_NS, f"functional:{domain_code}:{node_type}"),
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
            is_mvp=False,
            service_type=entry.get("service_type"),
            embedding=None,
        )
