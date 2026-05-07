from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas import NodeConfig


class NodeRegistry(ABC):
    """nodes-graph NodeDefinitionRepository를 감싸는 퍼사드 포트.

    ai-agent는 NodeDefinitionRepository에 직접 의존하지 않고 이 인터페이스만 사용한다.
    구현체는 services/api-server DI에서 주입된다.
    """

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[NodeConfig]: ...

    @abstractmethod
    async def get_schema(self, node_id: UUID) -> NodeConfig: ...
