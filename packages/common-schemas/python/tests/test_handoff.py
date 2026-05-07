from uuid import uuid4

from common_schemas.handoff import EvaluationResult, HandoffPayload


class TestHandoffPayload:
    def test_create(self):
        hp = HandoffPayload(
            handoff_type="recovery_mode",
            direction="forward",
            error_codes=["E_TIMEOUT"],
            error_messages=["Node timed out"],
            state_data={"retry_count": 2},
            correlation_id=uuid4(),
        )
        assert hp.handoff_type == "recovery_mode"
        assert hp.direction == "forward"

    def test_reverse_direction(self):
        hp = HandoffPayload(
            handoff_type="result_review",
            direction="reverse",
            error_codes=[],
            error_messages=[],
            state_data={},
            correlation_id=uuid4(),
        )
        assert hp.direction == "reverse"


class TestEvaluationResult:
    def test_create(self):
        er = EvaluationResult(
            score=0.85,
            pass_flag=True,
            reason="All criteria met",
            feedback="Good result",
        )
        assert er.pass_flag is True
        assert er.score == 0.85

    def test_failing_evaluation(self):
        er = EvaluationResult(
            score=0.3,
            pass_flag=False,
            reason="Missing required fields",
            feedback="Please include all mandatory parameters",
        )
        assert er.pass_flag is False
