"""WorkflowDiffService — draft vs final 워크플로우 구조적 비교."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from common_schemas import WorkflowSchema


@dataclass(frozen=True)
class NodeDiff:
    instance_id: UUID
    node_id: UUID                      # 카탈로그 참조 UUID (NodeConfig.node_id)
    parameters: dict[str, Any]
    node_type_name: str | None = None  # 호출자(Personalization/promote_node)가 NodeRegistry로 채움


@dataclass(frozen=True)
class ParameterChange:
    instance_id: UUID
    node_id: UUID                      # 카탈로그 참조 UUID
    param_key: str
    before: Any
    after: Any
    node_type_name: str | None = None  # 호출자가 채움


@dataclass(frozen=True)
class WorkflowDiff:
    """draft → final 변경 요약.

    Personalization Agent가 이 정보를 feedback MemoryEntry로 변환한다.
    node_type_name은 호출자(햄햄 Personalization / promote_node)가
    NodeRegistry를 통해 채운 뒤 to_feedback_lines()를 호출해야 의미 있는 출력이 나온다.
    """

    added_nodes: list[NodeDiff] = field(default_factory=list)
    removed_nodes: list[NodeDiff] = field(default_factory=list)
    modified_params: list[ParameterChange] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.added_nodes or self.removed_nodes or self.modified_params)

    def to_feedback_lines(self) -> list[str]:
        """피드백 문장 리스트 반환.

        node_type_name이 채워져 있으면 사람이 읽을 수 있는 타입명을 사용하고,
        없으면 node_id(UUID)를 fallback으로 사용한다.
        """
        lines: list[str] = []
        for n in self.removed_nodes:
            label = n.node_type_name or str(n.node_id)
            lines.append(f"사용자가 AI 제안 노드를 삭제함: {label}")
        for n in self.added_nodes:
            label = n.node_type_name or str(n.node_id)
            lines.append(f"사용자가 노드를 추가함: {label}")
        for p in self.modified_params:
            label = p.node_type_name or str(p.node_id)
            lines.append(
                f"사용자가 {label}.{p.param_key}을(를) "
                f"{p.before!r} → {p.after!r}로 변경함"
            )
        return lines


class WorkflowDiffService:
    """draft(AI 제안)와 final(사용자 승인) workflow를 비교해 WorkflowDiff를 반환한다.

    domain service — 외부 의존성 없음. 순수 비교 로직만 포함.
    node_type_name 해석은 호출자 책임 (NodeRegistry는 adapters 레이어 소유).
    """

    def compute(self, draft: WorkflowSchema, final: WorkflowSchema) -> WorkflowDiff:
        draft_map = {n.instance_id: n for n in draft.nodes}
        final_map = {n.instance_id: n for n in final.nodes}

        draft_ids = set(draft_map)
        final_ids = set(final_map)

        removed = [
            NodeDiff(
                instance_id=draft_map[iid].instance_id,
                node_id=draft_map[iid].node_id,
                parameters=dict(draft_map[iid].parameters),
            )
            for iid in draft_ids - final_ids
        ]

        added = [
            NodeDiff(
                instance_id=final_map[iid].instance_id,
                node_id=final_map[iid].node_id,
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
                            instance_id=iid,
                            node_id=d_node.node_id,
                            param_key=key,
                            before=before,
                            after=after,
                        )
                    )

        return WorkflowDiff(added_nodes=added, removed_nodes=removed, modified_params=modified)
