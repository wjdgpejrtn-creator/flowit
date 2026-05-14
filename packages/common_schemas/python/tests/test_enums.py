from common_schemas.enums import AgentMode, ErrorCode, ExecutionStatus, RiskLevel


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
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.PAUSED == "paused"

    def test_member_count(self):
        assert len(ExecutionStatus) == 4


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
