from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from common_schemas import DraftSpec, Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.exceptions import ExecutionError
from pydantic import BaseModel

from ..ports.llm_port import LLMPort

_logger = logging.getLogger(__name__)

# 데이터 흐름 참조 ${<token>.<field>} — LLM은 token으로 node_type(fresh)/ref(edit)를 쓰고,
# 빌드 시 instance_id로 재작성한다(token엔 점 없음 → 첫 '.'로 분리, ADR-0023 L1).
_REF_TOKEN_RE = re.compile(r"\$\{([^.}]+)\.([^}]+)\}")


def _rewrite_refs(value: Any, id_by_token: dict[str, UUID]) -> Any:
    """파라미터 값 내 ``${<token>.<field>}``의 token을 instance_id로 치환.

    token이 맵에 없으면(존재하지 않는 노드 참조) 원본을 보존한다 — 실행 시점
    ReferenceResolver가 미해결로 graceful degrade한다.
    """
    if isinstance(value, str):
        def _sub(m: re.Match[str]) -> str:
            token, field = m.group(1), m.group(2)
            inst = id_by_token.get(token)
            return f"${{{inst}.{field}}}" if inst is not None else m.group(0)
        return _REF_TOKEN_RE.sub(_sub, value)
    if isinstance(value, list):
        return [_rewrite_refs(v, id_by_token) for v in value]
    if isinstance(value, dict):
        return {k: _rewrite_refs(v, id_by_token) for k, v in value.items()}
    return value


def _ground_ref_fields(value: Any, outputs_by_instance: dict[UUID, list[str]]) -> Any:
    """``${<instance_id>.<field>}`` 참조의 ``<field>``를 상류 노드의 실제 출력 필드에 grounding.

    `_rewrite_refs` 이후(토큰이 이미 instance_id로 치환된 상태) 호출한다. LLM이 존재하지 않는
    출력 필드를 환각하는 것(예: 출력이 ``[scheduled_at, ...]``인데 ``.values`` 참조)을 방어:

    - 참조 노드의 출력 필드 집합에 ``<field>``가 있으면 그대로 둔다.
    - 없고 그 노드의 출력이 **정확히 1개**면 그 단일 필드로 보정한다(거의 확실히 의도한 필드).
    - 없고 출력이 0개 또는 2개 이상이면(어느 필드인지 결정 불가) 원본을 보존하고 경고만 남긴다
      — 런타임 ReferenceResolver가 미해결로 graceful degrade한다. 잘못된 **소스 노드 선택**은
      의미 판단이라 결정론적으로 고칠 수 없으므로 로그로만 노출한다.
    - 토큰이 instance_id가 아니거나(미해결 토큰) 맵에 없는 노드면 손대지 않는다.
    """
    if isinstance(value, str):
        def _sub(m: re.Match[str]) -> str:
            token, field = m.group(1), m.group(2)
            try:
                inst = UUID(token)
            except ValueError:
                return m.group(0)
            outs = outputs_by_instance.get(inst)
            if outs is None or field in outs:
                return m.group(0)
            if len(outs) == 1:
                _logger.warning("ref 필드 보정: %s.%s → %s.%s", token, field, token, outs[0])
                return f"${{{token}.{outs[0]}}}"
            _logger.warning(
                "ref 필드 미존재(보정 불가, graceful degrade): %s.%s (outputs=%s)", token, field, outs
            )
            return m.group(0)
        return _REF_TOKEN_RE.sub(_sub, value)
    if isinstance(value, list):
        return [_ground_ref_fields(v, outputs_by_instance) for v in value]
    if isinstance(value, dict):
        return {k: _ground_ref_fields(v, outputs_by_instance) for k, v in value.items()}
    return value


def _outputs_of(nc: NodeConfig) -> list[str]:
    """NodeConfig의 출력 필드명 목록 (output_schema.properties 키)."""
    return list((nc.output_schema or {}).get("properties", {}).keys())


