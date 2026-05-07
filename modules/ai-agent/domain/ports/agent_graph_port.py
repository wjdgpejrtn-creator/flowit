from __future__ import annotations

from abc import ABC, abstractmethod

from common_schemas import AgentState, PermissionSource


class AgentGraphPort(ABC):
    """LangGraph StateGraph 실행기의 인터페이스.

    구현체는 adapters/langgraph/graph_builder.py 에 위치한다.
    use case는 이 포트만 알고, LangGraph에 직접 의존하지 않는다.
    """

    @abstractmethod
    async def run(self, initial_state: AgentState, permission: PermissionSource) -> AgentState: ...
