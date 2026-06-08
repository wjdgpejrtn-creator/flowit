"""순수 지표 추출기 결정적 단위 테스트 (네트워크/DB 불필요).

라이브 스택 없이 합성 RunRecord로 metrics.py를 검증한다. 이 테스트가 그린이면
지표 계산 로직 자체는 회귀가 없다 — 라이브 캡처는 입력(스냅샷)만 공급한다.
"""
from __future__ import annotations

import pytest

from ai_agent.tests.eval.ontology_grounding.metrics import (
    QA_PASS_THRESHOLD,
    aggregate,
    detects_quality_gate_loop,
    hallucinated_node_types,
    has_condition_node,
    has_cycle,
    motif_verdict,
)
from ai_agent.tests.eval.ontology_grounding.records import UNKNOWN_NODE_TYPE, RunRecord
from ai_agent.tests.eval.ontology_grounding.scenarios import QUALITY_GATE_LOOP, SCENARIOS


def _rec(**kw) -> RunRecord:
    base = dict(
        scenario_id="t",
        utterance="u",
        expected_motif=None,
        distractor=False,
        produced_workflow=True,
        node_types=["anthropic_chat"],
        edges=[],
        validator_passed_first=True,
        retry_count=0,
        qa_score=9.0,
        error=None,
    )
    base.update(kw)
    return RunRecord(**base)


# ── 환각 ─────────────────────────────────────────────────────────────────────


def test_hallucination_detects_unknown_and_offcatalog():
    rec = _rec(node_types=["anthropic_chat", UNKNOWN_NODE_TYPE, "send_telegram_message"])
    halluc = hallucinated_node_types(rec)
    assert UNKNOWN_NODE_TYPE in halluc
    assert "send_telegram_message" in halluc  # 카탈로그에 없음
    assert "anthropic_chat" not in halluc


def test_no_hallucination_for_clean_catalog_nodes():
    rec = _rec(node_types=["schedule_trigger", "http_request", "anthropic_chat", "email_send"])
    assert hallucinated_node_types(rec) == []


# ── 순환/condition/모티프 ─────────────────────────────────────────────────────


def test_has_cycle_true_on_back_edge():
    # 0→1→2→1 (back-edge 2→1)
    rec = _rec(node_types=["a", "if_condition", "c"], edges=[(0, 1), (1, 2), (2, 1)])
    assert has_cycle(rec) is True


def test_has_cycle_false_on_dag():
    rec = _rec(node_types=["a", "b", "c"], edges=[(0, 1), (1, 2), (0, 2)])
    assert has_cycle(rec) is False


def test_self_loop_is_cycle():
    rec = _rec(node_types=["loop_count"], edges=[(0, 0)])
    assert has_cycle(rec) is True


def test_out_of_range_edges_ignored():
    rec = _rec(node_types=["a", "b"], edges=[(0, 5), (9, 1)])
    assert has_cycle(rec) is False


def test_has_condition_node():
    assert has_condition_node(_rec(node_types=["anthropic_chat", "if_condition"])) is True
    assert has_condition_node(_rec(node_types=["anthropic_chat", "email_send"])) is False


def test_quality_gate_loop_needs_both_cycle_and_condition():
    # 순환 O + condition O → 모티프 성립
    good = _rec(node_types=["anthropic_chat", "if_condition"], edges=[(0, 1), (1, 0)])
    assert detects_quality_gate_loop(good) is True
    # 순환 O + condition X → 불성립(엔진이 거부할 탈출불가 루프)
    no_cond = _rec(node_types=["anthropic_chat", "gemma_chat"], edges=[(0, 1), (1, 0)])
    assert detects_quality_gate_loop(no_cond) is False
    # condition O + 순환 X → 단순 분기, 루프 아님
    no_cycle = _rec(node_types=["anthropic_chat", "if_condition"], edges=[(0, 1)])
    assert detects_quality_gate_loop(no_cycle) is False


def test_motif_verdict_none_when_not_expected():
    assert motif_verdict(_rec(expected_motif=None)) is None


def test_motif_verdict_scores_loop_expectation():
    good = _rec(
        expected_motif=QUALITY_GATE_LOOP,
        node_types=["anthropic_chat", "if_condition"],
        edges=[(0, 1), (1, 0)],
    )
    bad = _rec(expected_motif=QUALITY_GATE_LOOP, node_types=["anthropic_chat"], edges=[])
    assert motif_verdict(good) is True
    assert motif_verdict(bad) is False


# ── 집계 ─────────────────────────────────────────────────────────────────────


