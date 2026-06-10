from __future__ import annotations

from collections import defaultdict
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

# ADR-0023 L3: 루프 탈출 판정 기준이 되는 condition 노드의 category 값.
# execution_engine CyclicScheduler가 is_brancher = (category == "condition")로
# 동일 판정한다 (execute_workflow.py). 본 validator는 그 수용 기준을 미러한다.
_CONDITION_CATEGORY = "condition"


class GraphValidator:
    """워크플로우 그래프 무결성 검증 서비스.

    검증 항목:
    1. 비실재 노드 (node_id가 카탈로그에 없음 = 실행 불가)
    2. 중복 instance_id
    3. 사이클 감지 (Kahn's algorithm)
    4. 노드 타입 불일치 (from_handle ↔ to_handle)
    5. 고립 노드 검출
    6. 필수 연결 누락 (required_connections)
    7. 필수 파라미터 누락 (input_schema.required 중 NodeInstance.parameters에 없는 필드)
    """

    def __init__(self, node_def_repo: NodeDefinitionRepository) -> None:
        self._repo = node_def_repo

    async def validate(self, workflow: WorkflowSchema) -> ValidationErrorResponse:
        errors: list[ValidationErrorItem] = []

        # 비실재 노드는 가장 먼저 본다 — get_by_id None인 노드는 이후 검사들이 조용히 skip해
        # (definition None → continue) 통과해버리므로, 여기서 명시적으로 거부해야 한다.
        errors.extend(await self._check_node_existence(workflow.nodes))
        errors.extend(self._check_duplicate_ids(workflow.nodes))
        errors.extend(await self._detect_cycles(workflow.nodes, workflow.connections))
        errors.extend(self._check_type_compatibility(workflow.connections))
        errors.extend(self._detect_isolated_nodes(workflow.nodes, workflow.connections))
        errors.extend(await self._check_required_connections(workflow.nodes))
        errors.extend(await self._check_required_parameters(workflow.nodes))

        return ValidationErrorResponse(
            validation_status="failed" if errors else "passed",
            errors=errors,
        )

    async def _check_node_existence(
        self, nodes: list[NodeInstance]
    ) -> list[ValidationErrorItem]:
        """node_id가 카탈로그에 실재하는지 검증 (ADR-0026 §6.6 검증 게이트).

        LLM이 임시 생성한 비실재 노드(executor 없음)가 QA를 통과한 뒤 실행 단계에서 죽는
        것을 차단한다. 다른 검사들은 ``definition is None``이면 조용히 skip하므로(연결/파라미터
        검증이 미존재 노드를 그냥 통과시킴), 비실재 노드는 본 검사가 단일 책임으로 거부한다.
        execution_engine도 동일 GraphValidator를 쓰므로 compose+execute 공통 게이트가 된다.
        """
        unknown: list[str] = []
        for node in nodes:
            if await self._repo.get_by_id(node.node_id) is None:
                unknown.append(str(node.instance_id))
        if not unknown:
            return []
        return [ValidationErrorItem(
            code=ErrorCode.E_UNKNOWN_NODE_TYPE,
            message="Unknown node — node_id not found in catalog (non-executable)",
            node_ids=unknown,
            validator="SchemaValidation",
        )]

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

    async def _detect_cycles(
        self, nodes: list[NodeInstance], edges: list[Edge]
    ) -> list[ValidationErrorItem]:
        """순환을 SCC로 분해해 **탈출 불가능한 순환만** 거부한다 (ADR-0023 L3).

        비순환 그래프(모든 SCC가 trivial)는 기존대로 통과한다. non-trivial SCC(노드
        ≥2개 또는 self-loop = 루프 바디)는 **탈출 조건이 되는 condition 노드를 ≥1개**
        포함해야 허용한다. 없으면 무한 루프이므로 ``E_CYCLE_DETECTED``로 거부한다.

        execution_engine ``CyclicScheduler``의 수용 기준과 1:1로 정합한다 — 본 검증을
        통과한 draft는 엔진에서 실행 가능하고, 거부된 draft는 엔진에서도 거부된다.
        (max-iterations 가드·back-edge 분류는 엔진 책임이며 전역 default가 유한성을
        보장하므로, validator는 condition 노드의 **존재**만 검사한다.)
        """
        sccs = self._tarjan_sccs(nodes, edges)
        nontrivial = [comp for comp in sccs if self._is_nontrivial(comp, edges)]
        if not nontrivial:
            return []

        instance_to_node_id = {n.instance_id: n.node_id for n in nodes}
        unbreakable: list[str] = []
        for comp in nontrivial:
            has_condition = False
            for instance_id in comp:
                node_id = instance_to_node_id.get(instance_id)
                if node_id is None:
                    continue
                definition = await self._repo.get_by_id(node_id)
                if definition is not None and definition.category == _CONDITION_CATEGORY:
                    has_condition = True
                    break
            if not has_condition:
                unbreakable.extend(str(i) for i in comp)

        if not unbreakable:
            return []

        return [ValidationErrorItem(
            code=ErrorCode.E_CYCLE_DETECTED,
            message="Unbreakable cycle detected — a finite loop must contain a condition node to exit",
            node_ids=unbreakable,
            validator="SchemaValidation",
        )]

    @staticmethod
    def _is_nontrivial(comp: list[UUID], edges: list[Edge]) -> bool:
        """SCC가 루프 바디인지 — 노드 ≥2개 또는 self-loop면 True (CyclicScheduler와 동일)."""
        if len(comp) > 1:
            return True
        nid = comp[0]
        return any(e.from_instance_id == nid and e.to_instance_id == nid for e in edges)

    @staticmethod
    def _tarjan_sccs(nodes: list[NodeInstance], edges: list[Edge]) -> list[list[UUID]]:
        """Tarjan 알고리즘으로 강연결요소(SCC)를 계산한다 (반복 구현 — 재귀 한계 회피).

        execution_engine ``CyclicScheduler._tarjan_sccs``와 동일 알고리즘이나, 의존 방향
        규칙(services → modules, 역방향 import 금지)상 공유 불가하여 각자 보유한다.
        """
        ids = [n.instance_id for n in nodes]
        idset = set(ids)
        adj: dict[UUID, list[UUID]] = defaultdict(list)
        for e in edges:
            if e.from_instance_id in idset and e.to_instance_id in idset:
                adj[e.from_instance_id].append(e.to_instance_id)

        counter = 0
        index: dict[UUID, int] = {}
        lowlink: dict[UUID, int] = {}
        on_stack: dict[UUID, bool] = {}
        stack: list[UUID] = []
        sccs: list[list[UUID]] = []

        for root in ids:
            if root in index:
                continue
            work: list[tuple[UUID, int]] = [(root, 0)]
            while work:
                v, child_idx = work[-1]
                if child_idx == 0:
                    index[v] = counter
                    lowlink[v] = counter
                    counter += 1
                    stack.append(v)
                    on_stack[v] = True

                recursed = False
                neighbors = adj[v]
                for i in range(child_idx, len(neighbors)):
                    w = neighbors[i]
                    if w not in index:
                        work[-1] = (v, i + 1)
                        work.append((w, 0))
                        recursed = True
                        break
                    if on_stack.get(w):
                        lowlink[v] = min(lowlink[v], index[w])
                if recursed:
                    continue

                if lowlink[v] == index[v]:
                    comp: list[UUID] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        comp.append(w)
                        if w == v:
                            break
                    sccs.append(comp)

                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])

        return sccs

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
            required = definition.required_connections
            if not required:
                continue
            # provider별 바인딩 해소 — credential_ids(명시적) + legacy credential_id(단일).
            # required에 있는데 바인딩 안 된 provider만 정확히 보고한다(멀티커넥션 부분
            # 바인딩 시 어느 connection이 빠졌는지 식별 — REQ-012 credential 복수화).
            resolved = node.resolve_credentials(required)
            missing = [svc for svc in required if svc not in resolved]
            if missing:
                errors.append(ValidationErrorItem(
                    code=ErrorCode.E_MISSING_CONNECTION,
                    message=f"Node requires external connection(s) not bound: {missing}",
                    node_ids=[str(node.instance_id)],
                    validator="SchemaValidation",
                ))
        return errors

    async def _check_required_parameters(self, nodes: list[NodeInstance]) -> list[ValidationErrorItem]:
        """input_schema.required 중 NodeInstance.parameters에 없거나 빈값인 필드를 보고한다.

        ValidateGraphUseCase가 통과한 워크플로우는 execute 직전 worker `CatalogNodeExecutor`가
        node.parameters를 dataclass kwargs로 unpack하므로, required 필드가 비어있으면
        worker가 `__init__() missing positional argument` 런타임 에러를 던진다. 본 검사는
        그 갭을 사전 차단한다.
        """
        errors: list[ValidationErrorItem] = []
        for node in nodes:
            definition = await self._repo.get_by_id(node.node_id)
            if definition is None:
                continue
            input_schema = definition.input_schema or {}
            required = input_schema.get("required") or []
            if not required:
                continue
            params = node.parameters or {}
            missing = [
                field for field in required
                if params.get(field) in (None, "")
            ]
            if missing:
                errors.append(ValidationErrorItem(
                    code=ErrorCode.E_MISSING_REQUIRED_PARAMETER,
                    message=f"Required parameter(s) missing: {missing}",
                    node_ids=[str(node.instance_id)],
                    validator="SchemaValidation",
                    hint="NodeConfigDrawer에서 노드를 선택해 누락된 필드를 입력하세요.",
                ))
        return errors
