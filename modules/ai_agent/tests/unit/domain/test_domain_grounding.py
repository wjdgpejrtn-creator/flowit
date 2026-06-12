"""도메인 그라운딩 VO 파서·검증 (ADR-0029) — skill builder 전용, composer 무관."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent.domain.value_objects.domain_grounding import (
    Domain,
    parse_domain,
    to_bundle,
)

_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds" / "domains"

_KNOWN = {"webhook_trigger", "manual_trigger", "if_condition", "slack_post_message", "gmail_send"}

_MINIMAL = {
    "code": "demo",
    "name": "데모",
    "kind": "industry",
    "rules": [
        {"kind": "required", "node_type": "gmail_send"},
        {"kind": "forbidden", "node_type": "if_condition"},
        {"kind": "focus", "statement": "추적 ID 남기기", "severity": "high"},
    ],
    "playbooks": [
        {
            "id": "demo.flow",
            "name": "데모 플로우",
            "intent": "데모|demo",
            "stages": [
                {"order": 2, "role": "sink", "purpose": "통지", "allowed_node_types": ["slack_post_message"]},
                {"order": 1, "role": "trigger", "purpose": "수신", "allowed_node_types": ["webhook_trigger"]},
            ],
        }
    ],
}


def test_parse_valid_domain():
    d = parse_domain(_MINIMAL, _KNOWN)
    assert d.code == "demo" and d.kind == "industry"
    assert len(d.rules) == 3
    assert len(d.playbooks) == 1


def test_stages_sorted_by_order():
    d = parse_domain(_MINIMAL, _KNOWN)
    orders = [s.order for s in d.playbooks[0].stages]
    assert orders == [1, 2]  # 시드 순서와 무관하게 order로 정렬


def test_to_bundle_aggregates_required_forbidden():
    bundle = to_bundle(parse_domain(_MINIMAL, _KNOWN))
    assert bundle.required_node_types == ("gmail_send",)
    assert bundle.forbidden_node_types == ("if_condition",)


def test_rejects_hallucinated_node_type():
    bad = {**_MINIMAL, "rules": [{"kind": "required", "node_type": "nonexistent_node_xyz"}]}
    with pytest.raises(ValueError, match="환각"):
        parse_domain(bad, _KNOWN)


def test_required_rule_needs_node_type_or_statement():
    bad = {**_MINIMAL, "playbooks": [], "rules": [{"kind": "required"}]}
    with pytest.raises(ValueError, match="node_type 또는 statement"):
        parse_domain(bad, _KNOWN)


def test_unknown_rule_kind_rejected():
    bad = {**_MINIMAL, "playbooks": [], "rules": [{"kind": "bogus", "statement": "x"}]}
    with pytest.raises(ValueError, match="rule kind"):
        parse_domain(bad, _KNOWN)


def test_invalid_domain_kind_rejected():
    bad = {**_MINIMAL, "kind": "sector"}
    with pytest.raises(ValueError, match="industry"):
        parse_domain(bad, _KNOWN)


# ── 레퍼런스 시드: 실 카탈로그로 검증 (내 seeds/domains/*.json의 node_type 실재 보장) ──
def test_reference_seeds_validate_against_real_catalog():
    from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES

    known = set(EXECUTABLE_NODE_TYPES)
    seeds = sorted(_SEEDS_DIR.glob("*.json"))
    assert seeds, "seeds/domains/*.json 시드가 있어야 한다(ecommerce 레퍼런스)"
    parsed: list[Domain] = []
    for path in seeds:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        parsed.append(parse_domain(data, known))  # 환각 node_type이면 ValueError로 실패
    assert any(d.code == "ecommerce" for d in parsed)
