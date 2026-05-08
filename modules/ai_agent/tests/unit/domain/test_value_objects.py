import pytest

from common_schemas.exceptions import ValidationError

from ai_agent.domain.value_objects import QualityThreshold, TurnLimit


class TestTurnLimit:
    limit = TurnLimit()

    def test_max_is_25(self):
        assert TurnLimit.MAX == 25

    def test_validate_passes_under_limit(self):
        self.limit.validate(24)
        self.limit.validate(25)

    def test_validate_raises_over_limit(self):
        with pytest.raises(ValidationError) as exc_info:
            self.limit.validate(26)
        assert exc_info.value.code == "E_TURN_LIMIT_EXCEEDED"

    def test_is_exceeded(self):
        assert self.limit.is_exceeded(26) is True
        assert self.limit.is_exceeded(25) is False


class TestQualityThreshold:
    threshold = QualityThreshold()

    def test_min_score_is_8(self):
        assert QualityThreshold.MIN_SCORE == 8.0

    def test_is_pass_above(self):
        assert self.threshold.is_pass(9.0) is True

    def test_is_pass_boundary(self):
        assert self.threshold.is_pass(8.0) is True

    def test_is_pass_below(self):
        assert self.threshold.is_pass(7.9) is False
