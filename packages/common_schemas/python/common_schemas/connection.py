from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConnectionStatus(BaseModel):
    """OAuth connection 연결 상태 — settings 통합 탭 + `GET /api/v1/connections` 응답 (ADR-0027).

    use case(`ListConnectionsUseCase`) 반환 ↔ api_server 응답 ↔ frontend 타입을 **단일 SSOT**로 공유.
    - ``display``: google=계정 이메일 / slack=workspace (미확보 시 None)
    - ``status``: ``"connected"`` | ``"expired"`` (expired는 토큰 refresh 연계)
    """

    model_config = ConfigDict(frozen=True)

    service: str
    connected: bool
    status: str
    display: Optional[str] = None
