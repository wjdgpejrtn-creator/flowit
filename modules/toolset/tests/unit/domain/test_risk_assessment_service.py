import pytest
from common_schemas.exceptions import AuthorizationError

from toolset.domain.services import RiskAssessmentService
from toolset.tests.fixtures import DummyTool, HighRiskDummyTool, RestrictedDummyTool


class TestRiskAssessmentService:

    def setup_method(self):
        self.service = RiskAssessmentService()

    def test_within_ceiling_returns_true(self, permission_high, dummy_tool):
        # MEDIUM tool, High ceiling → 통과
        assert self.service.assess(dummy_tool, permission_high) is True

    def test_exceeds_ceiling_raises_authorization_error(self, permission_high):
        # RESTRICTED tool, High ceiling → 거부 (RESTRICTED > High)
        with pytest.raises(AuthorizationError):
            self.service.assess(RestrictedDummyTool(), permission_high)

    def test_exact_ceiling_passes(self, permission_high, high_risk_tool):
        # HIGH tool, High ceiling → 통과 (같으면 허용)
        assert self.service.assess(high_risk_tool, permission_high) is True
