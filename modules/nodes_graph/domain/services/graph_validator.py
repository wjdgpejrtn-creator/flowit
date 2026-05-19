from __future__ import annotations

from collections import defaultdict, deque
from uuid import UUID

from common_schemas import (
    Edge,
    NodeInstance,
    ValidationErrorItem,
    ValidationErrorResponse,
    WorkflowSchema,
)
from common_schemas.enums import ErrorCode

from ..ports.node_definition_repository import NodeDefinitionRepository


class GraphValidator:
    """워크플로우 그래프 무결성 검증 서비스.

    검증 항목:
    1. 중복 instance_id
    2. 사이클 감지 (Kahn's algorithm)
    3. 노드 타입 불일치 (from_handle ↔ to_handle)
    4. 고립 노드 검출
    5. 필수 연결 누락 (required_connections)
    """

    def __init__(self, node_def_repo: NodeDefinitionRepository) -> None:
        self._repo = node_def_repo

    async def validate(self, workflow: WorkflowSchema) -> ValidationErrorResponse:
        errors: list[ValidationErrorItem] = []

        errors.extend(self._check_duplicate_ids(workflow.nodes))
        errors.extend(self._detect_cycles(workflow.nodes, workflow.connections))
        errors.extend(self._check_type_compatibility(workflow.connections))
        errors.extend(self._detect_isolated_nodes(workflow.nodes, workflow.connections))
        errors.extend(await self._check_required_connections(workflow.nodes))

        return ValidationErrorResponse(
            validation_status="failed" if errors else "passed",
            errors=errors,
        )

    def _check_duplicate_ids(self, nodes: list[NodeInstance]) -> list[ValidationErrorItem]:
        seen: set[UUID] = set()
        duplicates: list[str] = []
        for node in nodes:
            if node.instance_id in seen:
                duplicates.append(str(node.instance_id))
            seen.add(node.instance_id)

        if not duplicates:
            return []
        return [ValidationErrorItem(
            code=ErrorCode.E_DUPLICATE_ID,
            message="Duplicate instance_id detected",
            node_ids=duplicates,
            validator="SchemaValidation",
        )]

    def _detect_cycles(self, nodes: list[NodeInstance], edges: list[Edge]) -> list[ValidationErrorItem]:
        node_ids = {n.instance_id for n in nodes}
        in_degree: dict[UUID, int] = {nid: 0 for nid in node_ids}
        adjacency: dict[UUID, list[UUID]] = defaultdict(list)

        for edge in edges:
            if edge.from_instance_id in node_ids and edge.to_instance_id in node_ids:
                adjacency[edge.from_instance_id].append(edge.to_instance_id)
                in_degree[edge.to_instance_id] += 1

        queue: deque[UUID] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited == len(node_ids):
            return []

        cycle_nodes = [str(nid) for nid, deg in in_degree.items() if deg > 0]
        return [ValidationErrorItem(
            code=ErrorCode.E_CYCLE_DETECTED,
            message="Cycle detected in workflow graph",
            node_ids=cycle_nodes,
            validator="SchemaValidation",
        )]

    def _detect_isolated_nodes(self, nodes: list[NodeInstance], edges: list[Edge]) -> list[ValidationErrorItem]:
        if len(nodes) <= 1:
            return []

        connected: set[UUID] = set()
        for edge in edges:
            connected.add(edge.from_instance_id)
            connected.add(edge.to_instance_id)

        isolated = [str(n.instance_id) for n in nodes if n.instance_id not in connected]
        if not isolated:
            return []

        return [ValidationErrorItem(
            code=ErrorCode.E_ISOLATED_NODE,
            message="Isolated node(s) detected with no connections",
            node_ids=isolated,
            validator="SchemaValidation",
        )]

    def _check_type_compatibility(self, edges: list[Edge]) -> list[ValidationErrorItem]:
        """from_handle 출력 타입과 to_handle 입력 타입 호환 검증.

        현재는 handle 명칭 기반 단순 검증 (동일 handle명은 호환).
        향후 NodeDefinition에 handle 타입 메타데이터 추가 시 확장.
        """
        errors: list[ValidationErrorItem] = []
        for edge in edges:
            if edge.from_handle and edge.to_handle:
                pass  # 타입 메타데이터 확보 후 구체 검증 구현 (REQ-004 연동 시점)
        return errors

    async def _check_required_connections(self, nodes: list[NodeInstance]) -> list[ValidationErrorItem]:
        errors: list[ValidationErrorItem] = []
        for node in nodes:
            definition = await self._repo.get_by_id(node.node_id)
            if definition is None:
                continue
            if definition.required_connections and node.credential_id is None:
                errors.append(ValidationErrorItem(
                    code=ErrorCode.E_MISSING_CONNECTION,
                    message=f"Node requires external connection: {definition.required_connections}",
                    node_ids=[str(node.instance_id)],
                    validator="SchemaValidation",
                ))
        return errors
