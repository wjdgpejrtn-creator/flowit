from common_schemas.enums import AgentMode, ErrorCode, ExecutionStatus, IntentType, RiskLevel


class TestAgentMode:
    def test_values(self):
        assert AgentMode.ONBOARDING == "onboarding"
        assert AgentMode.WIZARD == "wizard"
        assert AgentMode.EDIT == "edit"
        assert AgentMode.GENERAL == "general"
        assert AgentMode.SECURITY == "security"
        assert AgentMode.SKILL_BUILDER == "skill_builder"

    def test_member_count(self):
        assert len(AgentMode) == 6


class TestExecutionStatus:
    def test_values(self):
        assert ExecutionStatus.PENDING == "pending"
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.PAUSED == "paused"
        assert ExecutionStatus.CANCELLED == "cancelled"

    def test_member_count(self):
        assert len(ExecutionStatus) == 6


class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.LOW == "Low"
        assert RiskLevel.MEDIUM == "Medium"
        assert RiskLevel.HIGH == "High"
        assert RiskLevel.RESTRICTED == "Restricted"


class TestErrorCode:
    def test_values(self):
        assert ErrorCode.E_NODE_TYPE_MISMATCH == "E_NODE_TYPE_MISMATCH"
        assert ErrorCode.E_CYCLE_DETECTED == "E_CYCLE_DETECTED"
        assert ErrorCode.E_ISOLATED_NODE == "E_ISOLATED_NODE"

    def test_member_count(self):
        assert len(ErrorCode) == 7


class TestIntentType:
    def test_values(self):
        assert IntentType.CLARIFY == "clarify"
        assert IntentType.DRAFT == "draft"
        assert IntentType.REFINE == "refine"
        assert IntentType.PROPOSE == "propose"
        assert IntentType.BUILD_SKILL == "build_skill"

    def test_member_count(self):
        assert len(IntentType) == 5

    def test_str_compat(self):
        # str(IntentType) JSON 직렬화 호환 — Python 3.11 이전 호환 패턴
        assert IntentType.DRAFT.value == "draft"
        assert IntentType("draft") == IntentType.DRAFT
