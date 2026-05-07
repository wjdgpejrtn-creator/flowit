from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from common_schemas import AgentState, DraftSpec, SlotFillingState
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_SYSTEM_PROMPT = """You are a workflow onboarding consultant (Skills Wizard).
Your goal is to help users clarify what they want to automate.
Ask focused questions to fill in: what tool, what trigger, what output.
When all slots are filled, output {"done": true, "spec": {...}}.
Otherwise output {"done": false, "question": "<next question>", "field": "<field_name>"}.
"""


class OnboardingConsultant:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def consult(
        self,
        state: AgentState,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Returns either a clarifying question or a completed DraftSpec dict."""
        current_spec = state.draft_spec
        context = {
            "slot_state": current_spec.slot_filling_state.model_dump() if current_spec else {},
            "turn": current_spec.consultant_turn_count if current_spec else 0,
        }
        prompt_messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            *messages,
        ]
        response = await self._llm.generate(prompt_messages)
        try:
            return json.loads(response["content"])
        except Exception as e:
            raise ExecutionError(f"OnboardingConsultant 응답 파싱 실패: {e}", code="E_ONBOARDING_PARSE")
