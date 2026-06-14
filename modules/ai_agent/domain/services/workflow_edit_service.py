from __future__ import annotations

import logging
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from common_schemas import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.exceptions import ExecutionError
from pydantic import BaseModel, Field

from .dataflow_grounding import ground_ref_fields, outputs_of, rewrite_refs

_logger = logging.getLogger(__name__)


# ── 편집 연산 스키마 (refine 전용) ────────────────────────────────────────────
# 기존 워크플로우에 대한 **구조화된 편집 연산**. 전체 재방출(_EditResponse) 대신 이 op들을
# 결정적으로 적용해 안 바뀐 노드의 instance_id를 보존한다(엣지·diff 안정). LLM(WorkflowEditPlanner)이
# 발화를 이 op 리스트로 번역하고, WorkflowEditService가 결정적으로 적용한다. 내부 DTO이므로
# common_schemas에 두지 않는다(크로스 모듈 transport 아님).
class SetParamOp(BaseModel):
    op: Literal["set_param"]
    target_ref: str
    parameters: dict[str, Any]


class ReplaceNodeOp(BaseModel):
    op: Literal["replace_node"]
    target_ref: str
    new_node_type: str
    parameters: dict[str, Any] = {}


class AddNodeOp(BaseModel):
    op: Literal["add_node"]
    new_node_type: str
    parameters: dict[str, Any] = {}
    after_ref: str | None = None
    before_ref: str | None = None


class RemoveNodeOp(BaseModel):
    op: Literal["remove_node"]
    target_ref: str


EditOp = Annotated[
    SetParamOp | ReplaceNodeOp | AddNodeOp | RemoveNodeOp,
    Field(discriminator="op"),
]


class EditPlan(BaseModel):
    name: str | None = None
    ops: list[EditOp] = []


