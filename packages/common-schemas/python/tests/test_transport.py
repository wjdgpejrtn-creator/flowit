from uuid import uuid4

from pydantic import TypeAdapter

from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    DraftSpecDeltaFrame,
    ErrorFrame,
    RationaleDeltaFrame,
    ResultFrame,
    SessionFrame,
    SlotFillQuestionFrame,
)


class TestSessionFrame:
    def test_create(self):
        f = SessionFrame(session_id=uuid4(), langgraph_thread_id=uuid4())
        assert f.frame_type == "session"


class TestAgentNodeFrame:
    def test_create(self):
        f = AgentNodeFrame(agent_node_name="intent_classifier")
        assert f.frame_type == "agent_node"


class TestRationaleDeltaFrame:
    def test_create(self):
        f = RationaleDeltaFrame(delta="thinking...")
        assert f.frame_type == "rationale_delta"


class TestSlotFillQuestionFrame:
    def test_create(self):
        f = SlotFillQuestionFrame(question="What email?", field_name="recipient")
        assert f.frame_type == "slot_fill_question"


class TestDraftSpecDeltaFrame:
    def test_create(self):
        f = DraftSpecDeltaFrame(delta={"intent": "updated"})
        assert f.frame_type == "draft_spec_delta"


class TestResultFrame:
    def test_create(self):
        f = ResultFrame(intent="draft", payload={"workflow_id": "abc"})
        assert f.frame_type == "result"


class TestErrorFrame:
    def test_create(self):
        f = ErrorFrame(code="E_TIMEOUT", message="Request timed out")
        assert f.frame_type == "error"


class TestAnySSEFrameDiscriminator:
    def test_discriminate_from_dict(self):
        adapter = TypeAdapter(AnySSEFrame)
        sid = uuid4()
        tid = uuid4()
        frame = adapter.validate_python(
            {"frame_type": "session", "session_id": str(sid), "langgraph_thread_id": str(tid)}
        )
        assert isinstance(frame, SessionFrame)

    def test_discriminate_error(self):
        adapter = TypeAdapter(AnySSEFrame)
        frame = adapter.validate_python(
            {"frame_type": "error", "code": "E_X", "message": "fail"}
        )
        assert isinstance(frame, ErrorFrame)
