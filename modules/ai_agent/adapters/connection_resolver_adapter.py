from __future__ import annotations

from uuid import UUID

from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository

from ..domain.ports.connection_resolver import ConnectionResolver


class OAuthConnectionResolver(ConnectionResolver):
    """ConnectionResolver 구현 — auth.OAuthConnectionRepository Facade.

    ai_agent는 auth의 OAuth 저장소에 직접 의존하지 않고 이 어댑터를 통해서만 접근한다.
    노드가 요구하는 provider(service)에 대해 사용자의 활성 connection을 조회하고
    그 credential_id만 돌려준다. 토큰 복호화·provider 스코프 매칭은 실행 시점
    CredentialInjectionService의 책임이라 여기서 다루지 않는다.

    api_key 기반 provider(예: anthropic)는 OAuth connection이 없어 항상 None을 반환한다
    (사용자가 워크플로우 편집 시 직접 credential을 선택해야 하는 author-scoped 자원).
    """

    def __init__(self, oauth_repo: OAuthConnectionRepository) -> None:
        self._oauth_repo = oauth_repo

    async def resolve(self, user_id: UUID, service: str) -> UUID | None:
        conn = await self._oauth_repo.get_active_for_user(user_id, service)
        if conn is None or not conn.is_active:
            return None
        return conn.credential_id
