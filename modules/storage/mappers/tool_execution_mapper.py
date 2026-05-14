from __future__ import annotations

from toolset.domain.entities.tool_execution_record import ToolExecutionRecord

from ..orm.tool_execution_model import ToolExecutionModel


class ToolExecutionMapper:
    @staticmethod
    def to_domain(orm: ToolExecutionModel) -> ToolExecutionRecord:
        return ToolExecutionRecord(
            execution_id=orm.tool_execution_id,
            tool_name=orm.tool_name,
            input_data=orm.input_data,
            output_data=orm.output_data,
            status=orm.status,
            duration_ms=orm.duration_ms,
            error_message=orm.error_message,
            executed_at=orm.executed_at,
        )

    @staticmethod
    def to_orm(entity: ToolExecutionRecord) -> ToolExecutionModel:
        return ToolExecutionModel(
            tool_execution_id=entity.execution_id,
            tool_name=entity.tool_name,
            input_data=entity.input_data,
            output_data=entity.output_data,
            status=entity.status,
            duration_ms=entity.duration_ms,
            error_message=entity.error_message,
            executed_at=entity.executed_at,
        )
