from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from common_schemas.enums import ErrorCode
from common_schemas.exceptions import ExecutionError, ValidationError
from common_schemas.workflow import Edge, NodeInstance, WorkflowSchema

from ..entities.execution_level import ExecutionLevel
from ..entities.execution_step import ExecutionStep, LoopBody
from .topological_scheduler import TopologicalScheduler

# 루프 condition 노드에 max_iterations 파라미터가 없을 때의 전역 가드 (ADR-0023 L3).
DEFAULT_MAX_ITERATIONS = 10

# DFS back-edge 분류용 방문 색상.
_WHITE, _GRAY, _BLACK = 0, 1, 2


class CyclicScheduler:
    """유한 순환을 허용하는 실행 플래너 (ADR-0023 L3).

    강연결요소(SCC, Tarjan)로 그래프를 응축한다. trivial SCC(단일 노드)는 1회 실행
    레벨로, non-trivial SCC는 back-edge를 제거한 sub-DAG 레벨 + back/exit 엣지를 묶은
    ``LoopBody``로 방출한다. 비순환 워크플로우는 전부 ``kind="level"`` 스텝이라 기존
    위상정렬 실행과 동일하다(회귀 위험 없음).

    검증: non-trivial SCC는 **탈출 조건(condition) 노드를 ≥1개** 포함해야 한다. 없으면
    무한 루프이므로 ``E_CYCLE_DETECTED``로 거부한다. ``TopologicalScheduler.validate_dag``는
    sub-DAG 검증용으로 그대로 쓰되, 순환 허용 판정은 여기서 한다.
    """

    def __init__(self, scheduler: TopologicalScheduler | None = None) -> None:
        self._scheduler = scheduler or TopologicalScheduler()

    def plan(
        self, workflow: WorkflowSchema, is_brancher: dict[UUID, bool],
    ) -> list[ExecutionStep]:
        if not workflow.validate_graph():
            raise ExecutionError(
                "워크플로우 그래프가 유효하지 않습니다", code="E_INVALID_GRAPH",
            )

        nodes = list(workflow.nodes)
        node_map = {n.instance_id: n for n in nodes}
        edges = list(workflow.connections)

        sccs = self._tarjan_sccs(nodes, edges)
        comp_of = {nid: ci for ci, comp in enumerate(sccs) for nid in comp}
        nontrivial = {
            ci for ci, comp in enumerate(sccs) if self._is_nontrivial(comp, edges)
        }

        # 비순환 워크플로우 — 기존 위상정렬 레벨 그대로.
        if not nontrivial:
            return [
                ExecutionStep(kind="level", level=lvl)
                for lvl in self._scheduler.schedule(workflow)
            ]

        for ci in nontrivial:
            if not any(is_brancher.get(nid, False) for nid in sccs[ci]):
                raise ValidationError(
                    "워크플로우에 탈출 불가능한 순환 참조가 존재합니다",
                    code=ErrorCode.E_CYCLE_DETECTED,
                )

        return self._emit_steps(sccs, comp_of, nontrivial, nodes, node_map, edges, is_brancher)

    # ── 응축 DAG를 topo 순으로 스텝 방출 ────────────────────────────────────
    def _emit_steps(
        self,
        sccs: list[list[UUID]],
        comp_of: dict[UUID, int],
        nontrivial: set[int],
        nodes: list[NodeInstance],
        node_map: dict[UUID, NodeInstance],
        edges: list[Edge],
        is_brancher: dict[UUID, bool],
    ) -> list[ExecutionStep]:
        order_index = {n.instance_id: i for i, n in enumerate(nodes)}
        comp_key = {ci: min(order_index[nid] for nid in comp) for ci, comp in enumerate(sccs)}

        comp_adj: dict[int, set[int]] = defaultdict(set)
        for e in edges:
            cu, cv = comp_of[e.from_instance_id], comp_of[e.to_instance_id]
            if cu != cv:
                comp_adj[cu].add(cv)
        comp_indeg = {ci: 0 for ci in range(len(sccs))}
        for targets in comp_adj.values():
            for cv in targets:
                comp_indeg[cv] += 1

        cur = sorted((ci for ci in range(len(sccs)) if comp_indeg[ci] == 0), key=comp_key.get)
        steps: list[ExecutionStep] = []
        rank = 0
        while cur:
            trivial_nodes: list[NodeInstance] = []
            loop_steps: list[ExecutionStep] = []
            for ci in cur:
                if ci in nontrivial:
                    loop_steps.append(
                        ExecutionStep(
                            kind="loop",
                            loop=self._build_loop(sccs[ci], node_map, edges, is_brancher),
                        )
                    )
                else:
                    trivial_nodes.append(node_map[sccs[ci][0]])

            if trivial_nodes:
                steps.append(
                    ExecutionStep(kind="level", level=ExecutionLevel(level=rank, nodes=trivial_nodes))
                )
            steps.extend(loop_steps)

            nxt: list[int] = []
            for ci in cur:
                for cv in comp_adj[ci]:
                    comp_indeg[cv] -= 1
                    if comp_indeg[cv] == 0:
                        nxt.append(cv)
            cur = sorted(nxt, key=comp_key.get)
            rank += 1

        return steps

    # ── 루프 바디(non-trivial SCC) 구성 ────────────────────────────────────
    def _build_loop(
        self,
        comp: list[UUID],
        node_map: dict[UUID, NodeInstance],
        edges: list[Edge],
        is_brancher: dict[UUID, bool],
    ) -> LoopBody:
        scc = set(comp)
        induced = [e for e in edges if e.from_instance_id in scc and e.to_instance_id in scc]
        exit_edges = [e for e in edges if e.from_instance_id in scc and e.to_instance_id not in scc]

        back_edges = self._classify_back_edges(comp, induced, edges, is_brancher)
        back_set = set(back_edges)
        forward = [e for e in induced if e not in back_set]
        levels = self._kahn_levels(comp, forward, node_map)

        maxes: list[int] = []
        for nid in comp:
            if not is_brancher.get(nid, False):
                continue
            raw = node_map[nid].parameters.get("max_iterations")
            if isinstance(raw, bool):
                continue
            if isinstance(raw, int):
                maxes.append(raw)
            elif isinstance(raw, str) and raw.isdigit():
                maxes.append(int(raw))
        max_iterations = min(maxes) if maxes else DEFAULT_MAX_ITERATIONS

        return LoopBody(
            levels=levels,
            back_edges=back_edges,
            exit_edges=exit_edges,
            max_iterations=max_iterations,
        )

    @staticmethod
    def _classify_back_edges(
        comp: list[UUID], induced: list[Edge], all_edges: list[Edge],
        is_brancher: dict[UUID, bool],
    ) -> list[Edge]:
        """SCC 유도 부분그래프에서 DFS로 back-edge를 분류한다.

        DFS 중 회색(GRAY, 스택 위) 노드로 가는 엣지가 back-edge. 시작 노드 우선순위로
        루프의 자연스러운 진입→꼬리 순서를 유도한다: ①SCC 밖에서 엣지를 받는 진입 노드
        ②비-조건 노드 ③조건 노드. 품질게이트 루프에서 조건 노드는 retry/done을 결정하는
        **꼬리**이므로 마지막에 방문돼야 그 back-edge(condition→진입)가 올바르게 잡힌다
        (외부 진입 엣지가 없는 루프-시작 워크플로우에서도 condition→target을 back으로 선택).
        """
        scc = set(comp)
        adj: dict[UUID, list[Edge]] = defaultdict(list)
        for e in induced:
            adj[e.from_instance_id].append(e)

        external_entry = {
            e.to_instance_id for e in all_edges
            if e.to_instance_id in scc and e.from_instance_id not in scc
        }
        order = {nid: i for i, nid in enumerate(comp)}
        starts = sorted(
            comp,
            key=lambda nid: (nid not in external_entry, is_brancher.get(nid, False), order[nid]),
        )

        color = {nid: _WHITE for nid in comp}
        back: list[Edge] = []

        def dfs(u: UUID) -> None:
            color[u] = _GRAY
            for e in adj[u]:
                v = e.to_instance_id
                if color[v] == _GRAY:
                    back.append(e)
                elif color[v] == _WHITE:
                    dfs(v)
            color[u] = _BLACK

        for start in starts:
            if color[start] == _WHITE:
                dfs(start)
        return back

    @staticmethod
    def _kahn_levels(
        comp: list[UUID], forward: list[Edge], node_map: dict[UUID, NodeInstance],
    ) -> list[ExecutionLevel]:
        indeg = {nid: 0 for nid in comp}
        adj: dict[UUID, list[UUID]] = defaultdict(list)
        for e in forward:
            adj[e.from_instance_id].append(e.to_instance_id)
            indeg[e.to_instance_id] += 1

        cur = [nid for nid in comp if indeg[nid] == 0]
        levels: list[ExecutionLevel] = []
        n = 0
        while cur:
            levels.append(ExecutionLevel(level=n, nodes=[node_map[nid] for nid in cur]))
            nxt: list[UUID] = []
            for nid in cur:
                for v in adj[nid]:
                    indeg[v] -= 1
                    if indeg[v] == 0:
                        nxt.append(v)
            cur = nxt
            n += 1
        return levels

    @staticmethod
    def _is_nontrivial(comp: list[UUID], edges: list[Edge]) -> bool:
        if len(comp) > 1:
            return True
        nid = comp[0]
        return any(e.from_instance_id == nid and e.to_instance_id == nid for e in edges)

    @staticmethod
    def _tarjan_sccs(nodes: list[NodeInstance], edges: list[Edge]) -> list[list[UUID]]:
        ids = [n.instance_id for n in nodes]
        idset = set(ids)
        adj: dict[UUID, list[UUID]] = defaultdict(list)
        for e in edges:
            if e.from_instance_id in idset and e.to_instance_id in idset:
                adj[e.from_instance_id].append(e.to_instance_id)

        counter = [0]
        index: dict[UUID, int] = {}
        lowlink: dict[UUID, int] = {}
        on_stack: dict[UUID, bool] = {}
        stack: list[UUID] = []
        result: list[list[UUID]] = []

        def strongconnect(v: UUID) -> None:
            index[v] = counter[0]
            lowlink[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on_stack[v] = True
            for w in adj[v]:
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif on_stack.get(w):
                    lowlink[v] = min(lowlink[v], index[w])
            if lowlink[v] == index[v]:
                comp: list[UUID] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == v:
                        break
                result.append(comp)

        for v in ids:
            if v not in index:
                strongconnect(v)
        return result
