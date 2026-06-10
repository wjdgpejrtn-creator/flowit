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
from ..value_objects.skeleton import AssembledDraft
from .skeleton_assembler import build_workflow_with_refs

_logger = logging.getLogger(__name__)

# 드래프터 프롬프트 다이어트 캡 — 컨텍스트 윈도우 초과 방지 (#413)
_MAX_CANDIDATES = 20   # 후보 노드 최대 수
_MAX_PATTERNS = 5      # 개인화 패턴 최대 수
_MAX_MOTIFS = 3        # 모티프 패턴 최대 수

# 캡에서 전수 보존할 우선 카테고리 — 스킬 바인딩 대상 LLM 노드(ai, #372)와 구조 노드
# (trigger/condition, #389). 호출부(composer)가 이들을 후보 풀 '끝'에 덧붙이므로 순서
# 무지하게 앞 N개만 자르면 풀>N일 때 보장 노드가 1순위로 드롭돼 바인딩이 조용히 실패한다.
# node_registry_adapter._STRUCTURAL_CATEGORIES({trigger,condition}) + ai를 미러 (도메인 정책).
_PRIORITY_CATEGORIES = frozenset({"ai", "trigger", "condition"})

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


def _slim_schema(schema: dict | None) -> dict:
    """input_schema에서 description/title 등 verbose 필드를 제거해 토큰 절감.

    LLM이 파라미터를 채우는 데 필요한 type·default·enum·required만 보존한다.
    """
    if not schema:
        return {}
    props = schema.get("properties") or {}
    slimmed = {}
    for k, v in props.items():
        entry: dict = {}
        for keep in ("type", "default", "enum"):
            if keep in v:
                entry[keep] = v[keep]
        slimmed[k] = entry
    result: dict = {"properties": slimmed}
    if schema.get("required"):
        result["required"] = schema["required"]
    return result


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

LOOPS (quality-gate / retry patterns): when the intent requires "regenerate if quality fails",
build a cycle using a back-edge:
1. Pick ONE ai node as the generator — do NOT add a second ai node for evaluation (that causes
   a duplicate node_type error). The same ai node is both the content producer and the retry target.
2. Use a condition node (e.g. if_condition) as the evaluator/branching point.
3. Add a forward connection generator → evaluator (from_handle="output", to_handle="input").
4. Add a BACK-EDGE connection evaluator → generator with from_handle="false" (the fail/retry
   branch) and to_handle="input". This back-edge creates the retry loop and is valid/required.
5. Add a forward exit connection evaluator → next_node with from_handle="true" (the pass branch).

MULTIPLE CONDITIONS: when the intent has OR/AND conditions (e.g. "긴급 or 장애"), use a SINGLE
condition node — do NOT create multiple if_condition nodes for each condition. One condition node
handles complex boolean logic.
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
user gave inline.

LOOPS (quality-gate / retry patterns): when adding or editing a loop cycle, use ref-based edges:
- Forward: {"from_ref": "<generator_ref>", "to_ref": "<evaluator_ref>", "from_handle": "output", "to_handle": "input"}
- BACK-EDGE (fail/retry): {"from_ref": "<evaluator_ref>", "to_ref": "<generator_ref>", "from_handle": "false", "to_handle": "input"}
- Exit (pass): {"from_ref": "<evaluator_ref>", "to_ref": "<next_ref>", "from_handle": "true", "to_handle": "input"}
Use ONE ai node as generator — do NOT add a second ai node for evaluation."""


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


# 스켈레톤 scaffold 경로 전용 — 구조는 코드가 결정(불변)하고 LLM은 ref별 parameters만 반환
# (ADR-0026 §6.6.3 step5). soft 구조 힌트(#416 효과0)와 달리 구조 생성 책임을 LLM에서 제거.
# top-level은 **list**(검증된 _DraftResponse와 동형) — 최상위 open dict는 attempt0 json-schema
# grammar에서 빈 객체로 trivially 만족돼 파라미터가 비는 위험이 있어 회피(modal_llm_adapter).
class _NodeParamFill(BaseModel):
    ref: str
    parameters: dict[str, Any] = {}


class _ParamFillResponse(BaseModel):
    name: str = "Untitled Workflow"
    nodes: list[_NodeParamFill] = []


_PARAM_FILL_SYSTEM_PROMPT = """You fill PARAMETERS for a workflow whose STRUCTURE IS ALREADY FIXED.
Do NOT invent, add, remove, or reorder nodes/edges — structure is decided by code.
For each node (identified by its stable "ref"), produce a `parameters` object whose keys match
that node's input_schema, derived from the user's request.

