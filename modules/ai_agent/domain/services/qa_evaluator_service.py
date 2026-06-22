from __future__ import annotations

import json
from uuid import UUID

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

Each workflow node carries a `node_type` field — the catalog identifier of the node's capability
(e.g. `pdf_generate` produces a PDF file, `email_send`/`gmail_send` send email, `gmail_read` reads
Gmail, `slack_post_message` posts to Slack, `gemma_chat` summarizes/generates text,
`google_drive_upload` uploads a file). Identify each node's capability BY ITS `node_type`, never by
guessing from parameters. If a requested action/channel is fulfilled by a node whose `node_type`
matches, it is COVERED — you MUST NOT list it in `missing_capabilities`. When a producer node feeds
a delivery node via a connection (e.g. `pdf_generate` → `email_send`), treat the produced artifact
as delivered by that downstream node (the connection carries the artifact).

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

    async def evaluate(
        self,
        workflow: WorkflowSchema,
        spec: DraftSpec,
        node_types: dict[str, str] | dict[UUID, str] | None = None,
    ) -> EvaluationResult:
        """워크플로우 품질을 평가한다.

        ``node_types``(node_id→node_type)가 주어지면 직렬화에 각 노드의 node_type을 주입한다 —
        `NodeInstance`는 node_type을 안 들고 node_id(UUID)·parameters만 가지므로, 미주입 시 QA
        LLM이 노드 종류를 파라미터로 추론해야 해 `pdf_generate`({title,sections})를 "PDF 생성"으로
        못 알아보고 누락으로 오판하던 false-negative가 발생한다(데모 디버깅 2026-06-16). 키는
        str/UUID 혼용 허용(model_dump는 node_id를 str로 직렬화).
        """
        wf_dump = workflow.model_dump(mode="json")
        if node_types:
            lookup = {str(k): v for k, v in node_types.items()}
            for node in wf_dump.get("nodes", []):
                nt = lookup.get(str(node.get("node_id")))
                if nt:
                    node["node_type"] = nt
        prompt = (
            _SYSTEM_PROMPT
            + f"\nDraftSpec intent: {spec.natural_language_intent}"
            + f"\nWorkflow: {json.dumps(wf_dump, ensure_ascii=False)}"
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
        # 점수↔판정 정합: missing 게이트로 fail시키면서 만점 점수를 그대로 노출하면 "10/10
        # (재시도 필요)" 모순 표시가 된다(조장 e2e 발견). 게이트 발동 시 점수를 임계 미만으로
        # 낮춰 일치시킨다 — 누락 사유는 feedback이 보유(프롬프트도 "score below 8"을 지시하나
        # LLM이 종종 불이행). missing 없으면 LLM 점수 그대로.
        score = min(result.score, _THRESHOLD.MIN_SCORE - 1.0) if missing else result.score
        return EvaluationResult(
            score=score,
            pass_flag=_THRESHOLD.is_pass(score) and not missing,
            reason=result.reason,
            feedback=feedback,
        )
