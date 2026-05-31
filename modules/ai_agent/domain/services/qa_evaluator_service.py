from __future__ import annotations

import json

from pydantic import BaseModel

from common_schemas import DraftSpec, EvaluationResult, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort
from ..value_objects.quality_threshold import QualityThreshold

_THRESHOLD = QualityThreshold()

_SYSTEM_PROMPT = """You are a QA evaluator for workflow drafts.
Score the workflow on a scale of 0-10 based on:
- Completeness: nodes and connections cover the user's intent (required parameters are enforced separately by graph validation, so do not penalize optional parameters left as "" for values the user did not specify)
- Safety: no high-risk nodes used without justification

Note: structural correctness (DAG, cycles, execution order) is enforced by GraphValidator upstream — do not re-evaluate it here.

pass_flag must be true if and only if score >= 8.
"""


# LLM 응답 전용 — pass_flag는 _THRESHOLD.is_pass(score)로 재계산하므로 수신 불필요.
class _EvalResponse(BaseModel):
    score: float
    reason: str = ""
    feedback: str = ""


class QAEvaluatorService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def evaluate(self, workflow: WorkflowSchema, spec: DraftSpec) -> EvaluationResult:
        prompt = (
            _SYSTEM_PROMPT
            + f"\nDraftSpec intent: {spec.natural_language_intent}"
            + f"\nWorkflow: {json.dumps(workflow.model_dump(mode='json'), ensure_ascii=False)}"
        )
        try:
            result = await self._llm.generate_structured(prompt, _EvalResponse)
        except Exception as e:
            raise ExecutionError(f"EvaluationResult 파싱 실패: {e}", code="E_QA_PARSE")
        return EvaluationResult(
            score=result.score,
            pass_flag=_THRESHOLD.is_pass(result.score),
            reason=result.reason,
            feedback=result.feedback,
        )