DATA FLOW — to use an upstream node's output, write "${<ref>.<field>}" where:
- <ref> is an EARLIER node in the list (nodes are given in execution order), and
- <field> is EXACTLY one of that node's listed "outputs". Never invent a field name not in "outputs"
  (e.g. do not write .output_text/.payload.text/.result if it is not listed) — an unlisted field
  silently breaks the data flow. If no suitable upstream output exists, write a literal value instead.

Return JSON: {"name": "<short workflow name>", "nodes": [{"ref": "<ref>", "parameters": {...}}, ...]}.
Only include refs from the provided node list. Omit a node entry if it needs no parameters."""


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
        personal_patterns: list[str] | None = None,
        skill_selected: bool = False,
        skill_composer_instructions: str | None = None,
        retry_feedback: str | None = None,
        dropped_node_types: list[str] | None = None,
        pattern_templates: list[Any] | None = None,
        skeleton_scaffold: AssembledDraft | None = None,
    ) -> WorkflowSchema:
        """워크플로우 초안 생성. ``prior_workflow``가 주어지면(대화형 refine) 처음부터
        재생성하지 않고 그 워크플로우를 편집 컨텍스트로 주어 지시한 부분만 수정한다.
        직렬화 불가(후보에 없는 node_type 포함) 시엔 안전하게 fresh draft로 폴백한다.

        ``personal_patterns``(RAG로 회수한 사용자 과거 패턴 본문)가 주어지면 시스템
        프롬프트에 "사용자 패턴" 블록으로 주입해, 이 사용자의 확립된 선호(예: 알림 채널,
        요약 언어/형식)가 이번 요청과 관련 있을 때 초안에 반영되게 한다(REQ-004 개인화 배선).

        ``skill_selected``가 True면(two-shot 스킬 선택) 그 스킬을 바인딩할 LLM 노드
        (category=="ai")를 반드시 포함하도록 프롬프트에 지시한다(#372 결함 A — 스킬은 LLM
        노드 system 프롬프트에 주입되는 지침서라 주입 대상 LLM 노드가 없으면 바인딩 불가).
        ``skill_composer_instructions``(COMPOSER.md 본문, 선택)가 주어지면 어떤 노드를 어떻게
        엮을지 구체 지침으로 함께 주입한다(미주어지면 LLM 노드 포함 기준선만 지시).

        ``retry_feedback``(validate/QA 실패 후 재시도 시, 선택)가 주어지면 별도 블록으로
        주입해 다음 초안을 교정한다. **`spec.natural_language_intent`에 섞지 않는다** — 그러면
        피드백 영어 텍스트가 워크플로우 이름/설명으로 누출되기 때문(#378 부차 — UI 누출).

        ``dropped_node_types``(선택, 출력용 리스트)가 주어지면 degrade로 버린 node_type
        (후보에 없어 떨군 것)을 거기에 append한다. 재시도 retriever가 QA-LLM 재인지가 아니라
        이 ground-truth로 직접 재검색하도록 결정화한다(#378 후속 리뷰 #2). 호출부가 요청마다
        새 리스트를 넘기므로 동시 요청 안전(서비스 인스턴스 공유 무관).

        ``skeleton_scaffold``(ADR-0026 §6.6)가 주어지면(refine 아닐 때) **구조를 코드가 결정**한
        결정적 골격에 LLM이 **파라미터만** 채운다 — soft 구조 힌트(#416 효과0)와 달리 구조
        생성 책임을 LLM에서 제거. scaffold 경로 실패 시 일반 LLM draft로 폴백(non-fatal).
        """
        if skeleton_scaffold is not None and prior_workflow is None:
            try:
                return await self._fill_scaffold_params(
                    skeleton_scaffold, candidates, spec, owner_user_id, retry_feedback
                )
            except Exception as exc:
                # 구조는 결정적이지만 파라미터 채움이 실패하면 일반 LLM draft로 폴백(완전 산출 보장).
                _logger.warning("스켈레톤 scaffold 파라미터 채움 실패 — 일반 draft 폴백: %s", exc)
        # 프롬프트 다이어트 — 컨텍스트 윈도우 초과 방지 (#413). 단 순서 무지하게 앞에서
        # 자르면 풀 끝에 붙은 보장 노드(ai 바인딩 대상·구조 노드)가 1순위로 드롭되므로
        # (리뷰 MED #1), 우선 카테고리는 전수 보존하고 나머지에서만 잘라 합을 캡 이하로 맞춘다.
        # 우선 노드만으로 캡을 넘으면 정확성(바인딩) 우선으로 전수 유지한다.
        if len(candidates) > _MAX_CANDIDATES:
            # **refine 편집 시 prior 워크플로우 노드는 캡에서 무조건 보존(#369)**. augment가 prior
            # 노드를 풀 '끝'에 덧붙이는데, 비-우선 카테고리(integration/action 등)면 순서 무지 캡이
            # 1순위로 떨궜다 → `_serialize_for_edit`이 그 노드를 candidates에서 못 찾아 편집 직렬화가
            # 실패(E_REFINE_SERIALIZE)했다(google_sheets_read 등). prior 노드를 우선군에 포함시킨다.
            prior_ids = {n.node_id for n in prior_workflow.nodes} if prior_workflow else frozenset()

            def _is_priority(c: NodeConfig) -> bool:
                return getattr(c, "category", None) in _PRIORITY_CATEGORIES or c.node_id in prior_ids

            priority = [c for c in candidates if _is_priority(c)]
            rest = [c for c in candidates if not _is_priority(c)]
            capped = priority + rest[: max(0, _MAX_CANDIDATES - len(priority))]
            _logger.warning(
                "후보 %d건 → %d건 캡 적용 (prompt diet; 우선/prior %d건 보존)",
                len(candidates),
                len(capped),
                len(priority),
            )
            candidates = capped
        capped_patterns = (personal_patterns or [])[:_MAX_PATTERNS]
        capped_motifs = (pattern_templates or [])[:_MAX_MOTIFS] if pattern_templates else pattern_templates

        catalog = [
            {
                "node_type": n.node_type,
                "name": n.name,
                "description": n.description,
                "required_connections": n.required_connections,
                # description/title 제거한 경량 스키마 — type/default/enum/required만 보존
                "input_schema": _slim_schema(n.input_schema),
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
        patterns_block = self._personal_patterns_block(capped_patterns)
        binding_block = self._skill_binding_block(skill_selected, skill_composer_instructions)
        retry_block = self._retry_feedback_block(retry_feedback)
        motif_block = self._motif_block(capped_motifs)
        # refine 편집 경로 — ref 기반 편집 응답으로 "지시한 부분만" 고친다(중복 node_type 안전).
        # **편집 잠금(조장 지시 2026-06-10)**: prior가 주어지면 절대 fresh draft로 재생성하지
        # 않는다. 직렬화 불가(기존 노드가 후보에 없음)면 폴백 대신 **에러** — 사용자가 쌓은
        # 워크플로우를 조용히 2노드로 갈아엎던 회귀(#369) 차단. 호출부가 prior 노드를
        # candidates에 보강(`_augment_candidates_with_prior`)하므로 정상 경로에선 직렬화 성공.
        if prior_workflow is not None:
            current = self._serialize_for_edit(prior_workflow, candidates)
            if current is None:
                raise ExecutionError(
                    "기존 워크플로우를 편집용으로 직렬화하지 못했습니다(노드 복원 실패) — "
                    "새로 생성하지 않습니다.",
                    code="E_REFINE_SERIALIZE",
                )
            edit_prompt = (
                _EDIT_SYSTEM_PROMPT
                + patterns_block
                + binding_block
                + motif_block
                + retry_block
                + f"\nDraftSpec: {spec_json}"
                + f"\nAvailable nodes: {catalog_json}"
                + f"\nCURRENT WORKFLOW: {json.dumps(current, ensure_ascii=False)}"
            )
            try:
                edit_resp = await self._llm.generate_structured(edit_prompt, _EditResponse)
            except Exception as e:
                raise ExecutionError(f"WorkflowSchema 파싱 실패: {e}", code="E_DRAFT_PARSE") from e
            return self._build_from_edit(edit_resp, candidates, owner_user_id)

        prompt = (
            _SYSTEM_PROMPT
            + patterns_block
            + binding_block
            + motif_block
            + retry_block
            + f"\nDraftSpec: {spec_json}"
            + f"\nAvailable nodes: {catalog_json}"
        )
        try:
            draft_resp = await self._llm.generate_structured(prompt, _DraftResponse)
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 파싱 실패: {e}", code="E_DRAFT_PARSE")
        return self._build(draft_resp, candidates, owner_user_id, dropped_sink=dropped_node_types)

    async def _fill_scaffold_params(
        self,
        scaffold: AssembledDraft,
        candidates: list[NodeConfig],
        spec: DraftSpec,
        owner_user_id: UUID,
        retry_feedback: str | None,
    ) -> WorkflowSchema:
        """결정적 스켈레톤 골격에 LLM 파라미터만 채워 완성 (ADR-0026 §6.6.3 step5).

        구조(노드/엣지)는 ``build_workflow_with_refs``가 코드로 빌드 — LLM 출력은 parameters에만
        적용하고 구조는 절대 바꾸지 않는다(결정적 보장). 데이터흐름 ``${ref.field}`` 참조는 _build와
        동일하게 instance_id로 rewrite + 상류 output_schema로 grounding한다(ADR-0023 L1).
        """
        node_id_by_type = {c.node_type: c.node_id for c in candidates}
        cfg_by_type = {c.node_type: c for c in candidates}
        wf, ref_to_iid = build_workflow_with_refs(scaffold, node_id_by_type, owner_user_id)
        if not wf.nodes:
            raise ExecutionError("scaffold node_type이 후보에 없음", code="E_DRAFT_PARSE")

        # ref_to_iid는 scaffold.nodes(슬롯=실행) 순서 보존 → 프롬프트의 "execution order"와 정합.
        ref_node_types = {dn.ref: dn.node_type for dn in scaffold.nodes}
        node_specs = [
            {
                "ref": ref,
                "node_type": ref_node_types[ref],
                "name": getattr(cfg_by_type.get(ref_node_types[ref]), "name", ref_node_types[ref]),
                "input_schema": _slim_schema(
                    getattr(cfg_by_type.get(ref_node_types[ref]), "input_schema", None)
                ),
                # 상류 output 필드명 — LLM이 ${ref.field} 데이터흐름을 실제 출력에 맞춰 쓰게 한다
                # (미제공 시 output_text/payload.text 등 유령 필드 추측 → degrade·retry, v2 측정).
                "outputs": _outputs_of(cfg_by_type[ref_node_types[ref]]),
            }
            for ref in ref_to_iid
        ]
        spec_json = json.dumps(
            {"intent": spec.natural_language_intent, "entities": spec.discovered_entities},
            ensure_ascii=False,
        )
        prompt = (
            _PARAM_FILL_SYSTEM_PROMPT
            + self._retry_feedback_block(retry_feedback)
            + f"\nUser request: {spec_json}"
            + f"\nNodes (structure fixed): {json.dumps(node_specs, ensure_ascii=False)}"
        )
        resp = await self._llm.generate_structured(prompt, _ParamFillResponse)
        params_by_ref = {item.ref: item.parameters for item in resp.nodes}

        outputs_by_instance = {
            ref_to_iid[ref]: _outputs_of(cfg_by_type[ref_node_types[ref]])
            for ref in ref_to_iid
            if ref_node_types[ref] in cfg_by_type
        }
        iid_to_ref = {iid: ref for ref, iid in ref_to_iid.items()}
        filled = [
            n.model_copy(
                update={
                    "parameters": _ground_ref_fields(
                        _rewrite_refs(params_by_ref.get(iid_to_ref[n.instance_id], {}), ref_to_iid),
                        outputs_by_instance,
                    )
                }
            )
            for n in wf.nodes
        ]
        name = (resp.name or "").strip() or (spec.natural_language_intent or "")[:60] or wf.name
        return wf.model_copy(update={"nodes": filled, "name": name})

    @staticmethod
    def _personal_patterns_block(personal_patterns: list[str] | None) -> str:
        """RAG로 회수한 사용자 패턴을 시스템 프롬프트 주입용 블록으로 직렬화.

        패턴이 없으면 빈 문자열을 반환해 프롬프트를 그대로 둔다(개인화 미적용 시 무영향).
        '관련 있을 때만 적용 / 패턴 충족을 위해 노드를 추가하지 말 것'을 명시해, 무관한
        과거 패턴이 이번 워크플로우를 오염시키는 것을 막는다(노이즈 가드).
        """
        if not personal_patterns:
            return ""
        joined = "\n".join(f"- {p}" for p in personal_patterns)
        return (
            "\nUSER PATTERNS (this user's established preferences recalled from their past "
            "workflows — apply ONLY the ones relevant to THIS request, e.g. a preferred "
            "notification channel, summary language, or output format. Ignore patterns that "
            "do not fit, and NEVER add a node solely to satisfy a pattern):\n"
            f"{joined}\n"
        )

    @staticmethod
    def _retry_feedback_block(retry_feedback: str | None) -> str:
        """validate/QA 실패 후 재시도 교정 피드백을 시스템 프롬프트 주입용 블록으로.

        피드백이 없으면 빈 문자열. **`natural_language_intent`와 분리**해 두므로 이 텍스트가
        워크플로우 이름/설명으로 새지 않는다(#378 부차 — UI 누출 차단). 직전 시도가 왜
        미달했는지를 알려 다음 초안을 고치게 하되, 워크플로우 산출물에는 노출되지 않는다.
        """
        if not retry_feedback:
            return ""
        return (
            "\nRETRY FEEDBACK (the previous draft failed validation/QA — fix these issues in "
            "this attempt; this is internal guidance, do NOT echo it into the workflow name or "
            f"description):\n{retry_feedback}\n"
        )

    @staticmethod
    def _motif_block(pattern_templates: list[Any] | None) -> str:
        """GraphRAG :Pattern 모티프를 drafter 프롬프트 주입용 블록으로 직렬화 (ADR-0026 Phase 2).

        ETL 시드 전(빈 리스트) 또는 role_slots가 없으면 빈 문자열 반환(무영향).
        슬롯 구조(패턴명 무관)로 모티프 형태를 판정해 형태별 배선 지침을 주입한다:
          - generator+evaluator → LOOP(back-edge 재시도).
          - classifier+router   → BRANCH(XOR 배타분기, 무순환).
          - 그 외               → 슬롯 평문 나열(폴백).
        패턴명 하드코딩 없음 — 같은 슬롯 구조의 패턴이 추가돼도 자동 처리.
        """
        if not pattern_templates:
            return ""
        lines: list[str] = []
        for pt in pattern_templates:
            slots: dict[str, Any] = getattr(pt, "role_slots", {}) or {}
            if not slots:
                continue
            generator_types = slots.get("generator", ())
            evaluator_types = slots.get("evaluator", ())
            classifier_types = slots.get("classifier", ())
            router_types = slots.get("router", ())
            if generator_types and evaluator_types:
                gen = generator_types[0] if len(generator_types) == 1 else f"({'/'.join(generator_types)})"
                ev = evaluator_types[0] if len(evaluator_types) == 1 else f"({'/'.join(evaluator_types)})"
                lines.append(
                    f"- {pt.name} (LOOP pattern — follow the LOOPS rules above):\n"
                    f"  generator slot: use ONE {gen} node (do NOT add a second {gen} for evaluation)\n"
                    f"  evaluator slot: use a {ev} node as the branching point\n"
                    f"  wiring: {gen} -[output]-> {ev}, then {ev} -[false]-> {gen} (BACK-EDGE retry),\n"
                    f"          then {ev} -[true]-> next_node (exit/pass branch)"
                )
            elif classifier_types and router_types:
                cls = classifier_types[0] if len(classifier_types) == 1 else f"({'/'.join(classifier_types)})"
                rt = router_types[0] if len(router_types) == 1 else f"({'/'.join(router_types)})"
                lines.append(
                    f"- {pt.name} (BRANCH pattern — exclusive choice / routing, NOT a loop):\n"
                    f"  classifier slot: use ONE {cls} node to classify/decide "
                    f"(or feed an existing value into the router)\n"
                    f"  router slot: use a {rt} node as the XOR branch point\n"
                    f"  wiring: classifier -[output]-> {rt}, then {rt} -[true]-> path_A "
                    f"and {rt} -[false]-> path_B\n"
                    f"          (each branch is a SEPARATE downstream path; do NOT add a back-edge)"
                )
            else:
                slot_desc = ", ".join(
                    f'{slot}={"|".join(types)}' for slot, types in slots.items() if types
                )
                lines.append(f"- {pt.name}: {slot_desc}")
        if not lines:
            return ""
        joined = "\n".join(lines)
        return (
            "\nWORKFLOW MOTIFS (structural patterns from the knowledge graph matching this "
            "intent — apply only if the request actually calls for it):\n"
            f"{joined}\n"
        )

    @staticmethod
    def _skill_binding_block(skill_selected: bool, composer_instructions: str | None) -> str:
        """선택된 스킬 바인딩을 위해 LLM 노드 포함을 drafter에 지시하는 프롬프트 블록 (#372 결함 A).

        스킬(모델 A)은 LLM 노드 system 프롬프트에 주입되는 도메인 지침서이므로, 스킬이 선택되면
        주입 대상 LLM 노드(category=="ai")가 워크플로우에 반드시 있어야 바인딩이 성립한다(없으면
        `_bind_skill_node`가 대상을 못 찾아 skip). composer_instructions(COMPOSER.md 본문, 선택)가
        주어지면 노드 구성 구체 지침으로 함께 주입한다(미주어지면 LLM 노드 포함 기준선만 지시).
        """
        if not skill_selected:
            return ""
        block = (
            "\nSKILL BINDING (a reusable skill will be bound to this workflow): you MUST include "
            'exactly one LLM node (a node whose category is "ai" in the available nodes) as the '
            "core reasoning/generation step and wire it into the flow. The skill's domain "
            "instructions are injected into that LLM node's system prompt at runtime — without an "
            "LLM node the skill cannot bind.\n"
        )
        if composer_instructions:
            block += (
                "Composition requirements from the selected skill (follow these when choosing and "
                f"wiring nodes):\n{composer_instructions}\n"
            )
        return block

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

    def _build(
        self,
        draft: _DraftResponse,
        candidates: list[NodeConfig],
        owner_user_id: UUID,
        dropped_sink: list[str] | None = None,
    ) -> WorkflowSchema:
        try:
            node_map = {n.node_type: n for n in candidates}
            nodes: list[NodeInstance] = []
            instance_id_map: dict[str, UUID] = {}  # node_type → instance_id (1:1 보장)
            for raw in draft.nodes:
                nc = node_map.get(raw.node_type)
                if nc is None:
                    # 후보에 없는 node_type은 하드페일(E_UNKNOWN_NODE_TYPE) 대신 drop+경고로 degrade
                    # (#378 후속 B). 즉시 죽으면 재시도 루프(retriever 재검색)가 돌 기회가 없다.
                    # 떨군 노드를 참조하는 엣지는 아래 instance_id_map 미존재로 자연히 스킵되고,
                    # 누락된 능력은 QA 의도-노드 게이트(missing_capabilities)가 잡아 재시도를 유발한다.
                    # 버린 node_type은 sink에 기록 → 재시도 retriever가 결정적으로 재검색(리뷰 #2).
                    _logger.warning("후보 목록에 없는 node_type drop (degrade): %s", raw.node_type)
                    if dropped_sink is not None:
                        dropped_sink.append(raw.node_type)
                    continue
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
