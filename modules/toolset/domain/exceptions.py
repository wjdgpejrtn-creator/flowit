from __future__ import annotations

from common_schemas.exceptions import DomainError


class ToolExecutionError(DomainError):
    """외부 API 호출 실패. HTTP 502로 매핑."""


class CredentialError(DomainError):
    """자격증명 획득/복호화 실패. HTTP 401로 매핑."""


class ConflictError(DomainError):
    """도구 중복 등록 등 충돌. HTTP 409로 매핑."""
