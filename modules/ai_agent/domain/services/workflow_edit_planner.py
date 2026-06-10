from __future__ import annotations

import json
import logging
from typing import Any

from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort
from .workflow_edit_service import EditPlan

_logger = logging.getLogger(__name__)

# refine 전용 — 발화를 **편집 연산 리스트**로 번역한다. 전체 워크플로우 재방출(_EditResponse)과
# 달리 안 바뀐 노드는 손대지 않으므로(연산만 적용) drift·QA 커버리지 오작동이 없다.
_PLAN_SYSTEM_PROMPT = """You are EDITING an existing workflow. Translate the user's edit instruction
into a MINIMAL list of operations on CURRENT WORKFLOW (whose nodes carry stable "ref"s n0,n1,…).
Output JSON: {"name": "<optional new name or null>", "ops": [ ... ]}.

Operation types (one JSON object per change):
- set_param    {"op","target_ref","parameters"}                       # change values on an existing node
- replace_node {"op","target_ref","new_node_type","parameters"}       # swap one node for another type
- add_node     {"op","new_node_type","parameters","after_ref"|"before_ref"}  # insert a node
- remove_node  {"op","target_ref"}                                    # delete a node

HARD RULES:
1. Emit ONLY the operations needed for the requested change. Do NOT touch unrelated nodes — they are
   preserved automatically. If the instruction changes one node's value, emit exactly one set_param.
2. "A 말고 B로" / "A를 B로 바꿔/변경" / "A 대신 B" = replace_node on A's ref with new_node_type B
   (NOT add_node — the user wants to swap, not append). "A 빼줘/제거/삭제" = remove_node. "추가/도
   넣어줘" = add_node.
3. new_node_type MUST be one of the provided "Available nodes" node_type values. Never invent a type.
4. On replace_node, map the old node's parameters onto the NEW node's input_schema fields (e.g. a Slack
   node's channel/text → a Gmail node's to/subject/body). Fill the new node's `required` fields; use the
   user-provided values where given, else reasonable values carried from the old node, else "".
5. target_ref/after_ref/before_ref MUST be refs that exist in CURRENT WORKFLOW.
6. To feed a value from an upstream node's output, use "${<ref>.<output_field>}" where <output_field> is
   copied verbatim from that node's `outputs`. Otherwise use literal values.
"""


class WorkflowEditPlanner:
    """발화 + 기존 워크플로우 + 노드 카탈로그 → 편집 연산(EditPlan). LLMPort만 의존."""

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def plan(
        self,
        prior_serialized: dict[str, Any],
        catalog: list[dict[str, Any]],
        instruction: str,
        retry_feedback: str | None = None,
    ) -> EditPlan:
        feedback_block = (
            f"\nThe previous attempt was rejected — fix this and retry: {retry_feedback}"
            if retry_feedback
            else ""
        )
        prompt = (
            _PLAN_SYSTEM_PROMPT
            + feedback_block
            + f"\nEdit instruction: {instruction}"
            + f"\nAvailable nodes: {json.dumps(catalog, ensure_ascii=False)}"
            + f"\nCURRENT WORKFLOW: {json.dumps(prior_serialized, ensure_ascii=False)}"
        )
        try:
            return await self._llm.generate_structured(prompt, EditPlan)
        except Exception as e:
            raise ExecutionError(f"EditPlan 파싱 실패: {e}", code="E_REFINE_PLAN_PARSE") from e
