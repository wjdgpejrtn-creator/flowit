"""Neo4jDomainGroundingAdapter (ADR-0029) — fake driver로 VO 조립 + composer 분리 가드."""
from __future__ import annotations

import pytest

from ai_agent.adapters.ontology.neo4j_domain_grounding_adapter import (
    Neo4jDomainGroundingAdapter,
)


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    def __init__(self, record, sink):
        self._record = record
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def run(self, cypher, **params):
        self._sink.append((cypher, params))
        return _FakeResult(self._record)


class _FakeDriver:
    def __init__(self, record, sink):
        self._record = record
        self._sink = sink
        self.closed = False

    def session(self):
        return _FakeSession(self._record, self._sink)

    async def close(self):
        self.closed = True


_RECORD = {
    "code": "ecommerce",
    "name": "이커머스",
    "kind": "industry",
    "description": "이커머스 자동화",
    "domain_rules": [
        {"kind": "required", "node_type": "gmail_send", "statement": "", "rationale": "", "severity": "normal"},
        {"kind": "forbidden", "node_type": "postgresql_query", "statement": "", "rationale": "", "severity": "high"},
        {"kind": "focus", "node_type": None, "statement": "추적 ID 남기기", "rationale": "", "severity": "high"},
    ],
    "playbooks": [
        {
            "id": "ecom.refund_approval",
            "name": "환불 승인",
            "intent": "환불|refund",
            "summary": "",
            "rules": [
                {"kind": "required", "node_type": None, "statement": "사람 승인",
                 "rationale": "", "severity": "high"}
            ],
            "stages": [
                {"order": 2, "role": "sink", "purpose": "통지",
                 "allowed_node_types": ["gmail_send"], "key_points": []},
                {"order": 1, "role": "trigger", "purpose": "수신",
                 "allowed_node_types": ["webhook_trigger"], "key_points": ["요청ID 필수"]},
            ],
        }
    ],
}


def _adapter(record, sink):
    return Neo4jDomainGroundingAdapter(driver_factory=lambda: _FakeDriver(record, sink))


@pytest.mark.asyncio
async def test_builds_bundle_from_record():
    sink: list = []
    bundle = await _adapter(_RECORD, sink).get_domain_grounding("ecommerce")

    assert bundle is not None
    assert bundle.domain.code == "ecommerce"
    assert bundle.required_node_types == ("gmail_send",)
    assert bundle.forbidden_node_types == ("postgresql_query",)
    pb = bundle.domain.playbooks[0]
    assert pb.id == "ecom.refund_approval"
    assert [s.order for s in pb.stages] == [1, 2]  # order로 정렬
    assert pb.stages[0].key_points == ("요청ID 필수",)


@pytest.mark.asyncio
async def test_none_when_no_record():
    bundle = await _adapter(None, []).get_domain_grounding("unknown")
    assert bundle is None


@pytest.mark.asyncio
async def test_query_does_not_touch_composer_labels():
    # 분리 불변식: 도메인 어댑터 쿼리는 composer 라벨(:Node/:Skeleton/:Pattern/:SlotSpec)을 절대 안 긁는다.
    sink: list = []
    await _adapter(_RECORD, sink).get_domain_grounding("ecommerce")
    cypher = " ".join(q for q, _ in sink)
    for composer_label in (":Node", ":Skeleton", ":Pattern", ":SlotSpec", "CAN_FOLLOW", "FILLED_BY"):
        assert composer_label not in cypher, f"도메인 쿼리가 composer 라벨 참조: {composer_label}"
    # 도메인 라벨은 참조
    assert ":Domain" in cypher and ":Playbook" in cypher
