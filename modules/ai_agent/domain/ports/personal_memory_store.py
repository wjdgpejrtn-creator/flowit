from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from uuid import UUID

from ..entities.memory_file import MemoryFile, MemoryFileRef


class PersonalMemoryStore(ABC):
    """GCS 기반 사용자 개인 memory 저장소 Port.

    저장 구조:
        gs://{bucket}/users/{user_id}/
            MEMORY.md           ← 인덱스 (load_index / save_index)
            {name}.md           ← 개별 메모리 파일 (load_file / save_file / delete_file)
            {name}.emb.json     ← embedding 분리 저장 (load_embedding / save_embedding)
    """

    @abstractmethod
    async def load_index(self, user_id: UUID) -> list[MemoryFileRef]:
        """MEMORY.md를 파싱해 MemoryFileRef 목록 반환. 파일 없으면 빈 리스트."""
        ...

    @abstractmethod
    async def save_index(self, user_id: UUID, refs: list[MemoryFileRef]) -> None:
        """MemoryFileRef 목록을 MEMORY.md 형식으로 직렬화해 저장."""
        ...

    @abstractmethod
    async def load_file(self, user_id: UUID, filename: str) -> MemoryFile:
        """개별 .md 파일 로드 (frontmatter 파싱 포함). 파일 없으면 FileNotFoundError."""
        ...

    @abstractmethod
    async def save_file(self, user_id: UUID, file: MemoryFile) -> None:
        """개별 .md 파일 저장 (frontmatter + body). if_generation_match로 동시성 제어."""
        ...

    @abstractmethod
    async def delete_file(self, user_id: UUID, filename: str) -> None:
        """개별 .md 파일 삭제. 파일 없어도 오류 없이 무시."""
        ...

    @abstractmethod
    async def load_embedding(self, user_id: UUID, name: str) -> list[float] | None:
        """{name}.emb.json 로드. 파일 없으면 None 반환."""
        ...

    @abstractmethod
    async def save_embedding(self, user_id: UUID, name: str, embedding: list[float]) -> None:
        """{name}.emb.json 저장. if_generation_match로 동시성 제어."""
        ...

    async def claim_debounce_window(self, user_id: UUID, now: datetime, window: timedelta) -> bool:
        """debounce 윈도우를 CAS로 선점.

        - 마지막 claim으로부터 window 이내면 False (아직 윈도우 내)
        - 다른 인스턴스가 동시에 선점해 CAS 경쟁에서 패하면 False
        - 선점 성공 시 True
        구현체가 CAS 기반 debounce가 필요한 경우 override. 기본은 항상 선점 허용.
        """
        return True

    async def cleanup(self, user_id: UUID) -> None:
        """세션 종료 후 인메모리 캐시 해제 (기본 no-op; 구현체가 필요 시 override)."""
