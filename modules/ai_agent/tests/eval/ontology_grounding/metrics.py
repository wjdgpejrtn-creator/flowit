"""순수·결정적 지표 추출기 (ADR-0026 §6.5).

네트워크/DB/Modal 어디에도 붙지 않는다. RunRecord(정규화된 캡처 결과)만 입력으로
받아 5대 지표를 계산한다. test_metrics.py가 합성 RunRecord로 이 함수들을 검증한다.

§6.5 지표:
  - validator-pass rate   : 1차 초안이 retry 없이 검증 통과한 비율
  - validator retry 횟수   : draft/validate/qa 재시도 평균
  - hallucinated-node rate : 카탈로그(EXECUTABLE_NODE_TYPES)에 없는 node_type 비율
  - motif-correctness      : "루프 요청 → 실행가능 quality_gate_loop 생성" 성공률
  - e2e quality score      : qa_evaluator 점수 분포(평균 + ≥8 통과율)
"""
from __future__ import annotations

from dataclasses import dataclass

from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES

from .records import UNKNOWN_NODE_TYPE, RunRecord
from .scenarios import BRANCH_ON_CLASSIFICATION, QUALITY_GATE_LOOP

QA_PASS_THRESHOLD = 8.0

# XOR 분기점이 될 수 있는 condition node_type(다중 outgoing 핸들로 라우팅).
# BranchEvaluator(execution_engine)가 selector 문자열로 live 핸들을 고르는 노드들.
# (loop_count/loop_list 등 반복 condition은 분기가 아니라 제외.)
ROUTER_NODE_TYPES: frozenset[str] = frozenset({"if_condition", "switch_case"})

# category=="condition"인 카탈로그 node_type 8종. validator(_CONDITION_CATEGORY)와
# CyclicScheduler(is_brancher = category=="condition")의 루프 탈출 판정 기준을 미러한다.
# nodes_graph/domain/catalog/control/*.py(category="condition") 기준.
#
# 드리프트(카탈로그에 condition 노드 추가/제거)는 import-time assert가 아니라
# test_metrics.test_condition_node_types_match_catalog가 **실측 카탈로그와 동치(==)**로
# 잡는다. import 시 죽이지 않아(harness uncollectable 회피) fail-loud는 테스트 레이어로.
# (PR #409 리뷰 LOW #2/#4.)
CONDITION_NODE_TYPES: frozenset[str] = frozenset(
    {
        "if_condition",
        "switch_case",
        "loop_count",
        "loop_list",
        "retry",
        "merge_branch",
        "stop_workflow",
        "delay",
    }
)


# ── per-record 판정 ──────────────────────────────────────────────────────────


def hallucinated_node_types(rec: RunRecord) -> list[str]:
    """카탈로그에 없는 node_type(미해소 UNKNOWN 포함). 환각 신호."""
    return [
        nt for nt in rec.node_types
        if nt == UNKNOWN_NODE_TYPE or nt not in EXECUTABLE_NODE_TYPES
    ]


def has_condition_node(rec: RunRecord) -> bool:
    return any(nt in CONDITION_NODE_TYPES for nt in rec.node_types)


def has_cycle(rec: RunRecord) -> bool:
    """산출 그래프에 유향 순환(back-edge)이 있는가 — 반복 DFS, 재귀 한계 회피."""
    n = len(rec.node_types)
    if n == 0:
        return False
    adj: list[list[int]] = [[] for _ in range(n)]
    for a, b in rec.edges:
        if 0 <= a < n and 0 <= b < n:
            adj[a].append(b)

    white, gray, black = 0, 1, 2
    color = [white] * n
    for start in range(n):
        if color[start] != white:
            continue
        stack = [(start, iter(adj[start]))]
        color[start] = gray
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color[nxt] == gray:
                    return True  # back-edge → 순환
                if color[nxt] == white:
                    color[nxt] = gray
                    stack.append((nxt, iter(adj[nxt])))
                    advanced = True
                    break
            if not advanced:
                color[node] = black
                stack.pop()
    return False


def detects_quality_gate_loop(rec: RunRecord) -> bool:
    """실행가능 quality_gate_loop 모티프 판정.

    validator §2 SCC 수용기준 정합: **유향 순환(루프 바디) + condition 노드 ≥1개**.
    둘 다여야 엔진 CyclicScheduler가 탈출 가능한 유한 순환으로 받아들인다.
    """
    return has_cycle(rec) and has_condition_node(rec)


def has_branch_point(rec: RunRecord) -> bool:
    """router condition 노드(if_condition/switch_case)가 outgoing 엣지 ≥2개를 가지는가.

    = XOR 분기점. BranchEvaluator가 selector로 한 핸들을 고르려면 분기가 ≥2 갈래여야 한다.
    """
    n = len(rec.node_types)
    out_degree = [0] * n
    for a, _b in rec.edges:
        if 0 <= a < n:
            out_degree[a] += 1
    return any(
        nt in ROUTER_NODE_TYPES and out_degree[i] >= 2
        for i, nt in enumerate(rec.node_types)
    )


def detects_branch_on_classification(rec: RunRecord) -> bool:
    """실행가능 XOR 분기 모티프 판정.

    router condition 노드의 다중 분기(outgoing ≥2) + **무순환**(루프 아닌 순수 분기).
    BranchEvaluator(L2) 수용 계약 정합 — 조건 노드가 outgoing 핸들 중 live를 선택.
    """
    return has_branch_point(rec) and not has_cycle(rec)


