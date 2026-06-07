"""스냅샷 row 스키마(RunRecord) + 스냅샷 로드/세이브.

RunRecord는 라이브 캡처(run_eval)가 실 composer를 1회 돌린 결과를 **정규화**한 것이다.
산출 WorkflowSchema의 NodeInstance는 node_type 문자열이 아니라 node_id(UUID)만 들고
있으므로(common_schemas.workflow), 캡처 시점에 node_candidates로 node_id→node_type을
해소해 `node_types`(문자열 리스트)로 평탄화한다. 해소 불가 노드는 환각 신호로
``UNKNOWN_NODE_TYPE``("<unknown>")로 기록한다.

이렇게 평탄화해 두면 지표 계산(metrics)·게이트(check_snapshot)는 UUID/DB 없이
순수·결정적으로 동작한다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_FILE = SNAPSHOT_DIR / "composer_grounding.json"
BASELINE_FILE = SNAPSHOT_DIR / "baseline.json"

# node_candidates로 해소 불가한 노드 = 카탈로그에 없는 node_id 참조(환각 후보).
UNKNOWN_NODE_TYPE = "<unknown>"


@dataclass(frozen=True)
class RunRecord:
    """골든 요청 1건의 composer 산출물 정규화 결과."""

    scenario_id: str
    utterance: str
    expected_motif: str | None
    distractor: bool

    # ── 캡처된 산출 ──────────────────────────────────────────────────────────
    produced_workflow: bool          # composer가 워크플로우 초안을 만들었는가
    node_types: list[str]            # 노드별 해소된 node_type(미해소=UNKNOWN_NODE_TYPE)
    edges: list[tuple[int, int]]     # (from_idx, to_idx) — node_types 인덱스 기준
    validator_passed_first: bool     # 1차 초안이 재초안(validator+QA) 없이 살아남음(retry_count==0)
    retry_count: int                 # 재초안 횟수 = WorkflowDraftFrame 개수-1 (validator+QA 모두)
    qa_score: float                  # 최종 qa_evaluator 점수(≥8 통과)
    error: str | None = None         # 캡처 중 예외/에러 프레임(없으면 None)
    meta: dict = field(default_factory=dict)  # 자유 진단 필드(elapsed_ms, motif 매칭명 등)

    def to_dict(self) -> dict:
        d = asdict(self)
        # JSON은 tuple을 list로 직렬화 — 왕복 시 tuple로 복원하기 위해 그대로 둠.
        d["edges"] = [list(e) for e in self.edges]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> RunRecord:
        return cls(
            scenario_id=d["scenario_id"],
            utterance=d["utterance"],
            expected_motif=d.get("expected_motif"),
            distractor=bool(d.get("distractor", False)),
            produced_workflow=bool(d["produced_workflow"]),
            node_types=list(d.get("node_types", [])),
            edges=[(int(a), int(b)) for a, b in d.get("edges", [])],
            validator_passed_first=bool(d.get("validator_passed_first", False)),
            retry_count=int(d.get("retry_count", 0)),
            qa_score=float(d.get("qa_score", 0.0)),
            error=d.get("error"),
            meta=dict(d.get("meta", {})),
        )


@dataclass(frozen=True)
class Snapshot:
    """캡처 1회분 — 메타 + RunRecord 리스트."""

    label: str               # 캡처 라벨(예: "baseline-pgvector", "phase2a-canfollow")
    captured_at: str         # ISO8601 문자열(러너가 주입 — Date.now 직접호출 회피)
    records: list[RunRecord]

    def to_json(self) -> str:
        return json.dumps(
            {
                "label": self.label,
                "captured_at": self.captured_at,
                "records": [r.to_dict() for r in self.records],
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> Snapshot:
        d = json.loads(text)
        return cls(
            label=d.get("label", "unknown"),
            captured_at=d.get("captured_at", ""),
            records=[RunRecord.from_dict(r) for r in d.get("records", [])],
        )


def save_snapshot(snap: Snapshot, path: Path = SNAPSHOT_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snap.to_json(), encoding="utf-8")
    return path


def load_snapshot(path: Path = SNAPSHOT_FILE) -> Snapshot | None:
    if not path.exists():
        return None
    return Snapshot.from_json(path.read_text(encoding="utf-8"))
