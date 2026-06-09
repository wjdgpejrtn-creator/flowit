from __future__ import annotations

from typing import Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel


class ConnectionAuditEntry(BaseModel):
    """관리자 자격증명 감사(Credential Audit) 1행 — OAuth connection + 소유자 식별 (REQ-002/003).

    관리자 화면(`/admin/credentials`)이 전사 OAuth connection을 소유자와 함께 나열하기 위한
    읽기 전용 read-model이다. `OAuthConnection` 엔티티에 소유자 표시 정보(email/name/department)를
    join으로 합성한 뷰 — 토큰(암호화된 access/refresh)은 절대 싣지 않는다(감사 화면에 불필요·민감).

    부서(`owner_department`)는 표시용 라벨(users.department) — NULL일 수 있다. 사용량/만료 같은
    지표는 현재 데이터 모델에 소스가 없어 포함하지 않는다(실 필드만 노출, 황대원 결정 2026-06-08).
    """

    oauth_id: UUID
    user_id: UUID
    owner_email: str
    owner_name: str
    owner_department: str | None = None
    service: Literal["google", "slack"]
    account_id: str | None = None
    display_name: str | None = None
    scopes: list[str]
    is_active: bool
    connected_at: UtcDatetime
    last_refreshed_at: UtcDatetime | None = None
