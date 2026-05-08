from __future__ import annotations

from common_schemas.exceptions import ValidationError


class TurnLimit:
    MAX = 25

    def validate(self, count: int) -> None:
        if count > self.MAX:
            raise ValidationError(
                f"최대 턴 수({self.MAX})를 초과했습니다: {count}턴",
                code="E_TURN_LIMIT_EXCEEDED",
            )

    def is_exceeded(self, count: int) -> bool:
        return count > self.MAX
