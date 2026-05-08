from common_schemas.enums import RiskLevel
from toolset.domain.base_tool import BaseTool


class DummyTool(BaseTool):
    name = "dummy"
    description = "테스트용 도구"
    version = "1.0.0"
    risk_level = RiskLevel.MEDIUM
    input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    output_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }

    async def execute(self, input_data: dict, **kwargs) -> dict:
        return {"result": f"ok: {input_data['message']}"}


class HighRiskDummyTool(BaseTool):
    name = "high_risk_dummy"
    description = "HIGH 위험도 테스트용"
    version = "1.0.0"
    risk_level = RiskLevel.HIGH
    input_schema = {"type": "object", "properties": {}}
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    async def execute(self, input_data: dict, **kwargs) -> dict:
        return {"ok": True}


class RestrictedDummyTool(BaseTool):
    name = "restricted_dummy"
    description = "RESTRICTED 위험도 테스트용"
    version = "1.0.0"
    risk_level = RiskLevel.RESTRICTED
    input_schema = {"type": "object", "properties": {}}
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    async def execute(self, input_data: dict, **kwargs) -> dict:
        return {"ok": True}
