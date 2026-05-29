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
from ...domain.services.tool_execution_service import ToolExecutionService
from ...domain.value_objects import ToolOutput


class ExecuteToolUseCase:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        secure_connector: SecureConnectorPort,
        execution_svc: ToolExecutionService,
        risk_service: RiskAssessmentService,
        execution_repo: ToolExecutionRepository,
        credential_injection_svc: CredentialInjectionService,
    ) -> None:
        self._registry = tool_registry
        self._connector = secure_connector
        self._execution_svc = execution_svc
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
    ) -> ToolOutput:
        tool = self._registry.get(tool_name)
        self._risk.assess(tool, context)

        credential: PlaintextCredential | None = None
        if credential_id is not None:
            if node_id is None:
                raise CredentialError(
                    message="credential_id requires node_id",
                    code="E_CREDENTIAL_NODE_ID_MISSING",
                )
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
        output: ToolOutput | None = None

        try:
            output = await self._execution_svc.execute(
                tool, input_data, credential=credential, connector=self._connector
            )
            status = "success"
            return output

        except (AuthorizationError, ToolExecutionError, CredentialError) as e:
            error_msg = str(e)
            raise

        finally:
            duration_ms = int((time.monotonic() - start_ms) * 1000)

            try:
                record = ToolExecutionRecord(
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data=output.data if output is not None else None,
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
