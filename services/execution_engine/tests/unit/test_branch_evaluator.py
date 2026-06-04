"""BranchEvaluator 단위 테스트 — 조건 노드 출력 → 엣지 live 판정 (ADR-0023 L2)."""
from __future__ import annotations

from src.domain.services.branch_evaluator import BranchEvaluator


def _e():
    return BranchEvaluator()


def test_non_brancher_always_live():
    out = {"summary": "x"}
    assert _e().is_edge_live(False, out, ["output"], "output") is True
    # 비조건 노드는 출력 문자열이 핸들과 같아도 분기 안 함
    assert _e().is_edge_live(False, {"k": "output"}, ["output", "x"], "x") is True


def test_if_condition_true_branch_live_false_dead():
    out = {"branch": "true", "value": 1, "condition_result": True}
    handles = ["true", "false"]
    assert _e().is_edge_live(True, out, handles, "true") is True
    assert _e().is_edge_live(True, out, handles, "false") is False


def test_switch_case_matched_live():
    out = {"matched_case": "caseA", "value": "payload"}
    handles = ["caseA", "caseB"]
    assert _e().is_edge_live(True, out, handles, "caseA") is True
    assert _e().is_edge_live(True, out, handles, "caseB") is False


def test_value_passthrough_excluded_from_selector():
    # value="false"가 selector로 새지 않아야 — branch만 selector
    out = {"branch": "true", "value": "false"}
    handles = ["true", "false"]
    assert _e().is_edge_live(True, out, handles, "false") is False
    assert _e().is_edge_live(True, out, handles, "true") is True


def test_degrade_all_live_when_no_handle_matches():
    # 레거시: 조건 노드인데 엣지 from_handle이 전부 "output" → selector 일치 0 → 전부 live
    out = {"branch": "true", "value": 1}
    handles = ["output"]
    assert _e().is_edge_live(True, out, handles, "output") is True


def test_live_handles_returns_none_when_inactive():
    assert _e().live_handles({"branch": "true"}, ["output"]) is None
    assert _e().live_handles({"branch": "true"}, ["true", "false"]) == {"true"}
    assert _e().live_handles("not-a-dict", ["x"]) is None
