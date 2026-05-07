from __future__ import annotations

import json
from typing import Any

from common_schemas import EvaluationResult, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_PASS_THRESHOLD = 8.0

_SYSTEM_PROMPT = """You are a QA evaluator for workflow drafts.
Score the workflow on a scale of 0-10 based on:
- Completeness: all user requirements addressed
- Correctness: nodes are logically connected
- Safety: no high-risk nodes used without justification

Respond ONLY with JSON:
{"score": <0-10>, "pass_flag": <true/false>, "reason": "<string>", "feedback": "<string>"}
pass_flag must be true if and only if score >= 8.
"""


class QAEvaluatorService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def evaluate(
        self,
        workflow: WorkflowSchema,
        original_messages: list[dict[str, Any]],
    ) -> EvaluationResult:
        prompt_messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"workflow": workflow.model_dump(mode="json")},
                    ensure_ascii=False,
                ),
            },
            *original_messages,
        ]
        response = await self._llm.generate(prompt_messages)
        return self._parse(response)

    def _parse(self, response: dict[str, Any]) -> EvaluationResult:
        try:
            data = json.loads(response["content"])
            score = float(data["score"])
            return EvaluationResult(
                score=score,
                pass_flag=score >= _PASS_THRESHOLD,
                reason=data.get("reason", ""),
                feedback=data.get("feedback", ""),
            )
        except Exception as e:
            raise ExecutionError(f"EvaluationResult 파싱 실패: {e}", code="E_QA_PARSE")
