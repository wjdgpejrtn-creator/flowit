from __future__ import annotations

import re

from common_schemas import PermissionSource
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError, ValidationError

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(?!an?\s+AI)", re.I),
    re.compile(r"act\s+as\s+(if\s+you\s+(are|were)\s+)?(?!an?\s+AI)", re.I),
    re.compile(r"(system\s*prompt|hidden\s*instruction)", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"DAN\s+mode", re.I),
    re.compile(r"<\s*/?(?:system|prompt|instruction)\s*>", re.I),
    re.compile(r"(reveal|show|print|output)\s+(your\s+)?(system\s+prompt|instructions?)", re.I),
    re.compile(r"roleplay\s+as", re.I),
]

_MAX_INPUT_LENGTH = 2000


class SecurityGuard:
    def check(self, user_input: str, permission: PermissionSource) -> None:
        """입력 검증. 문제가 있으면 예외를 발생시킨다."""
        self._check_length(user_input)
        self._check_injection(user_input)
        self._check_risk_ceiling(permission)

    def _check_length(self, text: str) -> None:
        if len(text) > _MAX_INPUT_LENGTH:
            raise ValidationError(
                f"입력이 {_MAX_INPUT_LENGTH}자를 초과했습니다 ({len(text)}자).",
                code="E_INPUT_TOO_LONG",
            )

    def _check_injection(self, text: str) -> None:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                raise AuthorizationError(
                    "Prompt Injection 패턴이 감지되었습니다.",
                    code="E_PROMPT_INJECTION",
                )

    def _check_risk_ceiling(self, permission: PermissionSource) -> None:
        if permission.risk_ceiling not in ("High", "Restricted"):
            raise AuthorizationError(
                f"허용되지 않은 risk_ceiling: {permission.risk_ceiling}",
                code="E_PERMISSION_DENIED",
            )
