from __future__ import annotations

from common_schemas import DraftSpec, Edge, NodeInstance, WorkflowSchema

from ..orm.workflow_model import WorkflowModel


class WorkflowMapper:
    @staticmethod
    def to_domain(orm: WorkflowModel) -> WorkflowSchema:
        return WorkflowSchema(
            workflow_id=orm.workflow_id,
            owner_user_id=orm.user_id,  # ORM은 NOT NULL, domain은 Optional
            name=orm.name,
            description=orm.description,
            scope=orm.scope,
            is_draft=orm.is_draft,
            draft_spec=DraftSpec.model_validate(orm.draft_spec) if orm.draft_spec else None,
            nodes=[NodeInstance.model_validate(n) for n in orm.nodes],
            connections=[Edge.model_validate(e) for e in orm.connections],
            version=orm.version,
            sha256=orm.sha256,
            created_via_session_id=orm.created_via_session_id,
        )

    @staticmethod
    def to_orm(entity: WorkflowSchema) -> WorkflowModel:
        # DB schema는 NOT NULL이라 owner_user_id 없으면 INSERT 불가 — 명시적 ValueError로 전환.
        if entity.owner_user_id is None:
            raise ValueError(
                "WorkflowSchema.owner_user_id is required for DB persistence "
                "(workflows.user_id NOT NULL). Set owner_user_id in the use case "
                "before calling Repository.save()."
            )
        return WorkflowModel(
            workflow_id=entity.workflow_id,
            user_id=entity.owner_user_id,
            name=entity.name,
            description=entity.description,
            scope=entity.scope,
            is_draft=entity.is_draft,
            draft_spec=entity.draft_spec.model_dump(mode="json") if entity.draft_spec else None,
            nodes=[n.model_dump(mode="json") for n in entity.nodes],
            connections=[e.model_dump(mode="json") for e in entity.connections],
            version=entity.version,
            sha256=entity.sha256,
            created_via_session_id=entity.created_via_session_id,
        )
