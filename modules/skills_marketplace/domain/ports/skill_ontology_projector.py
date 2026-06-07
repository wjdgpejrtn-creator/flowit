from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from ..value_objects.skill_scope import SkillScope


class SkillOntologyProjector(ABC):
    """게시 스킬을 온톨로지 그래프(Neo4j)에 투영하는 포트 (ADR-0026 Phase 2b).

    `PublishSkillUseCase`가 스킬 게시(PUBLISHED 전이) 시점에 호출해 `(:Skill)` 노드와
    `(:Skill)-[:BINDS]->(:Node)` edge를 incremental upsert한다(ADR-0026 Follow-up
    "스킬은 publish마다 incremental upsert"). 정적 카탈로그(노드)는 deploy 시 1회
    `scripts/build_ontology.py`로 투영되는 것과 대비된다.

    **Port 소유 = skills_marketplace(소비자=publish), 구현 = ai_agent/adapters/ontology**
    (ADR-0013 EmbedderPort 예외 패턴 — Neo4j 외부 인프라 호출 어댑터는 호출 모듈이 보유.
    skills_marketplace는 Neo4j를 직접 모름). `OntologyRetrieverPort`(읽기, ai_agent 소유)와
    별개의 쓰기 포트다. 구현체 DI 주입은 services Composition Root에서 받는다.

    **BINDS 의미(모델 A, ADR-0024 D2 정합)**: 스킬은 "실행 노드"가 아니라 "LLM 노드에 주입되는
    지침서"이므로(node_definition_id 경로 폐기), 스킬은 ai 카테고리 LLM 노드에 BINDS한다(런타임
    `CatalogNodeExecutor._inject_skill` + composer two-shot "first ai node" 바인딩과 정합 —
    #372 결함 A 그라운딩). 추가로 `required_connections`가 있으면 해당 connection을 요구하는
    노드에도 BINDS해 스킬 고유의 역량 신호를 남긴다(skill-builder grounding 소비자용).

    어댑터는 게시 자체를 막지 않도록 **non-fatal**로 호출된다(Neo4j 장애 시 게시 진행, 검색
    누락만 감수 — 임베딩 백필과 동일한 비치명 정책).
    """

    @abstractmethod
    async def project_skill(
        self,
        *,
        skill_id: UUID,
        scope: SkillScope,
        required_connections: Sequence[str] = (),
    ) -> None:
        """게시 스킬 하나를 `(:Skill)` + BINDS edge로 멱등 upsert.

        Args:
            skill_id: 스킬 식별자(`:Skill {id}` 키).
            scope: 스킬 범위(personal/team/company) — `:Skill {tier, audience}`로 투영.
            required_connections: 스킬이 요구하는 connection provider 목록. 각 provider를
                요구하는 노드에 BINDS edge를 추가한다(없으면 ai 노드 BINDS만).

        멱등: 재게시 시 기존 BINDS를 재계산(stale edge 제거 후 재생성)해야 한다.
        """
        ...
