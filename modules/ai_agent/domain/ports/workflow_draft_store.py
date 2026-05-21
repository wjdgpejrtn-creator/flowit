from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas import WorkflowSchema


class WorkflowDraftStore(ABC):
    """세션별 draft workflow 임시 보관 Port.

    사용자가 승인을 누르기 전까지 Composer가 생성한 DraftSpec(WorkflowSchema)을
    session 단위로 유지한다. 승인 시점에 (draft, final) 쌍을 비교해
    Personalization에 이벤트로 전달한다.
    """

    @abstractmethod
    async def save_draft(self, session_id: UUID, draft: WorkflowSchema) -> None:
        """session_id에 연결된 draft를 저장(덮어쓰기)한다."""

    @abstractmethod
    async def load_draft(self, session_id: UUID) -> WorkflowSchema | None:
        """저장된 draft를 반환한다. 없으면 None."""

    @abstractmethod
    async def delete_draft(self, session_id: UUID) -> None:
        """draft를 삭제한다. 없어도 예외를 발생시키지 않는다."""
