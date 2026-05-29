from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas import DraftSpec, NodeConfig
from common_schemas.agent import SlotFillingState
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError

from ai_agent.domain.ports import LLMPort
from ai_agent.domain.services.drafter_service import DrafterService, _DraftResponse, _EdgeDraft, _NodeDraft


def _node_config(node_type: str) -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type,
        category="test",
        version="1.0",
        description="",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        is_mvp=True,
    )


def _spec() -> DraftSpec:
    return DraftSpec(
        natural_language_intent="test intent",
        discovered_entities={},
        unresolved_nodes=[],
        slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
        consultant_turn_count=0,
    )


def _mock_llm(response: _DraftResponse) -> LLMPort:
    llm = AsyncMock(spec=LLMPort)
    llm.generate_structured = AsyncMock(return_value=response)
    return llm


class TestDrafterServiceBuild:
    def setup_method(self):
        self.owner_id = uuid4()

    def _svc(self, response: _DraftResponse) -> DrafterService:
        return DrafterService(_mock_llm(response))

    @pytest.mark.asyncio
    async def test_edges_correctly_mapped_to_instance_ids(self):
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="B")],
            connections=[_EdgeDraft(from_node_type="A", to_node_type="B")],
        )
        svc = self._svc(response)
        candidates = [_node_config("A"), _node_config("B")]
        schema = await svc.draft(_spec(), candidates, self.owner_id)

        assert len(schema.connections) == 1
        edge = schema.connections[0]
        a_id = next(n.instance_id for n in schema.nodes if True)
        node_ids = {n.instance_id for n in schema.nodes}
        assert edge.from_instance_id in node_ids
        assert edge.to_instance_id in node_ids
        assert edge.from_instance_id != edge.to_instance_id

    @pytest.mark.asyncio
    async def test_duplicate_node_type_raises(self):
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="A")],
            connections=[],
        )
        svc = self._svc(response)
        candidates = [_node_config("A")]
        with pytest.raises(ExecutionError) as exc_info:
            await svc.draft(_spec(), candidates, self.owner_id)
        assert exc_info.value.code == "E_DUPLICATE_NODE_TYPE"

    @pytest.mark.asyncio
    async def test_unknown_edge_node_type_skipped_with_warning(self, caplog):
        import logging
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A")],
            connections=[_EdgeDraft(from_node_type="A", to_node_type="UNKNOWN")],
        )
        svc = self._svc(response)
        candidates = [_node_config("A")]
        with caplog.at_level(logging.WARNING):
            schema = await svc.draft(_spec(), candidates, self.owner_id)
        assert len(schema.connections) == 0
        assert "UNKNOWN" in caplog.text

    @pytest.mark.asyncio
    async def test_connections_included_in_workflow_schema(self):
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="B"), _NodeDraft(node_type="C")],
            connections=[
                _EdgeDraft(from_node_type="A", to_node_type="B"),
                _EdgeDraft(from_node_type="B", to_node_type="C"),
            ],
        )
        svc = self._svc(response)
        candidates = [_node_config("A"), _node_config("B"), _node_config("C")]
        schema = await svc.draft(_spec(), candidates, self.owner_id)

        assert len(schema.connections) == 2
        assert schema.is_draft is True