# ── 결정적 applier ────────────────────────────────────────────────────────────
class WorkflowEditService:
    """편집 연산(EditPlan)을 기존 워크플로우에 **결정적으로** 적용한다 (refine 전용).

    LLM·프레임워크 의존 0 (순수 도메인). 핵심 불변식:
    - 영향받지 않은 노드의 ``instance_id``/``node_id``/``parameters``/``position``을 전수 보존.
    - ``replace_node``는 instance_id를 **유지**해 그 노드를 참조하던 엣지가 자동 생존(엣지 수술 불필요).
    - ``workflow_id``를 유지(같은 논리적 워크플로우의 버전 업데이트).
    - replace로 출력 필드가 바뀌면 하류 ``${instance_id.field}`` 데이터흐름 참조를 실제 출력에 재grounding
      (validator는 handle/dataflow 정합성을 검증하지 않으므로 — graph_validator `_check_type_compatibility` 스텁).
    """

    def apply(
        self,
        prior: WorkflowSchema,
        plan: EditPlan,
        candidates: list[NodeConfig],
    ) -> WorkflowSchema:
        # ref는 _serialize_for_edit가 부여한 n0,n1,… (prior.nodes 순서) — planner가 본 것과 동일.
        ref_to_instance: dict[str, UUID] = {
            f"n{i}": n.instance_id for i, n in enumerate(prior.nodes)
        }
        cfg_by_type: dict[str, NodeConfig] = {c.node_type: c for c in candidates}

        # 작업 상태: instance_id 키 dict(삽입순 보존) + 엣지 리스트(frozen → 재구성).
        nodes_by_iid: dict[UUID, NodeInstance] = {n.instance_id: n for n in prior.nodes}
        edges: list[Edge] = list(prior.connections)

        for op in plan.ops:
            if isinstance(op, SetParamOp):
                iid = self._resolve_ref(op.target_ref, ref_to_instance)
                node = nodes_by_iid[iid]
                nodes_by_iid[iid] = node.model_copy(
                    update={"parameters": {**node.parameters, **op.parameters}}
                )
            elif isinstance(op, ReplaceNodeOp):
                iid = self._resolve_ref(op.target_ref, ref_to_instance)
                new_cfg = self._require_node_type(op.new_node_type, cfg_by_type)
                node = nodes_by_iid[iid]
                # instance_id·position 유지 → 이 노드를 가리키던 엣지 자동 생존. creds 초기화(이전
                # provider 자격이 새 노드에 잘못 묻는 것 방지 — autobind가 재해소).
                nodes_by_iid[iid] = node.model_copy(
                    update={
                        "node_id": new_cfg.node_id,
                        "parameters": op.parameters,
                        "credential_id": None,
                        "credential_ids": {},
                        "skill_id": None,
                    }
                )
            elif isinstance(op, AddNodeOp):
                new_cfg = self._require_node_type(op.new_node_type, cfg_by_type)
                new_iid = uuid4()
                nodes_by_iid[new_iid] = NodeInstance(
                    instance_id=new_iid,
                    node_id=new_cfg.node_id,
                    parameters=op.parameters,
                    position=Position(x=0.0, y=0.0),  # layout이 재배치
                )
                edges = self._insert_node_edges(op, new_iid, ref_to_instance, edges)
            elif isinstance(op, RemoveNodeOp):
                iid = self._resolve_ref(op.target_ref, ref_to_instance)
                edges = self._remove_node_edges(iid, edges)
                nodes_by_iid.pop(iid, None)

        nodes = list(nodes_by_iid.values())
        # planner는 값 참조를 ${nX.field}(임시 ref — _serialize_for_edit가 부여한 n0,n1,…)로 낸다.
        # fresh draft 경로의 rewrite_refs와 동일하게 instance_id로 역번역해야 런타임 ReferenceResolver가
        # 푼다 — 이 패스가 edit 경로에 빠져 set_param/replace_node가 넣은 ${n2.content}가 그대로 누출됐다.
        # 안 건드린 노드 params는 이미 ${instance_id.field} 형식이라 n0..nX 키와 안 겹쳐 무손상.
        nodes = [
            n.model_copy(update={"parameters": rewrite_refs(n.parameters, ref_to_instance)})
            for n in nodes
        ]
        nodes = self._reground_dataflow(nodes, candidates)
        # workflow_id를 유지하므로 저장 시 repo가 같은 row를 UPDATE(merge)한다. version 컬럼은
        # NOT NULL(server_default는 INSERT에만 적용) → 편집본에 non-null version을 실어야 UPDATE가
        # 깨지지 않는다(NotNullViolation). 같은 논리적 워크플로우의 버전 업데이트 의미로 +1.
        next_version = (prior.version or 0) + 1
        return prior.model_copy(
            update={
                "name": plan.name or prior.name,
                "is_draft": True,
                "nodes": nodes,
                "connections": edges,
                "version": next_version,
            }
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _resolve_ref(ref: str, ref_to_instance: dict[str, UUID]) -> UUID:
        iid = ref_to_instance.get(ref)
        if iid is None:
            raise ExecutionError(f"편집 대상 ref를 찾을 수 없음: {ref}", code="E_REFINE_BAD_REF")
        return iid

    @staticmethod
    def _require_node_type(node_type: str, cfg_by_type: dict[str, NodeConfig]) -> NodeConfig:
        cfg = cfg_by_type.get(node_type)
        if cfg is None:
            raise ExecutionError(
                f"후보 목록에 없는 node_type: {node_type}", code="E_UNKNOWN_NODE_TYPE"
            )
        return cfg

    def _insert_node_edges(
        self, op: AddNodeOp, new_iid: UUID, ref_to_instance: dict[str, UUID], edges: list[Edge]
    ) -> list[Edge]:
        """after_ref: a→X 들을 new→X로 재배선 + a→new. before_ref: 대칭. 둘 다 없으면 댕글링 거부."""
        if op.after_ref is not None:
            a_iid = self._resolve_ref(op.after_ref, ref_to_instance)
            rewired = [
                e.model_copy(update={"from_instance_id": new_iid}) if e.from_instance_id == a_iid else e
                for e in edges
            ]
            return self._dedup_edges(rewired + [self._oi_edge(a_iid, new_iid)])
        if op.before_ref is not None:
            b_iid = self._resolve_ref(op.before_ref, ref_to_instance)
            rewired = [
                e.model_copy(update={"to_instance_id": new_iid}) if e.to_instance_id == b_iid else e
                for e in edges
            ]
            return self._dedup_edges(rewired + [self._oi_edge(new_iid, b_iid)])
        raise ExecutionError(
            "add_node에 after_ref/before_ref가 없어 위치를 정할 수 없음", code="E_REFINE_DANGLING"
        )

    @staticmethod
    def _oi_edge(frm: UUID, to: UUID) -> Edge:
        return Edge(from_instance_id=frm, to_instance_id=to, from_handle="output", to_handle="input")

    def _remove_node_edges(self, r_iid: UUID, edges: list[Edge]) -> list[Edge]:
        """제거 노드의 들어오는×나가는 엣지를 bridge(상류→하류 직결), 나머지는 보존."""
        incoming = [e for e in edges if e.to_instance_id == r_iid]
        outgoing = [e for e in edges if e.from_instance_id == r_iid]
        rest = [e for e in edges if e.from_instance_id != r_iid and e.to_instance_id != r_iid]
        bridges = [
            Edge(
                from_instance_id=inc.from_instance_id,
                to_instance_id=out.to_instance_id,
                from_handle=inc.from_handle,
                to_handle=out.to_handle,
            )
            for inc in incoming
            for out in outgoing
        ]
        return self._dedup_edges(rest + bridges)

    @staticmethod
    def _dedup_edges(edges: list[Edge]) -> list[Edge]:
        seen: set[tuple[UUID, UUID, str, str]] = set()
        out: list[Edge] = []
        for e in edges:
            key = (e.from_instance_id, e.to_instance_id, e.from_handle, e.to_handle)
            if key not in seen:
                seen.add(key)
                out.append(e)
        return out

    @staticmethod
    def _reground_dataflow(
        nodes: list[NodeInstance], candidates: list[NodeConfig]
    ) -> list[NodeInstance]:
        """편집 후 노드들의 ``${instance_id.field}`` 참조를 현재 상류 출력에 재grounding.

        replace_node로 노드의 출력 필드가 바뀐 경우, 그 노드를 참조하던 하류 노드의 필드를 실제
        출력으로 보정/degrade한다(이미 instance_id 형태이므로 rewrite 불필요, grounding만).
        """
        cfg_by_id = {c.node_id: c for c in candidates}
        outputs_by_instance = {
            n.instance_id: outputs_of(cfg_by_id[n.node_id])
            for n in nodes
            if n.node_id in cfg_by_id
        }
        return [
            n.model_copy(update={"parameters": ground_ref_fields(n.parameters, outputs_by_instance)})
            for n in nodes
        ]
