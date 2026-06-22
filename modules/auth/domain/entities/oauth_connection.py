from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel

# access token이 곧 만료될 때 실행 도중 만료(401)를 피하기 위한 선제 갱신 여유(초). #452 ②
TOKEN_REFRESH_SKEW_SECONDS = 60


class OAuthConnection(BaseModel):
    oauth_id: UUID
    user_id: UUID
    service: Literal["google", "slack"]
    credential_id: UUID
    access_token_encrypted: bytes
    refresh_token_encrypted: bytes | None = None
    scopes: list[str]
    # ADR-0027 settings 목록 display: 서비스측 안정 식별자(google=sub/slack=team_id)와
    # 표시명(google=email/slack=workspace). 미확보 경로는 None, 다음 connect/refresh 시 backfill.
    account_id: str | None = None
    display_name: str | None = None
    # #452 ② access token 만료시각(연결/갱신 시 now+expires_in). NULL=레거시(만료 미상) →
    # best-effort 갱신 대상. 갱신 성공 시 backfill되어 이후 정상 만료 판정.
    access_token_expires_at: UtcDatetime | None = None
    is_active: bool = True
    connected_at: UtcDatetime
    last_refreshed_at: UtcDatetime | None = None

    def revoke(self) -> None:
        self.is_active = False

    def needs_token_refresh(
        self, now: datetime, skew_seconds: int = TOKEN_REFRESH_SKEW_SECONDS
    ) -> bool:
        """access token이 만료/임박/미상이라 refresh가 필요한지 (#452 ②).

        - refresh_token이 없으면 갱신 수단이 없으므로 False (만료여도 갱신 불가).
        - expires_at NULL(레거시): True — best-effort 갱신으로 만료시각 backfill.
        - expires_at이 now+skew 이내: True — 실행 도중 만료 방지 선제 갱신.
        """
        if self.refresh_token_encrypted is None:
            return False
        if self.access_token_expires_at is None:
            return True
        return self.access_token_expires_at <= now + timedelta(seconds=skew_seconds)
