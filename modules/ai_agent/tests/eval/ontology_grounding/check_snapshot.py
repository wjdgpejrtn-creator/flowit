"""온톨로지 그라운딩 스냅샷 결정적 점검기 (네트워크/DB 불필요).

`/ontology-eval` 커맨드의 본체. run_eval가 떠둔 snapshots/composer_grounding.json만
읽어, (1) 골든셋이 전부 캡처됐는지 (2) 집계 지표가 베이스라인 대비 회귀하지 않았는지를
결정론적으로 assert한다. Modal·Neo4j·DB 어느 것에도 붙지 않는다.

베이스라인(snapshots/baseline.json)이 있으면 회귀 게이트로 동작하고, 없으면 현재
집계만 보고한 뒤(게이트 통과) "베이스라인을 승격하라"고 안내한다 — A1(CAN_FOLLOW)
적용 전 베이스라인을 1회 떠두고, 적용 후 재캡처해 before/after를 본다.

실행:
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    PYTHONPATH="modules:packages/common_schemas/python" \
    python -m ai_agent.tests.eval.ontology_grounding.check_snapshot

종료코드 0 = 통과(또는 베이스라인 없음), 1 = 회귀/스냅샷 결손.
"""
from __future__ import annotations

import json
import sys

from .metrics import AggregateMetrics, aggregate
from .records import BASELINE_FILE, SNAPSHOT_FILE, load_snapshot
from .scenarios import SCENARIOS

# 베이스라인 대비 허용 회귀 폭(이보다 더 나빠지면 FAIL). higher-is-better 지표.
_TOL_RATE = 0.05      # 비율 지표(pass/motif/qa_pass/distractor)는 5%p까지 하락 허용
_TOL_HALLUC = 0.03    # hallucination(낮을수록 좋음)은 3%p까지 상승 허용
_TOL_RETRY = 0.5      # 평균 retry(낮을수록 좋음)는 0.5회까지 상승 허용

# 품질 목표 floor — **게이트가 아니라 경고**(미달해도 FAIL 아님). 회귀 게이트 baseline은
# 실측(de-noise 0.5)이라 "0.5 정체를 무회귀로 조용히 통과"시킨다(PR #415 리뷰 LOW). 목표(0.6)
# 미달을 ⚠로 가시화해 "회귀는 아니지만 목표엔 못 미친다"를 드러낸다. 0.6 도달 시 baseline 승격.
_QA_PASS_TARGET = 0.60


class _Check:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.lines: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        self.lines.append(f"  [PASS] {label}{f' — {detail}' if detail else ''}")

    def fail(self, label: str, detail: str) -> None:
        self.lines.append(f"  [FAIL] {label} — {detail}")
        self.failures.append(f"{label}: {detail}")

    def warn(self, label: str, detail: str) -> None:
        """경고 — 가시화하되 종료코드엔 영향 없음(failures 미추가)."""
        self.lines.append(f"  [WARN] {label} — {detail}")


def _check_target(cur: AggregateMetrics, c: _Check) -> None:
    """품질 목표 floor 점검 — 미달 시 ⚠ 경고(FAIL 아님). 회귀 게이트와 독립."""
    if cur.qa_pass_rate < _QA_PASS_TARGET:
        c.warn(
            "목표:qa-pass",
            f"{cur.qa_pass_rate:.3f} < 목표 {_QA_PASS_TARGET:.2f} "
            f"(회귀는 아니나 품질 목표 미달 — retrieval/그라운딩 개선 필요)",
        )
    else:
        c.ok("목표:qa-pass", f"{cur.qa_pass_rate:.3f} ≥ {_QA_PASS_TARGET:.2f}")


def _check_complete(records, c: _Check) -> None:
    captured = {r.scenario_id for r in records}
    expected = {s.scenario_id for s in SCENARIOS}
    missing = expected - captured
    extra = captured - expected
    if missing:
        c.fail("골든셋 캡처 완전성", f"미캡처 {len(missing)}건: {sorted(missing)[:5]}")
    elif extra:
        c.fail("골든셋 캡처 완전성", f"미상 시나리오 {sorted(extra)[:5]}")
    else:
        c.ok("골든셋 캡처 완전성", f"{len(expected)}/{len(expected)}건")


def _regress(label: str, cur: float, base: float, tol: float, higher_better: bool, c: _Check) -> None:
    if higher_better:
        regressed = cur < base - tol
        arrow = f"{base:.3f} → {cur:.3f}"
    else:
        regressed = cur > base + tol
        arrow = f"{base:.3f} → {cur:.3f}"
    if regressed:
        c.fail(f"회귀:{label}", f"{arrow} (허용폭 {tol})")
    else:
        c.ok(f"회귀:{label}", arrow)


def _check_regression(cur: AggregateMetrics, c: _Check) -> None:
    if not BASELINE_FILE.exists():
        c.ok("베이스라인 회귀", "베이스라인 없음 — 게이트 생략(현재 집계를 베이스라인으로 승격하세요)")
        return
    base = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    _regress("validator-pass", cur.validator_pass_rate, base["validator_pass_rate"], _TOL_RATE, True, c)
    _regress("motif-correctness", cur.motif_correctness, base["motif_correctness"], _TOL_RATE, True, c)
    _regress("qa-pass", cur.qa_pass_rate, base["qa_pass_rate"], _TOL_RATE, True, c)
    _regress("distractor-정답", cur.distractor_correct_rate, base["distractor_correct_rate"], _TOL_RATE, True, c)
    _regress("hallucination", cur.hallucinated_node_rate, base["hallucinated_node_rate"], _TOL_HALLUC, False, c)
    _regress("retry", cur.avg_retry, base["avg_retry"], _TOL_RETRY, False, c)


def main() -> int:
    print(f"=== 온톨로지 그라운딩 스냅샷 점검 ===\n스냅샷: {SNAPSHOT_FILE}")
    snap = load_snapshot()
    if snap is None:
        print("\n[FAIL] 스냅샷 없음 — run_eval.py를 먼저 실행하세요 (Modal+Neo4j+DB 필요).")
        return 1

    print(f"라벨: {snap.label} / 캡처: {snap.captured_at} / 레코드 {len(snap.records)}건\n")
    c = _Check()
    _check_complete(snap.records, c)

    agg = aggregate(snap.records)
    print("[집계 지표]")
    print(agg.as_table())
    print()

    _check_regression(agg, c)
    _check_target(agg, c)

    print("\n".join(c.lines))
    if c.failures:
        print(f"\n=== 실패 {len(c.failures)}건 ===")
        for f in c.failures:
            print(f"  - {f}")
        return 1
    print("\n=== 통과 ✓ ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
