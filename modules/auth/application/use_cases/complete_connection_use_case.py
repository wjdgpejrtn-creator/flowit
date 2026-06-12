from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
      동시 callback race(get→create 사이)는 2번째 create가 이 index 위반(IntegrityError → `get_db`
      rollback). 데이터 정합 유지(active row 미증식) + 재시도 시 get_active→update_tokens로 치유.
      동시 callback이 극히 드물어 ON CONFLICT 대신 index 정합 + 재시도로 수용(셀프리뷰 ④).
    - ③ **단일 트랜잭션** — credentials + oauth_connection 2 write는 `get_db` request-단위 트랜잭션
      (repo는 flush only, 정상 종료 commit / 예외 rollback, `dependencies/database.py:99-101`).
      중간 실패 시 rollback으로 고아 credential 방지(셀프리뷰 ③).
    - account_id/display_name — exchange_code 정규화 계약(google=sub/email, slack=team_id/workspace).
    - service별 client 라우팅 — `oauth_clients[service]`(google/slack). 미배선 service는 ValueError.
    """

    def __init__(
        self,
        oauth_repo: OAuthConnectionRepository,
        credential_repo: CredentialRepository,
        cipher: CipherPort,
        oauth_clients: dict[str, OAuthClientPort],
    ) -> None:
        self._oauth_repo = oauth_repo
        self._credential_repo = credential_repo
        self._cipher = cipher
        # service별 OAuthClientPort 라우팅(google/slack). 미지원 service는 execute에서 ValueError.
        self._oauth_clients = oauth_clients

    async def execute(
        self, user_id: UUID, service: str, code: str, redirect_uri: str | None = None
    ) -> OAuthConnection:
        client = self._oauth_clients.get(service)
        if client is None:
            raise ValueError(f"No OAuth client wired for service: {service}")
        # redirect_uri는 authorize 때와 동일해야 provider 토큰 교환이 통과한다(셀프리뷰 HIGH 수정).
        info = await client.exchange_code(code, redirect_uri)
        enc_access = self._cipher.encrypt(info["access_token"].encode())
        refresh = info.get("refresh_token")
        enc_refresh = self._cipher.encrypt(refresh.encode()) if refresh else None  # 부재 시 None(클로버 방어, 조장 LOW)
        scopes: list[str] = info.get("scopes", [])
        # account_id/display_name = OAuthClientPort.exchange_code 정규화 계약(서비스 무관).
        # google=sub/email, slack=team_id/workspace를 각 어댑터가 이 키로 매핑해 반환한다.
        account_id = info.get("account_id")
        display_name = info.get("display_name")
        # #452 ② expires_in(초) → 절대 만료시각. _resolve_oauth가 이 값으로 선제 refresh 판정.
        # 미수신 시 None(레거시처럼 best-effort 갱신 대상).
        expires_at = self._compute_expires_at(info.get("expires_in"))

        existing = await self._oauth_repo.get_active_for_user(user_id, service)
        if existing is not None:
            # ④ upsert — 기존 active 토큰 갱신 (active row 미증식)
            await self._credential_repo.update_data(existing.credential_id, enc_access)
            # refresh 부재 시 refresh_token_encrypted 제외 → 기존 refresh 유지(클로버 방어, 조장 LOW).
            new_tokens: dict = {
                "access_token_encrypted": enc_access,
                "access_token_expires_at": expires_at,
            }
            if enc_refresh is not None:
                new_tokens["refresh_token_encrypted"] = enc_refresh
            await self._oauth_repo.update_tokens(existing.credential_id, new_tokens)
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
                "access_token_expires_at": expires_at,
            },
        )

    @staticmethod
    def _compute_expires_at(expires_in: int | None) -> datetime | None:
        if expires_in is None:
            return None
        return datetime.now(UTC) + timedelta(seconds=int(expires_in))
