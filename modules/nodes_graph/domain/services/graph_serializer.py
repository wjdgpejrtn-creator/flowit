from __future__ import annotations

from common_schemas import WorkflowSchema
from common_schemas.exceptions import ValidationError


class GraphSerializer:
    """워크플로우 직렬화/역직렬화 서비스."""

    def serialize(self, workflow: WorkflowSchema) -> dict:
        """WorkflowSchema → JSON-serializable dict."""
        return workflow.model_dump(mode="json")

    def deserialize(self, data: dict) -> WorkflowSchema:
        """dict → WorkflowSchema. 파싱 실패 시 ValidationError raise."""
        try:
            return WorkflowSchema.model_validate(data)
        except Exception as exc:
            raise ValidationError(f"Invalid workflow data: {exc}") from exc
