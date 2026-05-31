from uuid import uuid4

from pydantic import TypeAdapter

from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    ChatMessageFrame,
    DraftSpecDeltaFrame,
    ErrorFrame,
    RationaleDeltaFrame,
    ResultFrame,
    SessionFrame,
    SkillOption,
    SkillSelectionFrame,
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


class TestSkillSelectionFrame:
    def test_create(self):
        f = SkillSelectionFrame(
            prompt="적용할 스킬을 선택하세요",
            options=[
                SkillOption(skill_id=uuid4(), name="세무 전문가", description="세무 도메인 지침"),
            ],
        )
        assert f.frame_type == "skill_selection"
        assert f.field_name == "skill_selection"
        assert f.allow_skip is True
        assert f.options[0].name == "세무 전문가"
        assert f.options[0].document_preview is None
        assert f.options[0].node_definition_id is None


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


class TestChatMessageFrame:
    def test_create_user(self):
        f = ChatMessageFrame(role="user", content="이메일 자동화 워크플로우 만들어줘")
        assert f.frame_type == "chat_message"
        assert f.role == "user"
        assert f.content == "이메일 자동화 워크플로우 만들어줘"

    def test_create_assistant(self):
        f = ChatMessageFrame(role="assistant", content="워크플로우 초안을 생성했습니다")
        assert f.frame_type == "chat_message"
        assert f.role == "assistant"


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

    def test_discriminate_chat_message(self):
        adapter = TypeAdapter(AnySSEFrame)
        frame = adapter.validate_python(
            {"frame_type": "chat_message", "role": "user", "content": "hello"}
        )
        assert isinstance(frame, ChatMessageFrame)

    def test_discriminate_skill_selection(self):
        adapter = TypeAdapter(AnySSEFrame)
        sid = uuid4()
        frame = adapter.validate_python(
            {
                "frame_type": "skill_selection",
                "prompt": "스킬 선택",
                "options": [{"skill_id": str(sid), "name": "n", "description": "d"}],
            }
        )
        assert isinstance(frame, SkillSelectionFrame)
        assert frame.options[0].skill_id == sid
