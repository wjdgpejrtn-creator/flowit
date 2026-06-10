from __future__ import annotations

import json

from common_schemas import DraftSpec, EvaluationResult, WorkflowSchema
from common_schemas.exceptions import ExecutionError
from pydantic import BaseModel

from ..ports.llm_port import LLMPort
from ..value_objects.quality_threshold import QualityThreshold

_THRESHOLD = QualityThreshold()

# QA LLM(Gemma)이 "누락 없음"을 빈 리스트 []가 아니라 ["none"]/["없음"]/["N/A"] 같은 센티넬
# 문자열로 채워 반환하는 경우가 잦다. 이를 실제 누락으로 오인하면 만점(score≥8)이어도
# 의도-노드 게이트가 pass_flag를 False로 막아, 완성된 워크플로우가 동일 draft를 무한
# 재시도(no-progress)→E_QA_EXHAUSTED("누락된 필수 노드/채널: none")로 헛돈다. 센티넬을
# 걸러 진짜 누락만 게이트에 반영한다.
_NO_MISSING_SENTINELS = frozenset(
    {
        "", "none", "n/a", "na", "null", "nil", "-", "—",
        "없음", "해당 없음", "해당없음", "no missing capabilities", "no missing",
    }
)


def _real_missing_capabilities(items: list[str]) -> list[str]:
    real: list[str] = []
    for item in items:
        normalized = str(item).strip().rstrip(".。!").lower()
        if normalized and normalized not in _NO_MISSING_SENTINELS:
            real.append(item)
    return real

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
        missing = _real_missing_capabilities(list(getattr(result, "missing_capabilities", []) or []))
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
