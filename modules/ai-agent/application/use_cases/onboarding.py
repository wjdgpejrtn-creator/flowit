from __future__ import annotations

from typing import Any
from uuid import uuid4

from common_schemas import AgentState, DraftSpec, PermissionSource, SlotFillingState
from common_schemas.enums import AgentMode, ExecutionStatus

from ...domain.ports.agent_memory_repository import AgentMemoryRepository
from ...domain.services.onboarding_consultant import OnboardingConsultant
from ...domain.services.security_guard import SecurityGuard


class OnboardingUseCase:
    def __init__(
        self,
        security_guard: SecurityGuard,
        consultant: OnboardingConsultant,
        memory_repo: AgentMemoryRepository,
    ) -> None:
        self._guard = security_guard
        self._consultant = consultant
        self._memory_repo = memory_repo

    async def execute(
        self,
        message: str,
        permission: PermissionSource,
        state: AgentState | None = None,
    ) -> dict[str, Any]:
        """온보딩 세션 1턴을 처리한다.

        Returns:
            {"done": False, "question": str, "field": str}  — 추가 정보 필요
            {"done": True, "spec": dict}                    — 슬롯 모두 채워짐
        """
        self._guard.check(message, permission)

        if state is None:
            state = AgentState(
                session_id=uuid4(),
                user_id=permission.user_id,
                messages=[],
                turn_count=0,
                mode=AgentMode.ONBOARDING,
                execution_status=ExecutionStatus.RUNNING,
            )

        messages = [*state.messages, {"role": "user", "content": message}]
        result = await self._consultant.consult(state, messages)
        return result
