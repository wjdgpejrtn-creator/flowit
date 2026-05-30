from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas import SkillDocument

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_document_store import SkillDocumentStore
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.node_spec_staging import NodeSpecStaging
from ...domain.value_objects.skill_state import SkillState


class CreateDraftSkillUseCase:
    """Skills Builder(REQ-004 ③)가 추출 결과를 개인 DRAFT 스킬로 생성 (ADR-0020 ②e).

    Option B: NodeDefinition은 PUBLISHED 시점에만 생성하므로, 추출 직후엔 노드 스펙을
    `node_spec_staging`에 보관한 personal DRAFT만 만든다. NodeDefinition을 만들지 않으므로
    nodes_graph owner/team(①)과 무관 — ③ sop 경로가 ① 머지 없이 진행 가능한 근거.
    seed(자동 PUBLISHED) 경로는 이 DRAFT 생성 후 publish(②d, NodeDefinition 생성)를 거친다.

    ADR-0017 이중 저장: `doc_store`와 `instructions`가 함께 주어지면 SkillDocument(markdown)를
    GCS에 저장하고 반환된 gs:// URI를 메타데이터(`skill_document_uri`)에 기록한다. skill_id를 본
    use case가 생성하므로 문서 저장→메타 저장 순서를 여기서 일관되게 처리한다. `doc_store`는
    Optional — seed 등 문서 없는 경로/단위 테스트는 주입 없이 동작한다.
    """

    def __init__(self, repo: SkillRepository, doc_store: SkillDocumentStore | None = None) -> None:
        self._repo = repo
        self._doc_store = doc_store

    async def execute(
        self,
        owner_user_id: UUID,
        name: str,
        description: str,
        node_spec_staging: NodeSpecStaging,
        embedding: list[float] | None = None,
        skill_document_uri: str | None = None,
        instructions: str | None = None,
        source_document_id: UUID | None = None,
    ) -> UUID:
        skill_id = uuid4()

        # ADR-0017 이중 저장 — instructions(SKILL.md 본문)가 있으면 GCS에 저장하고 URI를 메타에 기록.
        # bucket은 어댑터만 알기 때문에 어댑터가 반환한 URI를 그대로 사용 (2026-05-24 결정).
        if self._doc_store is not None and instructions is not None:
            document = SkillDocument(
                skill_id=skill_id,
                name=name,
                description=description,
                instructions=instructions,
            )
            skill_document_uri = await self._doc_store.save(skill_id, document)

        now = datetime.now(UTC)
        skill = MarketplacePersonalSkill(
            skill_id=skill_id,
            owner_user_id=owner_user_id,
            name=name,
            description=description,
            node_definition_id=None,          # publish 전 미생성 (Option B)
            node_spec_staging=node_spec_staging,
            lifecycle_state=SkillState.DRAFT,
            embedding=embedding,
            skill_document_uri=skill_document_uri,
            source_document_id=source_document_id,  # 문서→빌더 핸드오프 association (REQ-010)
            created_at=now,
            updated_at=now,
        )
        saved = await self._repo.save_personal(skill)
        return saved.skill_id
