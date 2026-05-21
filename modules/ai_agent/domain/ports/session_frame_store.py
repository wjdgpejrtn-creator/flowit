from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas.transport import AnySSEFrame

from ..entities.session_ref import SessionRef


class SessionFrameStore(ABC):
    """세션 SSE 프레임 저장소 — 모니터링 히스토리 조회용.

    저장 구조 (GCS):
        sessions/{user_id}/{session_id}.json  ← 세션 프레임 전체
        sessions/{user_id}/index.json         ← 세션 목록 인덱스
    """

    @abstractmethod
    async def save_session(self, ref: SessionRef, frames: list[AnySSEFrame]) -> None:
        """세션 종료 시 SSE 프레임 전체 저장 + 인덱스 갱신."""
        ...

    @abstractmethod
    async def load_frames(self, session_id: UUID, user_id: UUID) -> list[AnySSEFrame]:
        """저장된 세션 프레임 목록 반환. 세션 없으면 빈 리스트."""
        ...

    @abstractmethod
    async def list_sessions(self, user_id: UUID, limit: int = 20) -> list[SessionRef]:
        """유저의 세션 목록 최신순 반환. 세션 없으면 빈 리스트."""
        ...