def motif_verdict(rec: RunRecord) -> bool | None:
    """motif-correctness 판정.

    - expected_motif 없음 → None(채점 제외).
    - quality_gate_loop 기대 → 실행가능 루프를 만들었는가.
    - branch_on_classification 기대 → 실행가능 XOR 분기를 만들었는가.
    """
    if rec.expected_motif == QUALITY_GATE_LOOP:
        return detects_quality_gate_loop(rec)
    if rec.expected_motif == BRANCH_ON_CLASSIFICATION:
        return detects_branch_on_classification(rec)
    return None


def distractor_verdict(rec: RunRecord) -> bool | None:
    """잡담은 워크플로우를 만들지 **않아야** 정답. distractor 아니면 None."""
    if not rec.distractor:
        return None
    return not rec.produced_workflow


# ── 집계 ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AggregateMetrics:
    n_total: int
    n_workflow: int               # 워크플로우를 만들어야 하는 시나리오 수(non-distractor)
    validator_pass_rate: float    # 1차 초안 무재초안율(validator+QA), n_workflow 대비
    avg_retry: float              # 평균 재초안 횟수(validator+QA), n_workflow 대비
    hallucinated_node_rate: float # 전체 노드 중 환각 노드 비율
    n_hallucinated_records: int   # 환각 노드를 1개 이상 가진 산출물 수
    motif_correctness: float      # expected_motif 있는 시나리오 대비
    n_motif: int
    qa_score_mean: float          # 산출물 평균 qa 점수
    qa_pass_rate: float           # qa_score ≥ 8 비율(n_workflow 대비)
    distractor_correct_rate: float  # 잡담을 올바로 무시한 비율
    n_distractor: int

    def as_table(self) -> str:
        rows = [
            ("시나리오 수", f"{self.n_total} (워크플로우 {self.n_workflow} / 잡담 {self.n_distractor})"),
            ("1차초안 무재초안율(val+QA)", f"{self.validator_pass_rate:.1%}"),
            ("평균 재초안 횟수(val+QA)", f"{self.avg_retry:.2f}"),
            ("hallucinated-node rate", f"{self.hallucinated_node_rate:.1%} ({self.n_hallucinated_records}개 산출물)"),
            ("motif-correctness", f"{self.motif_correctness:.1%} (n={self.n_motif})"),
            ("qa score 평균", f"{self.qa_score_mean:.2f}"),
            ("qa pass rate(≥8)", f"{self.qa_pass_rate:.1%}"),
            ("distractor 정답률", f"{self.distractor_correct_rate:.1%} (n={self.n_distractor})"),
        ]
        width = max(len(k) for k, _ in rows)
        return "\n".join(f"  {k.ljust(width)} : {v}" for k, v in rows)

    def to_dict(self) -> dict:
        return {
            "n_total": self.n_total,
            "n_workflow": self.n_workflow,
            "validator_pass_rate": self.validator_pass_rate,
            "avg_retry": self.avg_retry,
            "hallucinated_node_rate": self.hallucinated_node_rate,
            "n_hallucinated_records": self.n_hallucinated_records,
            "motif_correctness": self.motif_correctness,
            "n_motif": self.n_motif,
            "qa_score_mean": self.qa_score_mean,
            "qa_pass_rate": self.qa_pass_rate,
            "distractor_correct_rate": self.distractor_correct_rate,
            "n_distractor": self.n_distractor,
        }


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def aggregate(records: list[RunRecord]) -> AggregateMetrics:
    workflow_recs = [r for r in records if not r.distractor]
    distractor_recs = [r for r in records if r.distractor]
    motif_recs = [r for r in records if r.expected_motif is not None]

    total_nodes = sum(len(r.node_types) for r in workflow_recs)
    total_halluc_nodes = sum(len(hallucinated_node_types(r)) for r in workflow_recs)
    n_halluc_records = sum(1 for r in workflow_recs if hallucinated_node_types(r))

    motif_correct = sum(1 for r in motif_recs if motif_verdict(r) is True)
    distractor_correct = sum(1 for r in distractor_recs if distractor_verdict(r) is True)

    qa_scores = [r.qa_score for r in workflow_recs]
    qa_pass = sum(1 for s in qa_scores if s >= QA_PASS_THRESHOLD)

    return AggregateMetrics(
        n_total=len(records),
        n_workflow=len(workflow_recs),
        validator_pass_rate=_safe_div(
            sum(1 for r in workflow_recs if r.validator_passed_first), len(workflow_recs)
        ),
        avg_retry=_safe_div(sum(r.retry_count for r in workflow_recs), len(workflow_recs)),
        hallucinated_node_rate=_safe_div(total_halluc_nodes, total_nodes),
        n_hallucinated_records=n_halluc_records,
        motif_correctness=_safe_div(motif_correct, len(motif_recs)),
        n_motif=len(motif_recs),
        qa_score_mean=_safe_div(sum(qa_scores), len(qa_scores)),
        qa_pass_rate=_safe_div(qa_pass, len(workflow_recs)),
        distractor_correct_rate=_safe_div(distractor_correct, len(distractor_recs)),
        n_distractor=len(distractor_recs),
    )
