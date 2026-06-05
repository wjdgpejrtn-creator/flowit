from __future__ import annotations

import json

from common_schemas import DraftSpec, EvaluationResult, WorkflowSchema
from common_schemas.exceptions import ExecutionError
from pydantic import BaseModel

from ..ports.llm_port import LLMPort
from ..value_objects.quality_threshold import QualityThreshold

_THRESHOLD = QualityThreshold()

_SYSTEM_PROMPT = """You are a QA evaluator for workflow drafts.
Score the workflow on a scale of 0-10 based on:
- Completeness: nodes and connections cover the user's intent (required parameters are enforced separately by graph validation, so do not penalize optional parameters left as "" for values the user did not specify)
- Safety: no high-risk nodes used without justification

Note: structural correctness (DAG, cycles, execution order) is enforced by GraphValidator upstream — do not re-evaluate it here.

INTENT–NODE COVERAGE (critical): identify every distinct action/channel the user explicitly
requested (e.g. "read Gmail", "send to Slack", "summarize"). For each there must be a node that
fulfills it. List in `missing_capabilities` every requested action/channel that has NO
corresponding node in the workflow. If `missing_capabilities` is non-empty the workflow is
incomplete: score it below 8 and DO NOT contradict yourself by passing while telling the user to
add nodes.

pass_flag must be true if and only if score >= 8 AND missing_capabilities is empty.
"""


# LLM 응답 전용 — pass_flag는 score 임계 + missing_capabilities 공백으로 재계산하므로 수신 불필요.
class _EvalResponse(BaseModel):
    score: float
    reason: str = ""
    feedback: str = ""
    # 요청됐으나 노드로 충족 안 된 능력/채널 — 비어있지 않으면 점수 무관 fail (의도-노드 게이트, #378)
    missing_capabilities: list[str] = []


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
        # 의도-노드 게이트: 요청 채널/액션에 대응 노드가 빠졌으면(missing_capabilities) 점수와
        # 무관하게 fail — LLM이 만점 주면서 "노드 추가하라"는 자기모순(#378) 차단. missing은
        # feedback에 합쳐 retry 루프(→ drafter retry_feedback)가 교정하게 한다.
        missing = list(getattr(result, "missing_capabilities", []) or [])
        feedback = result.feedback
        if missing:
            gap = "누락된 필수 노드/채널: " + ", ".join(missing)
            feedback = f"{gap}\n{feedback}".strip() if feedback else gap
        return EvaluationResult(
            score=result.score,
            pass_flag=_THRESHOLD.is_pass(result.score) and not missing,
            reason=result.reason,
            feedback=feedback,
        )
