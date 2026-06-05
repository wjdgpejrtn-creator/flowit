from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodeContext(BaseModel):
    """노드 1회 실행분의 컨텍스트 — 실행 메타 + 해결된 connection 토큰 (ADR-0018).

    `CatalogNodeExecutor`가 `BaseNode.process(input, context)`로 전달한다.
    `connection_token`은 connection이 필요한 노드만 사용 — domain 28종 및
    connection 무관 external 노드는 무시한다. 멀티커넥션 노드는 provider별
    `connection_tokens`에서 토큰을 꺼내 쓴다(`connection_token`은 단일 노드 하위호환용
    primary 토큰).
    """

    model_config = ConfigDict(frozen=False)

    execution_id: UUID
    user_id: UUID
    connection_token: Optional[str] = None
    # provider(service)별 connection 토큰 — 멀티커넥션 노드 실행 지원 (REQ-012).
    # CatalogNodeExecutor가 노드의 모든 required connection을 inject해 채운다.
    connection_tokens: dict[str, str] = Field(default_factory=dict)

    def wipe(self) -> None:
        """process() 종료 후 평문 connection 토큰 제거 (ADR-0018 Decision 5)."""
        self.connection_token = None
        self.connection_tokens = {}
