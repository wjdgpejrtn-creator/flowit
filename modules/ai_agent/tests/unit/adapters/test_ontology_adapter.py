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
    records = [
        {
            "node_type": "slack_send", "category": "messaging", "risk_level": "medium",
            "requires": ["slack"], "siblings": ["discord_send", "slack_send"],
        }
    ]
    driver = _FakeDriver(records)
    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=lambda: driver)

    sg = await adapter.expand_candidates(["slack_send"])

    assert sg.seeds == ("slack_send",)
    seed = next(n for n in sg.nodes if n.node_type == "slack_send")
    assert seed.requires == ("slack",)
    assert seed.category == "messaging"
    # 자기 자신은 sibling에서 제거, discord는 후보로 포함
    assert sg.adjacency["slack_send"] == ("discord_send",)
    assert sg.allowed_node_types() == frozenset({"slack_send", "discord_send"})
    assert driver.closed is True  # per-request driver는 반드시 close


@pytest.mark.asyncio
async def test_empty_seeds_short_circuits_without_driver():
    def _boom():
        raise AssertionError("빈 seed에서는 driver를 만들면 안 된다")

    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=_boom)
    sg = await adapter.expand_candidates([])
    assert sg.nodes == ()
    assert sg.seeds == ()


@pytest.mark.asyncio
async def test_match_patterns_not_implemented_phase1():
    adapter = Neo4jOntologyAdapter(uri="neo4j+s://x", driver_factory=lambda: None)
    with pytest.raises(NotImplementedError):
        await adapter.match_patterns("검증/재생성")


def test_missing_uri_raises_on_driver_creation():
    # driver_factory 없고 NEO4J_URI 없으면 실제 호출 시 RuntimeError (lazy)
    adapter = Neo4jOntologyAdapter(uri=None)
    with pytest.raises(RuntimeError, match="NEO4J_URI"):
        adapter._new_driver()
