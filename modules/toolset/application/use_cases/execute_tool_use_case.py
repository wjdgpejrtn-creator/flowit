from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from auth.domain.services import CredentialInjectionService
from common_schemas.exceptions import AuthorizationError
from common_schemas.security import PermissionSource, PlaintextCredential

from ...domain.entities.tool_execution_record import ToolExecutionRecord
from ...domain.exceptions import CredentialError, ToolExecutionError
from ...domain.ports.secure_connector_port import SecureConnectorPort
from ...domain.ports.tool_execution_repository import ToolExecutionRepository
from ...domain.ports.tool_registry import ToolRegistry
from ...domain.services.risk_assessment_service import RiskAssessmentService
from ...domain.services.runtime_validator import RuntimeValidator


class ExecuteToolUseCase:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        secure_connector: SecureConnectorPort,
        validator: RuntimeValidator,
        risk_service: RiskAssessmentService,
        execution_repo: ToolExecutionRepository,
        credential_injection_svc: CredentialInjectionService,
    ) -> None:
        self._registry = tool_registry
        self._connector = secure_connector
        self._validator = validator
        self._risk = risk_service
        self._repo = execution_repo
        self._credential_svc = credential_injection_svc

    async def execute(
        self,
        tool_name: str,
        input_data: dict,
        context: PermissionSource,
        credential_id: UUID | None = None,
        node_id: UUID | None = None,
    ) -> dict:
        tool = self._registry.get(tool_name)
        self._risk.assess(tool, context)
        self._validator.validate_input(input_data, tool.input_schema)

        credential: PlaintextCredential | None = None
        if credential_id is not None and node_id is not None:
            try:
                credential = await self._credential_svc.inject(credential_id, node_id)
            except Exception as e:
                raise CredentialError(
                    message=f"Failed to acquire credential: {e}",
                    code="E_CREDENTIAL_INJECTION_FAILED",
                ) from e

        start_ms = time.monotonic()
        status = "failed"
        error_msg: str | None = None
        result: dict = {}

        try:
            result = await tool.execute(input_data, credential=credential, connector=self._connector)
            self._validator.validate_output(result, tool.output_schema)
            status = "success"
            return result

        except (AuthorizationError, ToolExecutionError, CredentialError):
            raise

        except Exception as e:
            error_msg = str(e)
            raise ToolExecutionError(
                message=f"Tool '{tool_name}' execution failed: {e}",
                code="TOOL_EXECUTION_ERROR",
            ) from e

        finally:
            duration_ms = int((time.monotonic() - start_ms) * 1000)

            try:
                record = ToolExecutionRecord(
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data=result if status == "success" else None,
                    status=status,
                    duration_ms=duration_ms,
                    executed_at=datetime.now(timezone.utc),
                    error_message=error_msg,
                    node_id=node_id,
                    user_id=context.user_id,
                )
                await self._repo.save(record)
            except Exception:
                pass

            if credential is not None:
                credential.wipe()
