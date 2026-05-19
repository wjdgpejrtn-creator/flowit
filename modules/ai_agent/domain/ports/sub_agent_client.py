from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse


class SubAgentClient(ABC):
    """Sub-agent HTTP 호출 포트 (VPC 내부 통신).

    orchestrator → composer / skills_builder / personalization 단방향 스트리밍.
    각 sub-agent는 POST /v1/agent/route 엔드포인트를 노출해야 한다.
    """

    @abstractmethod
    def send(
        self, request: AgentProtocolRequest
    ) -> AsyncIterator[AgentProtocolResponse]:
        """AgentProtocolRequest를 sub-agent에 전송하고 SSE 응답 스트림을 반환."""
        ...
