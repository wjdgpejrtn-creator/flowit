from __future__ import annotations

import json

from common_schemas import DraftSpec, EvaluationResult, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort
from ..value_objects.quality_threshold import QualityThreshold

_THRESHOLD = QualityThreshold()

_SYSTEM_PROMPT = """You are a QA evaluator for workflow drafts.
Score the workflow on a scale of 0-10 based on:
- Completeness: all requirements in the DraftSpec are addressed
- Correctness: nodes are logically connected
- Safety: no high-risk nodes used without justification

Respond ONLY with JSON:
{"score": <0-10>, "pass_flag": <true/false>, "reason": "<string>", "feedback": "<string>"}
pass_flag must be true if and only if score >= 8.
"""


class QAEvaluatorService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def evaluate(self, workflow: WorkflowSchema, spec: DraftSpec) -> EvaluationResult:
        prompt = (
            _SYSTEM_PROMPT
            + f"\nDraftSpec intent: {spec.natural_language_intent}"
            + f"\nWorkflow: {json.dumps(workflow.model_dump(mode='json'), ensure_ascii=False)}"
        )
        response = await self._llm.generate(prompt)
        return self._parse(response)

    def _parse(self, response: str) -> EvaluationResult:
        try:
            data = json.loads(response)
            score = float(data["score"])
            return EvaluationResult(
                score=score,
                pass_flag=_THRESHOLD.is_pass(score),
                reason=data.get("reason", ""),
                feedback=data.get("feedback", ""),
            )
        except Exception as e:
            raise ExecutionError(f"EvaluationResult 파싱 실패: {e}", code="E_QA_PARSE")
