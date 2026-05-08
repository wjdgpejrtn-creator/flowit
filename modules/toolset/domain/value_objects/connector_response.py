from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConnectorResponse:
    """SecureConnectorPort.connect() 반환 VO.

    adapter에서 httpx.Response → ConnectorResponse 변환 후 domain에 반환.
    domain 레이어가 httpx에 직접 의존하지 않도록 격리.
    """

    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300
