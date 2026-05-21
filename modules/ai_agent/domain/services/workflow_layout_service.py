from __future__ import annotations

from collections import defaultdict, deque
from uuid import UUID

from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema

_X_ORIGIN = 100
_Y_ORIGIN = 100
_X_STEP = 250  # 레벨 간 수평 간격
_Y_STEP = 150  # 같은 레벨 내 수직 간격


class WorkflowLayoutService:
    """위상 정렬(Kahn's algorithm)으로 노드 x, y 좌표 자동 배치.

    connections 기반으로 DAG 레벨 계산 후 레벨별 노드 위치 할당.
    사이클이 있어도 미처리 노드는 마지막 레벨에 배치 (GraphValidator가 별도 검증).
    """

    def apply_layout(self, workflow: WorkflowSchema) -> WorkflowSchema:
        """워크플로우 노드에 위상 정렬 기반 x, y 좌표를 할당해 반환."""
        if not workflow.nodes:
            return workflow
        levels = self._compute_levels(workflow.nodes, workflow.connections)
        positioned = self._assign_positions(workflow.nodes, levels)
        return workflow.model_copy(update={"nodes": positioned})

    # ------------------------------------------------------------------ private

    def _compute_levels(
        self,
        nodes: list[NodeInstance],
        connections: list[Edge],
    ) -> dict[UUID, int]:
        in_degree: dict[UUID, int] = {n.instance_id: 0 for n in nodes}
        adjacency: dict[UUID, list[UUID]] = defaultdict(list)

        for edge in connections:
            if edge.to_instance_id in in_degree:
                in_degree[edge.to_instance_id] += 1
            if edge.from_instance_id in in_degree:
                adjacency[edge.from_instance_id].append(edge.to_instance_id)

        level: dict[UUID, int] = {}
        queue: deque[UUID] = deque()

        for node_id, deg in in_degree.items():
            if deg == 0:
                level[node_id] = 0
                queue.append(node_id)

        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                candidate = level[current] + 1
                if neighbor not in level or level[neighbor] < candidate:
                    level[neighbor] = candidate
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 사이클 등으로 처리 안 된 노드는 마지막 레벨 뒤에 배치
        max_level = max(level.values(), default=0)
        for node in nodes:
            if node.instance_id not in level:
                level[node.instance_id] = max_level + 1

        return level

    def _assign_positions(
        self,
        nodes: list[NodeInstance],
        levels: dict[UUID, int],
    ) -> list[NodeInstance]:
        level_groups: dict[int, list[NodeInstance]] = defaultdict(list)
        for node in nodes:
            level_groups[levels[node.instance_id]].append(node)

        positioned: list[NodeInstance] = []
        for lvl in sorted(level_groups):
            group = level_groups[lvl]
            total = len(group)
            for idx, node in enumerate(group):
                # 같은 레벨 내 수직 중앙 정렬
                y_offset = (idx - (total - 1) / 2) * _Y_STEP
                positioned.append(
                    node.model_copy(
                        update={
                            "position": Position(
                                x=_X_ORIGIN + lvl * _X_STEP,
                                y=_Y_ORIGIN + y_offset,
                            )
                        }
                    )
                )

        return positioned
