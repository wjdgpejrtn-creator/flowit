from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.node_spec_staging import NodeSpecStaging
from ...domain.value_objects.skill_state import SkillState


class CreateDraftSkillUseCase:
    """Skills Builder(REQ-004 ③)가 추출 결과를 개인 DRAFT 스킬로 생성 (ADR-0020 ②e).

    Option B: NodeDefinition은 PUBLISHED 시점에만 생성하므로, 추출 직후엔 노드 스펙을
    `node_spec_staging`에 보관한 personal DRAFT만 만든다. NodeDefinition을 만들지 않으므로
    nodes_graph owner/team(①)과 무관 — ③ sop 경로가 ① 머지 없이 진행 가능한 근거.
    seed(자동 PUBLISHED) 경로는 이 DRAFT 생성 후 publish(②d, NodeDefinition 생성)를 거친다.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        owner_user_id: UUID,
        name: str,
        description: str,
        node_spec_staging: NodeSpecStaging,
        embedding: list[float] | None = None,
        skill_document_uri: str | None = None,
    ) -> UUID:
        now = datetime.now(UTC)
        skill = MarketplacePersonalSkill(
            skill_id=uuid4(),
            owner_user_id=owner_user_id,
            name=name,
            description=description,
            node_definition_id=None,          # publish 전 미생성 (Option B)
            node_spec_staging=node_spec_staging,
            lifecycle_state=SkillState.DRAFT,
            embedding=embedding,
            skill_document_uri=skill_document_uri,
            created_at=now,
            updated_at=now,
        )
        saved = await self._repo.save_personal(skill)
        return saved.skill_id