_SYSTEM_PROMPT = """You are a workflow drafter. Given a DraftSpec and candidate nodes,
output a JSON object matching this schema:
{
  "name": "<string>",
  "scope": "private",
  "is_draft": true,
  "nodes": [{"node_type": "<type>", "parameters": {"<param_key>": "<value>"}, "x": 0, "y": 0}],
  "connections": [{"from_node_type": "<type>", "to_node_type": "<type>", "from_handle": "output", "to_handle": "input"}]
}
Only use nodes from the provided candidate list.
Each node_type must appear at most once in the nodes list.
Connections define execution order: from_node_type runs before to_node_type.
Use "output" for from_handle and "input" for to_handle unless specific handles are needed.
Fill in `parameters` for each node using:
1. Values extracted from DraftSpec entities (e.g. schedule time, service names, channels).
2. The node's input_schema (a JSON Schema with `properties`, `required`, `default`) as a guide
   for which fields to fill. Fill every field listed in `required`; when the user did not specify
   a value, use the field's `default` if present.
3. Use an empty string "" only for optional fields the user did not specify that have no default.

Each candidate also carries `required_connections` — the external services it needs at runtime
(e.g. ["google"], ["slack"], ["anthropic"], or [] for none). When multiple candidates satisfy the
same step, prefer the one needing the fewest external connections, and do NOT add a
connection-requiring node the intent does not call for. Never invent credential values; required
connections are resolved separately after drafting.

DATA FLOW between nodes: when a node's input should receive data PRODUCED by an upstream node
(not a fixed value the user gave inline), set that parameter's value to a reference
"${<from_node_type>.<output_field>}". TWO hard rules — violating either produces a broken workflow:
1. SOURCE node: <from_node_type> MUST be a node whose output is SEMANTICALLY the data this input
   needs. Do not wire an unrelated node just to have a source (e.g. never feed a text-summary input
   from a scheduling/notification node). If NO candidate actually produces the needed data, leave
   the parameter as "" instead of referencing an unrelated node.
2. FIELD name: <output_field> MUST be copied VERBATIM from the chosen node's own `outputs` array.
   Never invent a field name, and never borrow a field name that belongs to a different node. If a
   node's `outputs` is ["a", "b"], its ONLY valid references are "${that_node.a}" and "${that_node.b}".
Also add a connection so the upstream node runs first. Use a literal string ONLY when the user
provided the value directly. Do NOT put placeholder prose like "the sheet data" where an upstream
output should flow in.
"""

# refine(대화형 수정) 전용 — 이전 워크플로우를 주고 "지시한 부분만" 고치게 한다.
# 노드 정체성을 node_type이 아니라 **안정적 ref**로 잡는다: 같은 node_type 노드가 둘 이상
# 있어도 ref로 구분되어 보존·편집이 모호하지 않다(node_type 키 방식의 중복 한계 해소).
_EDIT_SYSTEM_PROMPT = """You are EDITING an existing workflow. You are given CURRENT WORKFLOW whose
nodes each carry a stable "ref". Output a JSON object matching this schema:
{
  "name": "<string>",
  "scope": "private",
  "is_draft": true,
  "nodes": [{"ref": "<keep the SAME ref to preserve a node; use a new ref for an added node>",
             "node_type": "<type from the candidate list>", "parameters": {"<k>": "<v>"}, "x": 0, "y": 0}],
  "connections": [{"from_ref": "<ref>", "to_ref": "<ref>", "from_handle": "output", "to_handle": "input"}]
}
Apply ONLY the change requested in the DraftSpec intent. Preserve every OTHER node's ref, node_type,
and parameters EXACTLY, and keep unchanged connections. node_type must come from the candidate list.
The SAME node_type may appear multiple times — each is a distinct node identified by its ref.

DATA FLOW: to feed a node's input from an upstream node's output, set that parameter to
"${<ref>.<output_field>}" using the upstream node's "ref" (NOT its node_type). <output_field> MUST
be copied VERBATIM from that node's `outputs` in the candidate list — never invent a field name and
never borrow a field that belongs to a different node. Choose a source node whose output is
semantically the data the input needs; if none fits, leave "". Use a literal only for values the
user gave inline."""


# LLM 응답 전용 — common_schemas.WorkflowSchema의 owner_user_id/workflow_id 제외 부분집합.
# WorkflowSchema 필드 추가 시 이 모델도 확인 필요 (silent drift 방지).
class _NodeDraft(BaseModel):
    node_type: str
    parameters: dict[str, Any] = {}
    x: float = 0.0
    y: float = 0.0


class _EdgeDraft(BaseModel):
    from_node_type: str
    to_node_type: str
    from_handle: str = "output"
    to_handle: str = "input"


class _DraftResponse(BaseModel):
    name: str = "Untitled Workflow"
    scope: str = "private"
    is_draft: bool = True
    nodes: list[_NodeDraft] = []
    connections: list[_EdgeDraft] = []


# refine 편집 응답 전용 — node_type이 아니라 ref로 노드 정체성을 잡는다(중복 node_type 허용).
class _EditNodeDraft(BaseModel):
    ref: str
    node_type: str
    parameters: dict[str, Any] = {}
    x: float = 0.0
    y: float = 0.0


class _EditEdgeDraft(BaseModel):
    from_ref: str
    to_ref: str
    from_handle: str = "output"
    to_handle: str = "input"


class _EditResponse(BaseModel):
    name: str = "Untitled Workflow"
    scope: str = "private"
    is_draft: bool = True
    nodes: list[_EditNodeDraft] = []
    connections: list[_EditEdgeDraft] = []


