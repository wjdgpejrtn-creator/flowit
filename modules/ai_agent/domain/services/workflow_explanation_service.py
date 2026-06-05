"""WorkflowExplanationService — 컨펌 게이트 신뢰 매니페스트 생성.

WorkflowSchema + DraftSpec + NodeConfig 목록에서 WorkflowExplanation을 결정론적으로 추출한다.
LLM 호출 없음 — 그래프 구조와 어긋날 위험 0.
"""
from __future__ import annotations

from collections import defaultdict, deque
from uuid import UUID

from common_schemas import DraftSpec, WorkflowSchema
from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance
from common_schemas.workflow_explanation import (
    ExplanationStep,
    PermissionItem,
    WorkflowExplanation,
)


class WorkflowExplanationService:
    """WorkflowSchema → WorkflowExplanation 결정론적 변환."""

    def explain(
        self,
        workflow: WorkflowSchema,
        spec: DraftSpec,
        node_configs: list[NodeConfig],
    ) -> WorkflowExplanation:
        config_by_node_id: dict[UUID, NodeConfig] = {c.node_id: c for c in node_configs}
        config_by_instance: dict[UUID, NodeConfig] = {
            inst.instance_id: config_by_node_id[inst.node_id]
            for inst in workflow.nodes
            if inst.node_id in config_by_node_id
        }

        ordered = _topological_sort(workflow.nodes, workflow.connections)

        steps: list[ExplanationStep] = []
        for order, instance in enumerate(ordered, start=1):
            cfg = config_by_instance.get(instance.instance_id)
            steps.append(
                ExplanationStep(
                    order=order,
                    node_name=cfg.name if cfg else instance.instance_id.hex[:8],
                    description=cfg.description if cfg else "",
                    risk_level=cfg.risk_level if cfg else RiskLevel.LOW,
                )
            )

        permissions = _collect_permissions(ordered, config_by_instance)
        assumptions = _collect_assumptions(ordered, config_by_instance)

        summary = (
            f"총 {len(steps)}개 노드로 구성된 워크플로우입니다. "
            f"{spec.natural_language_intent}"
        )

        return WorkflowExplanation(
            intent_restatement=spec.natural_language_intent,
            summary=summary,
            steps=steps,
            permissions=permissions,
            assumptions=assumptions,
        )


# ------------------------------------------------------------------ module-level helpers


def _topological_sort(
    nodes: list[NodeInstance],
    connections: list,
) -> list[NodeInstance]:
    """Kahn's algorithm — 사이클이 있거나 연결이 없으면 원래 순서 반환."""
    adj: dict[UUID, list[UUID]] = defaultdict(list)
    in_degree: dict[UUID, int] = {n.instance_id: 0 for n in nodes}

    for edge in connections:
        src: UUID = edge.from_instance_id
        dst: UUID = edge.to_instance_id
        if src in in_degree and dst in in_degree:
            adj[src].append(dst)
            in_degree[dst] += 1

    queue: deque[UUID] = deque(iid for iid, deg in in_degree.items() if deg == 0)
    instance_map = {n.instance_id: n for n in nodes}
    result: list[NodeInstance] = []

    while queue:
        iid = queue.popleft()
        result.append(instance_map[iid])
        for neighbor in adj[iid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 사이클 등으로 정렬 불완전 시 원래 순서 그대로
    return result if len(result) == len(nodes) else list(nodes)


def _collect_permissions(
    ordered: list[NodeInstance],
    config_by_instance: dict[UUID, NodeConfig],
) -> list[PermissionItem]:
    seen: set[tuple[str, str]] = set()
    items: list[PermissionItem] = []
    for instance in ordered:
        cfg = config_by_instance.get(instance.instance_id)
        if cfg is None:
            continue
        for conn in cfg.required_connections:
            key = (conn, cfg.name)
            if key not in seen:
                seen.add(key)
                items.append(
                    PermissionItem(
                        connection=conn,
                        node_name=cfg.name,
                        risk_level=cfg.risk_level,
                    )
                )
    return items


def _collect_assumptions(
    ordered: list[NodeInstance],
    config_by_instance: dict[UUID, NodeConfig],
) -> list[str]:
    assumptions: list[str] = []
    for instance in ordered:
        cfg = config_by_instance.get(instance.instance_id)
        if cfg is None:
            continue
        for param, value in instance.parameters.items():
            if value == "" or value is None:
                assumptions.append(
                    f"'{cfg.name}' 노드의 '{param}' 파라미터가 지정되지 않아 기본값으로 처리됩니다."
                )
    return assumptions