def test_aggregate_basic_rates():
    records = [
        # 워크플로우 2건: 하나는 깨끗+통과, 하나는 환각+retry
        _rec(scenario_id="w1", node_types=["anthropic_chat", "email_send"],
             validator_passed_first=True, retry_count=0, qa_score=9.0),
        _rec(scenario_id="w2", node_types=["anthropic_chat", "bogus_node"],
             validator_passed_first=False, retry_count=2, qa_score=7.0),
        # 루프 1건(정답)
        _rec(scenario_id="m1", expected_motif=QUALITY_GATE_LOOP,
             node_types=["anthropic_chat", "if_condition"], edges=[(0, 1), (1, 0)],
             validator_passed_first=True, retry_count=0, qa_score=8.0),
        # 잡담 1건(정답 — 워크플로우 미생성)
        _rec(scenario_id="d1", distractor=True, produced_workflow=False,
             node_types=[], qa_score=0.0),
    ]
    agg = aggregate(records)
    assert agg.n_total == 4
    assert agg.n_workflow == 3       # distractor 제외
    assert agg.n_distractor == 1
    assert agg.n_motif == 1
    # validator-pass: 3건 중 2건 통과
    assert agg.validator_pass_rate == pytest.approx(2 / 3)
    # avg retry: (0+2+0)/3
    assert agg.avg_retry == pytest.approx(2 / 3)
    # 환각 노드: 전체 노드 (2+2+2=6) 중 1개(bogus_node)
    assert agg.hallucinated_node_rate == pytest.approx(1 / 6)
    assert agg.n_hallucinated_records == 1
    # motif: 1/1
    assert agg.motif_correctness == pytest.approx(1.0)
    # qa pass(≥8): 9.0, 8.0 통과 / 7.0 미달 → 2/3
    assert agg.qa_pass_rate == pytest.approx(2 / 3)
    assert agg.distractor_correct_rate == pytest.approx(1.0)


def test_aggregate_empty_is_safe():
    agg = aggregate([])
    assert agg.n_total == 0
    assert agg.validator_pass_rate == 0.0
    assert agg.hallucinated_node_rate == 0.0


def test_distractor_producing_workflow_is_wrong():
    # 잡담인데 워크플로우를 만들면 오답
    rec = _rec(distractor=True, produced_workflow=True, node_types=["anthropic_chat"])
    agg = aggregate([rec])
    assert agg.distractor_correct_rate == 0.0


# ── 골든셋 sanity ─────────────────────────────────────────────────────────────


def test_golden_set_shape():
    ids = [s.scenario_id for s in SCENARIOS]
    assert len(ids) == len(set(ids)), "scenario_id 중복"
    assert sum(1 for s in SCENARIOS if s.expected_motif == QUALITY_GATE_LOOP) >= 5
    assert sum(1 for s in SCENARIOS if s.distractor) >= 3
    assert len(SCENARIOS) >= 30  # §6.5 권장 규모


def test_qa_threshold_constant():
    assert QA_PASS_THRESHOLD == 8.0  # ADR-0004 통과 기준


# ── 카탈로그 드리프트 가드 (PR #409 리뷰 LOW #2/#4) ───────────────────────────


def _catalog_condition_node_types() -> frozenset[str]:
    """실측 카탈로그에서 category=="condition"인 node_type을 수집.

    control/*.py만 importlib로 읽는다(외부 어댑터 heavy import 회피). condition
    카테고리 노드는 control 패키지에만 존재 — drift 시 여기서 자연히 갱신된다.
    """
    import glob
    import importlib
    import os

    import nodes_graph.domain.catalog.control as control_pkg

    control_dir = os.path.dirname(control_pkg.__file__)
    found: set[str] = set()
    for path in glob.glob(os.path.join(control_dir, "*.py")):
        name = os.path.splitext(os.path.basename(path))[0]
        if name == "__init__":
            continue
        mod = importlib.import_module(f"nodes_graph.domain.catalog.control.{name}")
        getter = getattr(mod, "get_node_definition", None)
        if getter is None:
            continue
        defn = getter()
        if getattr(defn, "category", None) == "condition":
            found.add(defn.node_type)
    return frozenset(found)


def test_condition_node_types_match_catalog():
    # CONDITION_NODE_TYPES가 실측 카탈로그(category=="condition")와 **동치**여야 한다.
    # subset이 아니라 == 라서 9번째 condition 노드 추가도, 기존 노드 제거도 잡는다.
    from ai_agent.tests.eval.ontology_grounding.metrics import CONDITION_NODE_TYPES

    assert CONDITION_NODE_TYPES == _catalog_condition_node_types()


def test_condition_subset_of_executable_catalog():
    from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES

    from ai_agent.tests.eval.ontology_grounding.metrics import CONDITION_NODE_TYPES

    assert CONDITION_NODE_TYPES <= EXECUTABLE_NODE_TYPES