class DrafterService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def draft(
        self,
        spec: DraftSpec,
        candidates: list[NodeConfig],
        owner_user_id: UUID,
        prior_workflow: WorkflowSchema | None = None,
    ) -> WorkflowSchema:
        """워크플로우 초안 생성. ``prior_workflow``가 주어지면(대화형 refine) 처음부터
        재생성하지 않고 그 워크플로우를 편집 컨텍스트로 주어 지시한 부분만 수정한다.
        직렬화 불가(후보에 없는 node_type 포함) 시엔 안전하게 fresh draft로 폴백한다.
        """
        catalog = [
            {
                "node_type": n.node_type,
                "name": n.name,
                "description": n.description,
                "required_connections": n.required_connections,
                "input_schema": n.input_schema,
                # 데이터 흐름 참조에 쓸 수 있는 출력 필드명 (ADR-0023 L1)
                "outputs": list((n.output_schema or {}).get("properties", {}).keys()),
            }
            for n in candidates
        ]
        spec_json = json.dumps(
            {"intent": spec.natural_language_intent, "entities": spec.discovered_entities},
            ensure_ascii=False,
        )
        catalog_json = json.dumps(catalog, ensure_ascii=False)
        # refine 편집 경로 — 직렬화 성공 시 ref 기반 편집 응답으로(중복 node_type 안전).
        # 직렬화 불가(후보에 없는 node_type)면 None → fresh draft로 폴백.
        if prior_workflow is not None:
            current = self._serialize_for_edit(prior_workflow, candidates)
            if current is not None:
                edit_prompt = (
                    _EDIT_SYSTEM_PROMPT
                    + f"\nDraftSpec: {spec_json}"
                    + f"\nAvailable nodes: {catalog_json}"
                    + f"\nCURRENT WORKFLOW: {json.dumps(current, ensure_ascii=False)}"
                )
                try:
                    edit_resp = await self._llm.generate_structured(edit_prompt, _EditResponse)
                except Exception as e:
                    raise ExecutionError(f"WorkflowSchema 파싱 실패: {e}", code="E_DRAFT_PARSE")
                return self._build_from_edit(edit_resp, candidates, owner_user_id)

        prompt = _SYSTEM_PROMPT + f"\nDraftSpec: {spec_json}" + f"\nAvailable nodes: {catalog_json}"
        try:
            draft_resp = await self._llm.generate_structured(prompt, _DraftResponse)
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 파싱 실패: {e}", code="E_DRAFT_PARSE")
        return self._build(draft_resp, candidates, owner_user_id)

    @staticmethod
    def _serialize_for_edit(
        workflow: WorkflowSchema, candidates: list[NodeConfig]
    ) -> dict[str, Any] | None:
        """이전 워크플로우를 LLM 편집용 **ref 기반** JSON으로 직렬화.

        각 노드에 안정적 ref(n0, n1, …)를 부여해 node_type이 중복돼도 정체성이 모호하지
        않게 한다. NodeInstance는 node_id만 가지므로 candidates로 node_type을 역매핑하며,
        한 노드라도 후보에 없으면 None을 반환해 호출부가 fresh draft로 폴백하게 한다(부분
        컨텍스트로 기존 노드를 잃는 것보다 안전).
        """
        type_by_id = {c.node_id: c.node_type for c in candidates}
        ref_by_instance: dict[UUID, str] = {}
        nodes: list[dict[str, Any]] = []
        for i, n in enumerate(workflow.nodes):
            node_type = type_by_id.get(n.node_id)
            if node_type is None:
                return None
            ref = f"n{i}"
            ref_by_instance[n.instance_id] = ref
            nodes.append({"ref": ref, "node_type": node_type, "parameters": n.parameters})
        connections: list[dict[str, str]] = []
        for edge in workflow.connections:
            from_ref = ref_by_instance.get(edge.from_instance_id)
            to_ref = ref_by_instance.get(edge.to_instance_id)
            if from_ref and to_ref:
                connections.append({
                    "from_ref": from_ref,
                    "to_ref": to_ref,
                    "from_handle": edge.from_handle,
                    "to_handle": edge.to_handle,
                })
        return {"name": workflow.name, "nodes": nodes, "connections": connections}

    def _build_from_edit(
        self, draft: _EditResponse, candidates: list[NodeConfig], owner_user_id: UUID
    ) -> WorkflowSchema:
        """ref 기반 편집 응답 → WorkflowSchema. node_type 대신 ref가 노드 정체성이라 동일
        node_type 다중 노드를 허용한다(중복 ref만 거부)."""
        try:
            node_map = {n.node_type: n for n in candidates}
            nodes: list[NodeInstance] = []
            ref_to_instance: dict[str, UUID] = {}
            for raw in draft.nodes:
                nc = node_map.get(raw.node_type)
                if nc is None:
                    raise ExecutionError(
                        f"후보 목록에 없는 node_type: {raw.node_type}",
                        code="E_UNKNOWN_NODE_TYPE",
                    )
                if raw.ref in ref_to_instance:
                    raise ExecutionError(f"ref 중복 사용 불가: {raw.ref}", code="E_DUPLICATE_REF")
                instance_id = uuid4()
                ref_to_instance[raw.ref] = instance_id
                nodes.append(
                    NodeInstance(
                        instance_id=instance_id,
                        node_id=nc.node_id,
                        parameters=raw.parameters,
                        position=Position(x=raw.x, y=raw.y),
                    )
                )

            # 데이터 흐름 참조 재작성 — LLM이 쓴 ref 토큰을 instance_id로 (ADR-0023 L1)
            # → grounding: 환각한 출력 필드를 상류 노드의 실제 output_schema에 맞춘다 (REQ-004 bug B)
            outputs_by_instance = {
                ref_to_instance[raw.ref]: _outputs_of(node_map[raw.node_type]) for raw in draft.nodes
            }
            nodes = [
                n.model_copy(
                    update={
                        "parameters": _ground_ref_fields(
                            _rewrite_refs(n.parameters, ref_to_instance), outputs_by_instance
                        )
                    }
                )
                for n in nodes
            ]

            connections: list[Edge] = []
            for edge in draft.connections:
                from_id = ref_to_instance.get(edge.from_ref)
                to_id = ref_to_instance.get(edge.to_ref)
                if from_id is None or to_id is None:
                    _logger.warning(
                        "엣지 건너뜀 — 알 수 없는 ref: %s → %s", edge.from_ref, edge.to_ref
                    )
                    continue
                connections.append(
                    Edge(
                        from_instance_id=from_id,
                        to_instance_id=to_id,
                        from_handle=edge.from_handle,
                        to_handle=edge.to_handle,
                    )
                )

            return WorkflowSchema(
                workflow_id=uuid4(),
                name=draft.name,
                scope=draft.scope,
                is_draft=True,
                nodes=nodes,
                connections=connections,
                owner_user_id=owner_user_id,
            )
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 빌드 실패: {e}", code="E_DRAFT_PARSE")

    def _build(self, draft: _DraftResponse, candidates: list[NodeConfig], owner_user_id: UUID) -> WorkflowSchema:
        try:
            node_map = {n.node_type: n for n in candidates}
            nodes: list[NodeInstance] = []
            instance_id_map: dict[str, UUID] = {}  # node_type → instance_id (1:1 보장)
            for raw in draft.nodes:
                nc = node_map.get(raw.node_type)
                if nc is None:
                    raise ExecutionError(
                        f"후보 목록에 없는 node_type: {raw.node_type}",
                        code="E_UNKNOWN_NODE_TYPE",
                    )
                if raw.node_type in instance_id_map:
                    raise ExecutionError(
                        f"node_type 중복 사용 불가: {raw.node_type}",
                        code="E_DUPLICATE_NODE_TYPE",
                    )
                instance_id = uuid4()
                instance_id_map[raw.node_type] = instance_id
                nodes.append(
                    NodeInstance(
                        instance_id=instance_id,
                        node_id=nc.node_id,
                        parameters=raw.parameters,
                        position=Position(x=raw.x, y=raw.y),
                    )
                )

            # 데이터 흐름 참조 재작성 — LLM이 쓴 node_type 토큰을 instance_id로 (ADR-0023 L1)
            # → grounding: 환각한 출력 필드를 상류 노드의 실제 output_schema에 맞춘다 (REQ-004 bug B)
            outputs_by_instance = {
                instance_id_map[ntype]: _outputs_of(node_map[ntype]) for ntype in instance_id_map
            }
            nodes = [
                n.model_copy(
                    update={
                        "parameters": _ground_ref_fields(
                            _rewrite_refs(n.parameters, instance_id_map), outputs_by_instance
                        )
                    }
                )
                for n in nodes
            ]

            connections: list[Edge] = []
            for edge in draft.connections:
                from_id = instance_id_map.get(edge.from_node_type)
                to_id = instance_id_map.get(edge.to_node_type)
                if from_id is None or to_id is None:
                    _logger.warning(
                        "엣지 건너뜀 — 알 수 없는 node_type: %s → %s",
                        edge.from_node_type,
                        edge.to_node_type,
                    )
                    continue
                connections.append(
                    Edge(
                        from_instance_id=from_id,
                        to_instance_id=to_id,
                        from_handle=edge.from_handle,
                        to_handle=edge.to_handle,
                    )
                )

            return WorkflowSchema(
                workflow_id=uuid4(),
                name=draft.name,
                scope=draft.scope,
                is_draft=True,
                nodes=nodes,
                connections=connections,
                owner_user_id=owner_user_id,
            )
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 빌드 실패: {e}", code="E_DRAFT_PARSE")
