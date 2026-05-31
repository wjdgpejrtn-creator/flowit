"""ComposerStateStore — two-shot HITL 1차 라운드 상태 영속 Port (REQ-013)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class ComposerStateStore(ABC):
    """Composer two-shot HITL의 1차 라운드 상태를 영속/복원한다.

    1차(스킬 옵션 제시 후 종료) 시점에 2차 재개에 필요한 그래프 상태(draft_spec/
    node_candidates/intent 등)를 직렬화 dict로 저장하고, 2차(사용자 선택) 라운드에서
    복원해 draft 단계부터 이어간다. Modal 다중 컨테이너 stateless 환경 대응
    (GCSWorkflowDraftStore와 동일 패턴, 별도 키 공간).

    저장 경로(GCS 구현): `composer_state/{session_id}.json`.
    """

    @abstractmethod
    async def save_state(self, session_id: UUID, state: dict[str, Any]) -> None:
        """1차 라운드 종료 시 재개용 상태(직렬화 dict)를 저장."""
        ...

    @abstractmethod
    async def load_state(self, session_id: UUID) -> dict[str, Any] | None:
        """session_id의 저장된 재개 상태 조회 (없으면 None — 만료/미존재)."""
        ...

    @abstractmethod
    async def delete_state(self, session_id: UUID) -> None:
        """재개 상태 삭제 (2차 완료 후 정리). 멱등 — 객체 없으면 no-op."""
        ...
