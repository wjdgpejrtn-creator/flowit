from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas import (
    AgentProtocolRequest,
    AgentProtocolResponse,
    AgentState,
    MemoryEntry,
)
from common_schemas.enums import AgentMode, ExecutionStatus
from common_schemas.transport import AgentNodeFrame, ResultFrame


def _state(mode: AgentMode = AgentMode.ONBOARDING) -> AgentState:
    return AgentState(
        session_id=uuid4(),
        user_id=uuid4(),
        messages=[],
        turn_count=0,
        mode=mode,
        execution_status=ExecutionStatus.RUNNING,
    )


class TestAgentProtocolRequest:
    def test_minimal(self):
        req = AgentProtocolRequest(
            session_id=uuid4(),
            user_id=uuid4(),
            state=_state(),
        )
        assert req.personal_memory == []
        assert req.payload == {}
        assert req.trace_id is None

    def test_with_memory_and_payload(self):
        uid = uuid4()
        entry = MemoryEntry(user_id=uid, memory_type="preference", content="Slack 우선")
        req = AgentProtocolRequest(
            session_id=uuid4(),
            user_id=uid,
            state=_state(AgentMode.SKILL_BUILDER),
            personal_memory=[entry],
            payload={"industry_code": "manufacturing"},
            trace_id="trace-abc",
        )
        assert req.personal_memory[0].content == "Slack 우선"
        assert req.payload["industry_code"] == "manufacturing"
        assert req.trace_id == "trace-abc"

    def test_roundtrip_json(self):
        req = AgentProtocolRequest(
            session_id=uuid4(),
            user_id=uuid4(),
            state=_state(),
            payload={"k": 1},
        )
        restored = AgentProtocolRequest.model_validate_json(req.model_dump_json())
        assert restored.payload["k"] == 1

    def test_immutable(self):
        req = AgentProtocolRequest(
            session_id=uuid4(),
            user_id=uuid4(),
            state=_state(),
        )
        with pytest.raises(ValidationError):
            req.trace_id = "x"  # type: ignore[misc]


class TestAgentProtocolResponse:
    def test_continue(self):
        resp = AgentProtocolResponse(
            frames=[AgentNodeFrame(agent_node_name="intent_node")],
            state_delta={"turn_count": 1},
            next_action="continue",
        )
        assert resp.next_action == "continue"
        assert resp.frames[0].agent_node_name == "intent_node"

    def test_complete_with_result(self):
        resp = AgentProtocolResponse(
            frames=[ResultFrame(intent="propose", payload={"workflow_id": "wf-1"})],
            state_delta={},
            next_action="complete",
        )
        assert resp.next_action == "complete"

    def test_error_next_action(self):
        resp = AgentProtocolResponse(next_action="error")
        assert resp.frames == []
        assert resp.state_delta == {}

    def test_invalid_next_action(self):
        with pytest.raises(ValidationError):
            AgentProtocolResponse(next_action="weird")  # type: ignore[arg-type]

    def test_frame_discriminator_roundtrip(self):
        resp = AgentProtocolResponse(
            frames=[
                AgentNodeFrame(agent_node_name="intent_node"),
                ResultFrame(intent="propose", payload={"workflow_id": "wf-1"}),
            ],
            next_action="complete",
        )
        restored = AgentProtocolResponse.model_validate_json(resp.model_dump_json())
        assert restored.frames[0].frame_type == "agent_node"
        assert restored.frames[1].frame_type == "result"
