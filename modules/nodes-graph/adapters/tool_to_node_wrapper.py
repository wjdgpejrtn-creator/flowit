from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_DNS, uuid5

from common_schemas.enums import RiskLevel

from ..domain.entities.node_definition import NodeDefinition
from ..domain.entities.node_metadata import NodeMetadata


class ToolToNodeWrapper:
    """REQ-005 BaseTool → REQ-003 BaseNode 변환 어댑터.

    REQ-005 toolset 모듈의 BaseTool 인터페이스를 BaseNode 인터페이스로 래핑하여
    기존 도구를 워크플로우 노드로 사용할 수 있게 한다.
    """

    def __init__(self, tool: Any) -> None:
        self._tool = tool
        self.metadata = NodeMetadata(
            node_id=uuid5(NAMESPACE_DNS, tool.tool_id),
            name=tool.name,
            category=getattr(tool, "category", "external"),
            risk_level=getattr(tool, "risk_level", RiskLevel.LOW),
            is_mvp=getattr(tool, "is_mvp", False),
        )

    async def process(self, input: dict) -> dict:
        """tool.run() 호출을 BaseNode.process() 시그니처로 래핑."""
        credential = input.pop("credential", None)
        return await self._tool.run(params=input, credential=credential)

    def to_node_definition(self) -> NodeDefinition:
        """BaseTool 메타데이터로 NodeDefinition 엔티티 생성. RegisterNodesUseCase 등록 시 사용."""
        return NodeDefinition(
            node_id=self.metadata.node_id,
            node_type=getattr(self._tool, "tool_type", self._tool.name.lower().replace(" ", "_")),
            name=self.metadata.name,
            category=self.metadata.category,
            version=getattr(self._tool, "version", "1.0.0"),
            input_schema=getattr(self._tool, "input_schema", {}),
            output_schema=getattr(self._tool, "output_schema", {}),
            parameter_schema=getattr(self._tool, "parameter_schema", {}),
            risk_level=self.metadata.risk_level,
            required_connections=getattr(self._tool, "required_connections", []),
            description=getattr(self._tool, "description", ""),
            is_mvp=self.metadata.is_mvp,
            service_type=getattr(self._tool, "service_type", None),
        )
