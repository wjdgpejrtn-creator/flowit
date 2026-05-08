from __future__ import annotations

from common_schemas import ValidationErrorResponse, WorkflowSchema

from ...domain.services.graph_validator import GraphValidator


class ValidateGraphUseCase:
    """워크플로우 그래프 무결성 검증 유스케이스."""

    def __init__(self, validator: GraphValidator) -> None:
        self._validator = validator

    async def execute(self, workflow: WorkflowSchema) -> ValidationErrorResponse:
        """
        1. workflow.validate_graph() — 기본 참조 무결성 (common_schemas 내장)
        2. GraphValidator.validate() — 정적/의미적 검증
        """
        if not workflow.validate_graph():
            from common_schemas import ValidationErrorItem
            from common_schemas.enums import ErrorCode
            return ValidationErrorResponse(
                validation_status="failed",
                errors=[ValidationErrorItem(
                    code=ErrorCode.E_ISOLATED_NODE,
                    message="Edge references non-existent node instance_id",
                    node_ids=[],
                    validator="SchemaValidation",
                )],
            )
        return await self._validator.validate(workflow)
