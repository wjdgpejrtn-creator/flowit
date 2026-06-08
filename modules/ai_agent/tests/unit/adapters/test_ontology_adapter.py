import pytest

from ai_agent.adapters.ontology import Neo4jOntologyAdapter


class _FakeResult:
    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        async def _gen():
            for r in self._records:
                yield r

        return _gen()


class _FakeSession:
    def __init__(self, records, calls):
        self._records = records
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, **params):
        self._calls.append((query, params))
        return _FakeResult(self._records)


class _FakeDriver:
    def __init__(self, records):
        self._records = records
        self.calls = []
        self.closed = False

    def session(self):
        return _FakeSession(self._records, self.calls)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_expand_candidates_maps_records_to_subgraph():
    # CAN_FOLLOW 순방향 이웃을 successors 맵으로 회수 (ADR-0026 §4.2a).
    records = [
        {
            "node_type": "csv_parse", "category": "transform", "risk_level": "low",
            "requires": [],
            "successors": [
                {"node_type": "csv_build", "category": "transform", "risk_level": "low", "confidence": 1},
                {"node_type": "csv_parse", "category": "transform", "risk_level": "low", "confidence": 1},  # self
                {"node_type": None, "category": None, "risk_level": None, "confidence": None},  # null succ
            ],
        }
    ]
    driver = _FakeDriver(records)
    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=lambda: driver)

    sg = await adapter.expand_candidates(["csv_parse"])

    assert sg.seeds == ("csv_parse",)
    seed = next(n for n in sg.nodes if n.node_type == "csv_parse")
    assert seed.category == "transform"
    # 자기 자신·null succ는 제거, csv_build만 후행 노드로 포함
    assert sg.adjacency["csv_parse"] == ("csv_build",)
    assert sg.allowed_node_types() == frozenset({"csv_parse", "csv_build"})
    assert driver.closed is True  # per-request driver는 반드시 close


@pytest.mark.asyncio
async def test_expand_successors_sorted_by_confidence_desc():
    # 소비측 cap이 고신뢰 이웃을 결정적으로 보존하도록 adjacency는 confidence 내림차순 (#410 MED).
    records = [
        {
            "node_type": "a", "category": "transform", "risk_level": "low", "requires": [],
            "successors": [
                {"node_type": "low1", "category": "x", "risk_level": "low", "confidence": 1},
                {"node_type": "high", "category": "x", "risk_level": "low", "confidence": 2},
                {"node_type": "low2", "category": "x", "risk_level": "low", "confidence": 1},
            ],
        }
    ]
    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=lambda: _FakeDriver(records))
    sg = await adapter.expand_candidates(["a"])
    # confidence 2가 먼저, 동률(1)은 node_type 사전순으로 결정적
    assert sg.adjacency["a"] == ("high", "low1", "low2")


@pytest.mark.asyncio
async def test_empty_seeds_short_circuits_without_driver():
    def _boom():
        raise AssertionError("빈 seed에서는 driver를 만들면 안 된다")

    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=_boom)
    sg = await adapter.expand_candidates([])
    assert sg.nodes == ()
    assert sg.seeds == ()


@pytest.mark.asyncio
async def test_match_patterns_returns_templates():
    records = [
        {
            "name": "quality_gate_loop",
            "intent": "검증 후 재생성",
            "role_rows": [
                {"slot": "generator", "node_type": "llm_generate"},
                {"slot": "evaluator", "node_type": "if_condition"},
            ],
        }
    ]
    driver = _FakeDriver(records)
    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=lambda: driver)

    templates = await adapter.match_patterns("검증/재생성")

    assert len(templates) == 1
    t = templates[0]
    assert t.name == "quality_gate_loop"
    assert t.role_slots["generator"] == ("llm_generate",)
    assert t.role_slots["evaluator"] == ("if_condition",)
    assert driver.closed is True


@pytest.mark.asyncio
async def test_match_patterns_empty_when_no_pattern_nodes():
    driver = _FakeDriver([])
    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=lambda: driver)
    templates = await adapter.match_patterns("품질 검증")
    assert templates == []


def test_missing_uri_raises_on_driver_creation(monkeypatch):
    # driver_factory 없고 NEO4J_URI 없으면 실제 호출 시 RuntimeError (lazy).
    # CI에 NEO4J_URI가 셋돼 있으면 os.getenv 폴백으로 false-pass하므로 명시적으로 제거.
    monkeypatch.delenv("NEO4J_URI", raising=False)
    adapter = Neo4jOntologyAdapter(uri=None)
    with pytest.raises(RuntimeError, match="NEO4J_URI"):
        adapter._new_driver()
