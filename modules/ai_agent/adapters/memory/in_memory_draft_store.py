"""InMemoryWorkflowDraftStore — WorkflowDraftStore의 in-memory 구현체."""
from __future__ import annotations

from uuid import UUID

from common_schemas import WorkflowSchema

from ...domain.ports.workflow_draft_store import WorkflowDraftStore


class InMemoryWorkflowDraftStore(WorkflowDraftStore):
    """session_id → WorkflowSchema 딕셔너리 기반 임시 저장소.

    단일 프로세스 내에서만 유효.
    Modal app scale-out 시 GCS 어댑터(GCSWorkflowDraftStore)로 교체 필요.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, WorkflowSchema] = {}

    async def save_draft(self, session_id: UUID, draft: WorkflowSchema) -> None:
        self._store[session_id] = draft

    async def load_draft(self, session_id: UUID) -> WorkflowSchema | None:
        return self._store.get(session_id)

    async def delete_draft(self, session_id: UUID) -> None:
        self._store.pop(session_id, None)
