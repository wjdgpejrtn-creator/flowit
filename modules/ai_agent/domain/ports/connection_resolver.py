from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class ConnectionResolver(ABC):
    """노드의 ``required_connections``를 사용자가 보유한 credential로 해소하는 Port.

    Composer가 draft를 만든 뒤(후처리), 각 노드가 요구하는 외부 서비스(provider)에
    대해 사용자가 이미 연결해 둔 활성 connection이 있으면 그 ``credential_id``를 찾아
    ``NodeInstance.credential_id``에 선바인딩한다. 이렇게 하면 사용자가 SSO로 연결한
    서비스(예: google) 노드는 검증 단계에서 ``E_MISSING_CONNECTION``을 띄우지 않는다.

    구현은 auth의 ``OAuthConnectionRepository``를 감싸는 adapter가 담당한다
    (provider 스코프 검증·실제 토큰 복호화는 실행 시점 ``CredentialInjectionService``가
    수행하므로 여기서는 credential_id 매핑만 책임진다).
    """

    @abstractmethod
    async def resolve(self, user_id: UUID, service: str) -> UUID | None:
        """``user_id``가 보유한 ``service`` 활성 connection의 credential_id를 반환.

        보유 connection이 없거나 비활성이면 ``None``을 반환한다(바인딩 생략).
        """
