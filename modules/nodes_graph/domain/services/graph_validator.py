from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
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

# 데이터 흐름 참조 ${<instance_id>.<field>}. ai_agent dataflow_grounding의 동일 패턴이나
# 의존 방향 규칙(modules 간 역import 금지)상 공유 불가하여 각자 보유한다(Tarjan과 동일).
# token엔 점이 없으므로 첫 '.'로 instance_id ↔ field를 분리한다 (ADR-0023 L1).
_REF_TOKEN_RE = re.compile(r"\$\{([^.}]+)\.([^}]+)\}")

# JSON Schema 타입 → shape 분류. 1차 검증은 이 shape 레벨(scalar/array/object)만 본다.
# nested items / oneOf 정밀 검증은 스키마 보강 후 2차 스코프.
_SCALAR_TYPES = frozenset({"string", "number", "integer", "boolean"})


def _shape_of(json_type: Any) -> str | None:
    """JSON Schema의 type 값을 shape("scalar"/"array"/"object")으로 분류. 미선언/미상은 None."""
    if not isinstance(json_type, str):
        return None
    if json_type in _SCALAR_TYPES:
        return "scalar"
    if json_type in ("array", "object"):
        return json_type
    return None


def _resolve_output_path(
    output_schema: dict[str, Any] | None, segments: list[str]
) -> tuple[str, str | None]:
    """표현식 경로(``field`` / ``field.sub`` / ``field.0.sub``)를 output_schema의
    properties·items를 따라 walk해 분류한다 (Phase 2b nested 경로 검증).

    returns:
    - ``("ok", shape | None)``: 경로 끝까지 도달. shape=최종 타입 shape(타입 미선언이면 None).
    - ``("missing", seg)``: 경로가 스키마에서 끊김(properties에 없거나 scalar에 ``.subfield``
      접근) = 출력 경로 환각 → 호출부가 ``E_NODE_TYPE_MISMATCH``로 거부.
    - ``("unknown", None)``: 스키마 미정의(properties / items.properties 미선언) → 보수적 통과.

    array는 items로 내려가며, 숫자 인덱스 세그먼트는 원소 타입을 유지한 채 건너뛴다. object는
    properties로 내려간다. items/object 내부가 미정의면 깊은 검증이 불가하므로 보수적으로
    통과시킨다(동적 키 노드 — DB rows 등).
    """
    props = (output_schema or {}).get("properties")
    if not props:
        return ("unknown", None)
    head = segments[0]
    if head not in props:
        return ("missing", head)
    spec = props[head] or {}
    for seg in segments[1:]:
        t = spec.get("type")
        if t == "array":
            spec = spec.get("items") or {}
            if seg.isdigit():
                continue  # 인덱스 접근 → 원소 타입 유지
            iprops = spec.get("properties")
            if not iprops:
                return ("unknown", None)  # items 내부 미정의 → 보수적
            if seg not in iprops:
                return ("missing", seg)
            spec = iprops[seg] or {}
        elif t == "object":
            oprops = spec.get("properties")
            if not oprops:
                return ("unknown", None)  # object 내부 미정의 → 보수적
            if seg not in oprops:
                return ("missing", seg)
            spec = oprops[seg] or {}
        elif t is None:
            return ("unknown", None)  # 타입 미선언 → 보수적
        else:
            return ("missing", seg)  # scalar에 .subfield 접근 = 불가
    return ("ok", _shape_of(spec.get("type")))


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
        errors.extend(await self._check_type_compatibility(workflow))
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

    async def _check_type_compatibility(self, workflow: WorkflowSchema) -> list[ValidationErrorItem]:
        """표현식 경로(``${instance_id.field}``)의 출력 타입 ↔ 소비 파라미터 기대 타입 호환 검증.

        전수조사(2026-06-15) 결정: ``Edge.from_handle/to_handle``은 ``"true"/"false"`` 같은
        **제어 분기 라벨**이라 handle 기반 타입 검증은 무의미하다. 실제 IO 불일치는 노드
        ``parameters``에 박히는 데이터 참조 표현식에서 발생한다(staging 버그: sheets_read 2D
        배열 → gmail_send scalar 기대). 따라서 **표현식 경로**를 검증 대상으로 삼는다.

        1차 스코프 = **shape 레벨**(scalar↔array↔object) 불일치만 검출한다:
        - 검증 단위는 "값이 **정확히** 단일 표현식(``"${id.field}"``)"인 경우다. 문자열 보간
          (``"Total: ${id.field}"``)은 결과가 str로 합쳐지므로 str 컨텍스트로 보고 완화(통과).
        - str 파라미터: 기대 shape = ``input_schema.properties[param].type``.
        - **list 파라미터**: 기대 shape = ``input_schema.properties[param].items.type`` (원소
          기대 타입). 각 원소가 단일 표현식이면 그 출력 shape와 비교한다. staging 실데이터상
          실제 데이터 흐름의 주류가 ``to: ["${x.field}"]`` / ``operands: ["${x.field}", ...]``
          처럼 **list 원소 표현식**이라(2026-06-15 덤프), str-only로는 거의 못 잡는다.
        - 비교 대상은 upstream 출력 경로의 최종 타입(``_resolve_output_path``로 walk). shape가
          다르면 ``E_NODE_TYPE_MISMATCH``.
        - **Phase 2b nested 경로 검증** (#525 output_schema properties 보강 활용): field가
          ``items.email`` / ``messages.0.subject`` 같은 nested path면 properties·items를 따라
          walk한다. 첫 세그먼트(head)가 출력에 없거나 scalar에 ``.subfield`` 접근이면 **경로
          환각으로 거부**한다(staging ``to=None``의 execute 게이트 — grounding(#524)이 compose에서
          못 잡은 수동편집 경로를 막는다). items/object 내부가 미정의(동적 키 노드 — DB rows)면
          깊은 검증 불가라 **보수적 통과**.
        - 어느 한쪽이라도 type 미선언(``{}`` = ANY)이거나 output_schema 미선언이면 **보수적 통과**
          (false positive 방지).
        - 토큰이 instance_id(UUID)가 아니면(rewrite 전 잔재) skip — 런타임 ReferenceResolver가
          미해결로 graceful degrade한다.

        grounding(ai_agent ``ground_ref_fields``, #524)과 역할 분담: grounding은 **compose 시점**
        head 절단/보정, 본 validator는 **compose+execute 공통 게이트**(수동편집 워크플로우는
        grounding 미적용이라 validator만 탐).

        execution_engine ``CyclicScheduler``에는 대응 검증이 없다 — 본 타입검증은 ``validate``가
        스케줄러보다 엄격한 **의도된 비대칭**이다(``required_connections``/parameter 검증과 동일
        패턴). cycle parity(``test_validator_scheduler_parity``)는 타입 축과 무관하므로 유지된다.
        """
        errors: list[ValidationErrorItem] = []
        inst_map = {n.instance_id: n for n in workflow.nodes}
        def_cache: dict[UUID, Any] = {}

        async def _def(node_id: UUID) -> Any:
            if node_id not in def_cache:
                def_cache[node_id] = await self._repo.get_by_id(node_id)
            return def_cache[node_id]

        async def _check_ref(node: NodeInstance, param_key: str, raw: str, in_shape: str | None) -> None:
            """raw가 단일 표현식 전체일 때 출력 경로를 walk해 환각/shape 불일치를 errors에 보고."""
            if in_shape is None:
                return  # 소비측 기대 타입 미선언 → 보수적 통과
            m = _REF_TOKEN_RE.fullmatch(raw.strip())
            if m is None:
                return  # 리터럴 또는 문자열 보간 → str 컨텍스트, 검증 완화
            token, field = m.group(1), m.group(2)
            try:
                src_id = UUID(token)
            except ValueError:
                return  # 미해결 토큰
            src = inst_map.get(src_id)
            if src is None:
                return
            src_def = await _def(src.node_id)
            if src_def is None:
                return
            status, info = _resolve_output_path(src_def.output_schema, field.split("."))
            if status == "unknown":
                return  # 스키마 미정의(동적 키 노드 등) → 보수적 통과
            if status == "missing":
                # 출력에 없는 경로 참조 = 환각 (staging to=None의 execute 게이트).
                # grounding(compose)이 못 잡은 수동편집 경로를 validator가 거부한다.
                errors.append(ValidationErrorItem(
                    code=ErrorCode.E_NODE_TYPE_MISMATCH,
                    message=(
                        f"Unknown output path on '{param_key}': "
                        f"${{...}}.{field} (segment '{info}' not in output schema)"
                    ),
                    node_ids=[str(node.instance_id)],
                    validator="SchemaValidation",
                    hint="상류 노드 출력에 없는 필드 경로를 참조하고 있습니다.",
                ))
                return
            out_shape = info  # status == "ok"
            if out_shape is None or out_shape == in_shape:
                return  # 최종 타입 미선언 또는 호환 → 통과
            errors.append(ValidationErrorItem(
                code=ErrorCode.E_NODE_TYPE_MISMATCH,
                message=(
                    f"Type mismatch on '{param_key}': expects {in_shape} "
                    f"but ${{...}}.{field} yields {out_shape}"
                ),
                node_ids=[str(node.instance_id)],
                validator="SchemaValidation",
                hint="상류 노드의 출력 형태와 이 파라미터가 기대하는 형태가 다릅니다.",
            ))

        for node in workflow.nodes:
            consumer_def = await _def(node.node_id)
            if consumer_def is None:
                continue
            in_props = (consumer_def.input_schema or {}).get("properties") or {}
            for param_key, raw in (node.parameters or {}).items():
                spec = in_props.get(param_key) or {}
                if isinstance(raw, str):
                    await _check_ref(node, param_key, raw, _shape_of(spec.get("type")))
                elif isinstance(raw, list):
                    items_shape = _shape_of((spec.get("items") or {}).get("type"))
                    for el in raw:
                        if isinstance(el, str):
                            await _check_ref(node, param_key, el, items_shape)
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
