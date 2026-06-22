from __future__ import annotations

from collections import deque
from uuid import UUID

from common_schemas.enums import ErrorCode
from common_schemas.exceptions import ValidationError
from common_schemas.workflow import WorkflowSchema

from ..entities.execution_level import ExecutionLevel


class TopologicalScheduler:
    """Kahn's algorithm 기반 위상 정렬 스케줄러.

    동일 in-degree 노드를 같은 ExecutionLevel로 묶어
    병렬 실행 순서를 결정한다.
    """

    def validate_dag(self, workflow: WorkflowSchema) -> None:
        """순환 참조 검출. 발견 시 ValidationError 발생."""
        node_ids = {n.instance_id for n in workflow.nodes}
        in_degree: dict[UUID, int] = {nid: 0 for nid in node_ids}
        adjacency: dict[UUID, list[UUID]] = {nid: [] for nid in node_ids}

        for edge in workflow.connections:
            adjacency[edge.from_instance_id].append(edge.to_instance_id)
            in_degree[edge.to_instance_id] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(node_ids):
            raise ValidationError(
                "워크플로우에 순환 참조가 존재합니다",
                code=ErrorCode.E_CYCLE_DETECTED,
            )

    def schedule(self, workflow: WorkflowSchema) -> list[ExecutionLevel]:
        """Kahn's algorithm으로 병렬 실��� 레벨을 계산한다."""
        self.validate_dag(workflow)

        node_map = {n.instance_id: n for n in workflow.nodes}
        node_ids = set(node_map.keys())
        in_degree: dict[UUID, int] = {nid: 0 for nid in node_ids}
        adjacency: dict[UUID, list[UUID]] = {nid: [] for nid in node_ids}

        for edge in workflow.connections:
            adjacency[edge.from_instance_id].append(edge.to_instance_id)
            in_degree[edge.to_instance_id] += 1

        current_level_ids = [nid for nid, deg in in_degree.items() if deg == 0]
        levels: list[ExecutionLevel] = []
        level_num = 0

        while current_level_ids:
            level_nodes = [node_map[nid] for nid in current_level_ids]
            levels.append(ExecutionLevel(level=level_num, nodes=level_nodes))

            next_level_ids: list[UUID] = []
            for nid in current_level_ids:
                for neighbor in adjacency[nid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_level_ids.append(neighbor)

            current_level_ids = next_level_ids
            level_num += 1

        return levels
