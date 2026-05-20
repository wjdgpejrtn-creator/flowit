from __future__ import annotations

import json
from typing import Any

from common_schemas import IntentResult
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_SYSTEM_PROMPT = """You are an intent classifier for a workflow automation assistant.
Classify the user's latest message into one of five intents:
- clarify: user input is ambiguous, needs more information
- draft: user wants a new workflow created
- refine: user wants to modify an existing workflow
- propose: user is ready to accept the current proposal
- build_skill: user wants to build a reusable skill based on industry, department, or SOP document

When intent is "build_skill", include source_type in analyzed_entities:
- "industry_default": user mentions an industry (ecommerce, manufacturing, food, it, wholesale_retail, service)
  → also include "industry_code" (the detected industry key)
- "functional_domain": user mentions a department/function (hr, marketing, it_ops, customer_support, document_data)
  → also include "domain_code" (the detected domain key)
- "sop": user provides a procedure, guideline, or SOP document text

Context will be provided as additional JSON. Use it to inform classification.
"""


class IntentAnalyzerService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def analyze(self, messages: list[dict[str, Any]], context: dict[str, Any]) -> IntentResult:
        system_with_context = _SYSTEM_PROMPT
        if context:
            system_with_context += f"\nContext: {json.dumps(context, ensure_ascii=False)}"

        prompt = system_with_context + "\n\nMessages:\n" + json.dumps(messages, ensure_ascii=False)
        try:
            return await self._llm.generate_structured(prompt, IntentResult)
        except Exception as e:
            raise ExecutionError(f"IntentResult 파싱 실패: {e}", code="E_INTENT_PARSE")
