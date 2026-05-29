from uuid import uuid4

import pytest
from common_schemas.enums import RiskLevel

from nodes_graph.application.use_cases.search_nodes_use_case import SearchNodesUseCase
from nodes_graph.domain.entities.node_definition import NodeDefinition


class _Repo:
    def __init__(self, nodes=None):
        self._nodes = {str(n.node_id): n for n in (nodes or [])}

    async def upsert(self, d):
        self._nodes[str(d.node_id)] = d
        return d
    async def list_all(self, mvp_only=False): return list(self._nodes.values())
    async def get_by_id(self, nid): return self._nodes.get(str(nid))
    async def search_by_embedding(self, q, limit=10, viewer_user_id=None, viewer_team_ids=None):
        return list(self._nodes.values())[:limit]


class _Embedder:
    async def embed(self, text): return [0.1] * 768
    async def embed_batch(self, texts): return [[0.1] * 768 for _ in texts]


def _def(node_type="test"):
    return NodeDefinition(
        node_id=uuid4(), node_type=node_type, name=node_type, category="x", version="1.0.0",
        input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="x", is_mvp=True,
    )


@pytest.mark.asyncio
async def test_search_returns_results():
    node = _def("gmail_send")
    uc = SearchNodesUseCase(_Repo([node]), _Embedder())
    results = await uc.execute("이메일 보내기")
    assert any(n.node_type == "gmail_send" for n in results)


@pytest.mark.asyncio
async def test_search_respects_limit():
    nodes = [_def(f"node_{i}") for i in range(5)]
    uc = SearchNodesUseCase(_Repo(nodes), _Embedder())
    results = await uc.execute("검색", limit=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_search_empty_repo_returns_empty():
    uc = SearchNodesUseCase(_Repo(), _Embedder())
    results = await uc.execute("아무것도 없음")
    assert results == []


@pytest.mark.asyncio
async def test_search_passes_scope_to_repo():
    # ADR-0020 (i): 검색 가시성 격리 — viewer scope를 repo로 전달해야 한다.
    captured = {}

    class _ScopeRepo(_Repo):
        async def search_by_embedding(self, q, limit=10, viewer_user_id=None, viewer_team_ids=None):
            captured["viewer_user_id"] = viewer_user_id
            captured["viewer_team_ids"] = viewer_team_ids
            return []

    uid, tid = uuid4(), uuid4()
    uc = SearchNodesUseCase(_ScopeRepo(), _Embedder())
    await uc.execute("쿼리", viewer_user_id=uid, viewer_team_ids=[tid])
    assert captured["viewer_user_id"] == uid
    assert captured["viewer_team_ids"] == [tid]


@pytest.mark.asyncio
async def test_search_scope_defaults_none_global():
    # scope 미지정 = None = 전역(기존 호출 호환, 비침습)
    captured = {}

    class _ScopeRepo(_Repo):
        async def search_by_embedding(self, q, limit=10, viewer_user_id=None, viewer_team_ids=None):
            captured["viewer_user_id"] = viewer_user_id
            return list(self._nodes.values())[:limit]

    uc = SearchNodesUseCase(_ScopeRepo([_def("x")]), _Embedder())
    await uc.execute("쿼리")
    assert captured["viewer_user_id"] is None
