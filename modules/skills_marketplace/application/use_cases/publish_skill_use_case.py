from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.exceptions import NotFoundError
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_lifecycle import SkillLifecycle
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class PublishSkillUseCase:
    """스킬 게시 — APPROVED → PUBLISHED + NodeDefinition 생성 (ADR-0020 Option B / Q1).

    storage/marketplace/application/use_cases/publish_skill.py에서 이전 (ADR-0012 PR-2d).
    정석 정정: 원본 `PgSkillRepository`(구현체) 직접 의존 → `SkillRepository`(ABC) 의존.

    ②(d): PUBLISHED 시점에만 `node_spec_staging` + 스킬 메타로 `NodeDefinition`을 생성·upsert하고
    `node_definition_id`를 연결한다(Option B — 미검토 스킬이 카탈로그 오염 방지). scope별 owner/team을
    NodeDefinition에 격리(personal=owner_user_id, team=team_id, company=전역). nodes_graph는
    `domain.ports.NodeDefinitionRepository`만 참조(CLAUDE.md 허용 교차 import).
    """

    def __init__(self, repo: SkillRepository, node_def_repo: NodeDefinitionRepository) -> None:
        self._repo = repo
        self._node_def_repo = node_def_repo

    async def execute(self, skill_id: UUID, scope: SkillScope) -> None:
        skill = await self._get(skill_id, scope)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} (scope={scope.value}) not found")

        new_state = SkillLifecycle.transition(SkillState(skill.lifecycle_state), SkillState.PUBLISHED)
        changes: dict = {"lifecycle_state": new_state, "updated_at": datetime.now(UTC)}

        # Option B: PUBLISHED 시점에만 NodeDefinition 생성 (staging 있고 아직 미연결인 경우)
        staging = getattr(skill, "node_spec_staging", None)
        if staging is not None and skill.node_definition_id is None:
            node_def = self._build_node_definition(skill, scope, staging)
            await self._node_def_repo.upsert(node_def)
            changes["node_definition_id"] = node_def.node_id

        updated = skill.model_copy(update=changes)
        await self._save(updated, scope)

    @staticmethod
    def _build_node_definition(skill, scope: SkillScope, staging) -> NodeDefinition:
        return NodeDefinition(
            node_id=uuid4(),
            node_type=f"skill_{skill.skill_id}",
            name=skill.name,
            category=staging.category,
            version=skill.version,
            input_schema=staging.input_schema,
            output_schema=staging.output_schema,
            parameter_schema={},
            risk_level=staging.risk_level,
            required_connections=staging.required_connections,
            description=skill.description,
            is_mvp=False,
            service_type=staging.service_type,
            embedding=skill.embedding,
            owner_user_id=skill.owner_user_id if scope == SkillScope.PERSONAL else None,
            team_id=getattr(skill, "team_id", None) if scope == SkillScope.TEAM else None,
        )

    async def _get(self, skill_id: UUID, scope: SkillScope):
        if scope == SkillScope.PERSONAL:
            return await self._repo.get_personal(skill_id)
        if scope == SkillScope.TEAM:
            return await self._repo.get_team(skill_id)
        return await self._repo.get_company(skill_id)

    async def _save(self, skill, scope: SkillScope) -> None:
        if scope == SkillScope.PERSONAL:
            await self._repo.save_personal(skill)
        elif scope == SkillScope.TEAM:
            await self._repo.save_team(skill)
        else:
            await self._repo.save_company(skill)
