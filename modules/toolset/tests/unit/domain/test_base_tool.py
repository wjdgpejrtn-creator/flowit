import pytest
from common_schemas.enums import RiskLevel

from toolset.domain.base_tool import BaseTool
from toolset.domain.entities.tool_metadata import ToolCategory


class TestBaseToolAbstractInterface:

    def test_missing_abstract_raises_type_error(self):
        with pytest.raises(TypeError):
            class BrokenTool(BaseTool):
                async def execute(self, input_data, **kwargs):
                    return {}
            BrokenTool()

    def test_complete_subclass_instantiates(self):
        class OkTool(BaseTool):
            name = "ok"
            description = "ok tool"
            version = "1.0.0"
            risk_level = RiskLevel.LOW
            category = ToolCategory.TRANSFORM
            capabilities = ["test"]
            input_schema = {"type": "object"}
            output_schema = {"type": "object"}
            async def execute(self, input_data, **kwargs):
                return {}

        tool = OkTool()
        assert tool.name == "ok"
        assert tool.description == "ok tool"
        assert tool.version == "1.0.0"
        assert tool.risk_level == RiskLevel.LOW
        assert tool.category == ToolCategory.TRANSFORM
        assert tool.capabilities == ["test"]
