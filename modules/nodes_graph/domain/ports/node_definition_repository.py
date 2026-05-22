from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.node_definition import NodeDefinition

__all__ = ["NodeDefinitionRepository"]


class NodeDefinitionRepository(ABC):
    """노드 정의 카탈로그 저장소 인터페이스.

    구현은 REQ-008(storage) / REQ-001(database)이 담당.
    H-4 합의: get_by_id() 반환값의 필드로 risk_level, required_connections, service_type에 접근한다.
    별도 get_risk_level() 등의 메서드를 추가하지 않는다.
    """

    @abstractmethod
    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        """노드 정의 생성 또는 갱신. Plugin discovery 시 53종 노드를 일괄 등록할 때 사용."""
        ...

    @abstractmethod
    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        """전체 노드 목록 조회. mvp_only=True면 is_mvp=True 노드만 반환."""
        ...

    @abstractmethod
    async def get_by_id(self, node_id: UUID) -> NodeDefinition | None:
        """node_id로 단일 노드 정의 조회. REQ-002 CredentialInjectionService가 이 메서드를 사용한다."""
        ...

    @abstractmethod
    async def search_by_embedding(
        self,
        query_embedding: list[float],
        limit: int = 10,
        viewer_user_id: UUID | None = None,
        viewer_team_ids: list[UUID] | None = None,
    ) -> list[NodeDefinition]:
        """벡터 유사도 기반 노드 검색. AI Agent(REQ-004)의 노드 추천에 사용.

        ADR-0020 (i) scope 격리: viewer 지정 시 가시 노드만 반환.
        필터 = (owner_user_id IS NULL AND team_id IS NULL)  # company 전역
               OR owner_user_id == viewer_user_id           # personal
               OR team_id IN viewer_team_ids                # team
        viewer_user_id/viewer_team_ids 모두 None이면 전역 노드만(비침습 기본).
        """
        ...
