from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, Field

CredentialKind = Literal["api_key", "oauth_token", "password", "certificate", "custom"]


class Credential(BaseModel):
    """통합 credential 저장 엔티티 (DB: credentials 테이블, 002_credentials_*.sql).

    OAuth 토큰 / API key / 비밀번호 등을 암호화해 단일 저장소로 관리한다.
    `oauth_connections.credential_id`가 본 엔티티의 `credential_id`를 FK로 참조 —
    OAuth connection은 credentials row 하나를 backing으로 가진다.
    """

    credential_id: UUID
    user_id: UUID
    name: str
    credential_kind: CredentialKind
    encrypted_data: bytes
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: UtcDatetime
    updated_at: UtcDatetime
