from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas import NodeConfig


class NodeRegistry(ABC):
    """nodes_graph NodeDefinitionRepository를 감싸는 퍼사드 포트.

    ai_agent는 NodeDefinitionRepository에 직접 의존하지 않고 이 인터페이스만 사용한다.
    구현체는 services/api_server DI에서 주입된다.
    """

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[NodeConfig]: ...

    @abstractmethod
    async def get_schema(self, node_id: UUID) -> NodeConfig: ...

    @abstractmethod
    async def list_structural(self) -> list[NodeConfig]:
        """구조 노드(트리거/제어흐름)를 관련성 무관하게 전부 반환한다.

        트리거("매주 월요일 9시")·분기·루프는 사용자 문장에 자연어로 녹아 노드 이름/설명
        임베딩과 매칭이 약해 ``search`` top-k에서 누락되곤 한다(#378 후속). Composer가 이
        목록을 검색 후보와 합집합해 drafter가 첫 초안부터 schedule_trigger 등을 쓸 수 있게 한다.
        """
        ...
