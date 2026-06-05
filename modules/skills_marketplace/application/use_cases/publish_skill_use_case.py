from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from common_schemas import UserRole
from common_schemas.exceptions import NotFoundError
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_approval_policy import SkillApprovalPolicy
from ...domain.services.skill_lifecycle import SkillLifecycle
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState

_logger = logging.getLogger(__name__)


class PublishSkillUseCase:
    """스킬 게시 — APPROVED → PUBLISHED (ADR-0024 D2: NodeDefinition 생성 폐기).

    storage/marketplace/application/use_cases/publish_skill.py에서 이전 (ADR-0012 PR-2d).
    정석 정정: 원본 `PgSkillRepository`(구현체) 직접 의존 → `SkillRepository`(ABC) 의존.

    **ADR-0024 D2 (#372 결함 B)**: 게시 시 더 이상 `NodeDefinition`을 생성하지 않는다. 스킬은
    "실행 노드"가 아니라 "LLM 노드에 주입되는 지침서"(모델 A)이며, Composer는 스킬 자체 임베딩으로
    검색한다(`SearchSkillsUseCase`). 게시는 lifecycle 전이 + 검색용 임베딩 채움만 담당한다.
    (구 ADR-0020 Option B의 `node_spec_staging`→`NodeDefinition` upsert 경로 제거 — 스킬이 일반
    노드 검색 `SearchNodesUseCase`에 섞여 워크플로우 노드로 둔갑하던 결함 B 차단.)
    """

    def __init__(
        self,
        repo: SkillRepository,
        node_def_repo: NodeDefinitionRepository | None = None,
        embedder: EmbedderPort | None = None,
    ) -> None:
        self._repo = repo
        # ADR-0024 D2: deprecated — 게시 시 NodeDef를 만들지 않으므로 미사용. 호출부 시그니처
        # 하위호환을 위해 파라미터만 유지(후속 정리). 신규 조립부는 주입하지 않아도 된다.
        self._node_def_repo = node_def_repo
        self._embedder = embedder

    async def execute(
        self,
        skill_id: UUID,
        scope: SkillScope,
        *,
        actor_user_id: UUID,
        actor_role: UserRole,
        actor_department_id: UUID | None = None,
    ) -> None:
        skill = await self._get(skill_id, scope)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} (scope={scope.value}) not found")

        # ADR-0020 위임2: scope별 actor 인가. 실패 시 AuthorizationError.
        SkillApprovalPolicy.authorize(
            scope=scope,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            actor_department_id=actor_department_id,
            skill_owner_user_id=getattr(skill, "owner_user_id", None),
            skill_team_id=getattr(skill, "team_id", None),
        )

        new_state = SkillLifecycle.transition(SkillState(skill.lifecycle_state), SkillState.PUBLISHED)
        changes: dict = {"lifecycle_state": new_state, "updated_at": datetime.now(UTC)}

        # 검색 가능성 보장 — 게시 시 임베딩이 비어 있으면 생성한다. 생성 경로가 임베딩을 채우지
        # 않은 스킬(예: api `POST /skills/personal`은 embedding 미전달 → NULL)도 PUBLISHED 시점에
        # Composer 하이브리드 스킬 검색(`SearchSkillsUseCase`, `embedding IS NOT NULL`)에 노출되도록.
        # embedder 미주입(하위호환)·생성 실패 시 non-fatal — 게시 자체는 막지 않는다(검색만 누락).
        embedding = skill.embedding
        if embedding is None and self._embedder is not None:
            text = (skill.description or skill.name or "").strip()
            if text:
                try:
                    embedding = await self._embedder.embed(text)
                    changes["embedding"] = embedding
                except Exception as exc:
                    _logger.warning("publish 임베딩 생성 실패 (non-fatal, 검색 누락 가능): %s", exc)

        # ADR-0024 D2 (#372 결함 B): 게시 시 NodeDefinition을 생성하지 않는다. 스킬은 "실행 노드"가
        # 아니라 "LLM 노드에 주입되는 지침서"(모델 A)이며, 노드 검색이 아니라 스킬 자체 임베딩으로
        # 검색된다. 스킬을 NodeDef로 등록하면 일반 노드 검색(`SearchNodesUseCase`)에 섞여 워크플로우
        # 노드로 둔갑하므로(예: `hr_onboarding_workflow`가 노드 후보로 노출) 생성 자체를 폐기한다.
        # `node_definition_id`는 None으로 유지. (기존에 등록된 NodeDef 정리는 별도 DB 마이그레이션.)
        updated = skill.model_copy(update=changes)
        await self._save(updated, scope)

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
