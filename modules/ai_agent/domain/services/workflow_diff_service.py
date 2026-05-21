"""WorkflowDiffService — draft vs final 워크플로우 구조적 비교."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from common_schemas import WorkflowSchema


@dataclass(frozen=True)
class NodeDiff:
    node_id: UUID
    node_type: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ParameterChange:
    node_id: UUID
    node_type: str
    param_key: str
    before: Any
    after: Any


@dataclass(frozen=True)
class WorkflowDiff:
    """draft → final 변경 요약.

    Personalization Agent가 이 정보를 feedback MemoryEntry로 변환한다.
    """

    added_nodes: list[NodeDiff] = field(default_factory=list)
    removed_nodes: list[NodeDiff] = field(default_factory=list)
    modified_params: list[ParameterChange] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.added_nodes or self.removed_nodes or self.modified_params)

    def to_feedback_lines(self) -> list[str]:
        """사람이 읽을 수 있는 피드백 문장 리스트로 변환."""
        lines: list[str] = []
        for n in self.removed_nodes:
            lines.append(f"사용자가 AI 제안 노드를 삭제함: {n.node_type}")
        for n in self.added_nodes:
            lines.append(f"사용자가 노드를 추가함: {n.node_type}")
        for p in self.modified_params:
            lines.append(
                f"사용자가 {p.node_type}.{p.param_key}을(를) "
                f"{p.before!r} → {p.after!r}로 변경함"
            )
        return lines


class WorkflowDiffService:
    """draft(AI 제안)와 final(사용자 승인) workflow를 비교해 WorkflowDiff를 반환한다.

    domain service — 외부 의존성 없음. 순수 비교 로직만 포함.
    """

    def compute(self, draft: WorkflowSchema, final: WorkflowSchema) -> WorkflowDiff:
        draft_map = {n.instance_id: n for n in draft.nodes}
        final_map = {n.instance_id: n for n in final.nodes}

        draft_ids = set(draft_map)
        final_ids = set(final_map)

        removed = [
            NodeDiff(
                node_id=draft_map[iid].instance_id,
                node_type=str(draft_map[iid].node_id),
                parameters=dict(draft_map[iid].parameters),
            )
            for iid in draft_ids - final_ids
        ]

        added = [
            NodeDiff(
                node_id=final_map[iid].instance_id,
                node_type=str(final_map[iid].node_id),
                parameters=dict(final_map[iid].parameters),
            )
            for iid in final_ids - draft_ids
        ]

        modified: list[ParameterChange] = []
        for iid in draft_ids & final_ids:
            d_node = draft_map[iid]
            f_node = final_map[iid]
            all_keys = set(d_node.parameters) | set(f_node.parameters)
            for key in all_keys:
                before = d_node.parameters.get(key)
                after = f_node.parameters.get(key)
                if before != after:
                    modified.append(
                        ParameterChange(
                            node_id=iid,
                            node_type=str(d_node.node_id),
                            param_key=key,
                            before=before,
                            after=after,
                        )
                    )

        return WorkflowDiff(added_nodes=added, removed_nodes=removed, modified_params=modified)
