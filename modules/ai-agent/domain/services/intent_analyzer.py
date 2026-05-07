from __future__ import annotations

import json
from typing import Any

from common_schemas import IntentResult
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_SYSTEM_PROMPT = """You are an intent classifier for a workflow automation assistant.
Classify the user's latest message into one of four intents:
- clarify: user input is ambiguous, needs more information
- draft: user wants a new workflow created
- refine: user wants to modify an existing workflow
- propose: user is ready to accept the current proposal

Context will be provided as additional JSON. Use it to inform classification.

Respond ONLY with JSON: {"intent": "<intent>", "confidence": <0.0-1.0>, "analyzed_entities": {}}
"""


class IntentAnalyzerService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def analyze(self, messages: list[dict[str, Any]], context: dict[str, Any]) -> IntentResult:
        system_with_context = _SYSTEM_PROMPT
        if context:
            system_with_context += f"\nContext: {json.dumps(context, ensure_ascii=False)}"

        prompt = system_with_context + "\n\nMessages:\n" + json.dumps(messages, ensure_ascii=False)
        response = await self._llm.generate(prompt)
        return self._parse(response)

    def _parse(self, response: str) -> IntentResult:
        try:
            data = json.loads(response)
            return IntentResult(
                intent=data["intent"],
                confidence=float(data["confidence"]),
                analyzed_entities=data.get("analyzed_entities", {}),
            )
        except Exception as e:
            raise ExecutionError(f"IntentResult 파싱 실패: {e}", code="E_INTENT_PARSE")
