from __future__ import annotations

from uuid import UUID

from ...domain.entities.oauth_connection import OAuthConnection
from ...domain.ports.cipher_port import CipherPort
from ...domain.ports.credential_repository import CredentialRepository
from ...domain.ports.oauth_client_port import OAuthClientPort
from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository


class CompleteConnectionUseCase:
    """connection OAuth callback 처리 — code 교환 → 토큰 암호화 → credentials + oauth_connection 저장.

    ADR-0027:
    - ④ **upsert** — 같은 user+service active 있으면 update_tokens, 없으면 create
      (active partial unique index `idx_oauth_connections_user_service_active`(008:19-20) 충족, 미증식).
    - ③ **단일 트랜잭션** — credentials + oauth_connection write는 호출부(api_server) 단일 세션/트랜잭션.
    - account_id/display_name(#422) — google=sub/email (slack=team_id/workspace는 후속).
    """

    def __init__(
        self,
        oauth_repo: OAuthConnectionRepository,
        credential_repo: CredentialRepository,
        cipher: CipherPort,
        oauth_client: OAuthClientPort,
    ) -> None:
        self._oauth_repo = oauth_repo
        self._credential_repo = credential_repo
        self._cipher = cipher
        self._oauth_client = oauth_client

    async def execute(
        self, user_id: UUID, service: str, code: str, redirect_uri: str | None = None
    ) -> OAuthConnection:
        # redirect_uri는 authorize 때와 동일해야 google 토큰 교환이 통과한다(셀프리뷰 HIGH 수정).
        info = await self._oauth_client.exchange_code(code, redirect_uri)
        enc_access = self._cipher.encrypt(info["access_token"].encode())
        enc_refresh = self._cipher.encrypt(info.get("refresh_token", "").encode())
        scopes: list[str] = info.get("scopes", [])
        account_id = info.get("sub")  # google subject (slack=team_id 후속)
        display_name = info.get("email")  # google email (slack=workspace 후속)

        existing = await self._oauth_repo.get_active_for_user(user_id, service)
        if existing is not None:
            # ④ upsert — 기존 active 토큰 갱신 (active row 미증식)
            await self._credential_repo.update_data(existing.credential_id, enc_access)
            await self._oauth_repo.update_tokens(
                existing.credential_id,
                {"access_token_encrypted": enc_access, "refresh_token_encrypted": enc_refresh},
            )
            return existing

        credential = await self._credential_repo.create(
            user_id=user_id,
            name=f"{service} connection",
            credential_kind="oauth_token",
            encrypted_data=enc_access,
            metadata={"service": service, "scopes": scopes},
        )
        return await self._oauth_repo.create(
            user_id=user_id,
            service=service,
            tokens={
                "credential_id": credential.credential_id,
                "access_token_encrypted": enc_access,
                "refresh_token_encrypted": enc_refresh,
                "scopes": scopes,
                "account_id": account_id,
                "display_name": display_name,
            },
        )
