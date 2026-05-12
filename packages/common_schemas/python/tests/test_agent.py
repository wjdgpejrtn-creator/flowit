from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.agent import (
    AgentState,
    DraftSpec,
    IntentResult,
    MemoryEntry,
    SlotFillingState,
    UnresolvedNode,
)
from common_schemas.enums import AgentMode, ExecutionStatus


class TestUnresolvedNode:
    def test_create(self):
        un = UnresolvedNode(
            placeholder_id="ph_1",
            hint="needs HTTP node",
            candidate_node_types=["http_request", "webhook"],
        )
        assert len(un.candidate_node_types) == 2


class TestSlotFillingState:
    def test_create(self):
        sfs = SlotFillingState(
            asked=["q1"],
            pending=["q2", "q3"],
            filled={"q1": "answer1"},
        )
        assert sfs.filled["q1"] == "answer1"


class TestDraftSpec:
    def test_create(self):
        ds = DraftSpec(
            natural_language_intent="Send email when form submitted",
            unresolved_nodes=[],
            discovered_entities={"trigger": "form_submit"},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=2,
        )
        assert ds.consultant_turn_count == 2


class TestIntentResult:
    def test_valid_intents(self):
        for intent in ("clarify", "draft", "refine", "propose", "build_skill"):
            ir = IntentResult(
                intent=intent,
                confidence=0.9,
                analyzed_entities={},
            )
            assert ir.intent == intent

    def test_invalid_intent(self):
        with pytest.raises(ValidationError):
            IntentResult(
                intent="invalid",
                confidence=0.9,
                analyzed_entities={},
            )


class TestMemoryEntry:
    def test_defaults(self):
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="preference",
            content="Slack 알림 항상 포함",
        )
        assert entry.source_session_id is None
        assert entry.metadata == {}
        assert entry.created_at is not None

    def test_with_session(self):
        sid = uuid4()
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="workflow_pattern",
            content="주간 보고서 자동화",
            source_session_id=sid,
            metadata={"score": 0.91},
        )
        assert entry.source_session_id == sid
        assert entry.metadata["score"] == 0.91

    def test_is_ephemeral_whitespace(self):
        entry = MemoryEntry(user_id=uuid4(), memory_type="summary", content="   ")
        assert entry.is_ephemeral() is True

    def test_is_ephemeral_filled(self):
        entry = MemoryEntry(user_id=uuid4(), memory_type="correction", content="x")
        assert entry.is_ephemeral() is False

    def test_immutable(self):
        entry = MemoryEntry(user_id=uuid4(), memory_type="preference", content="a")
        with pytest.raises(ValidationError):
            entry.content = "b"  # type: ignore[misc]

    def test_invalid_memory_type(self):
        with pytest.raises(ValidationError):
            MemoryEntry(user_id=uuid4(), memory_type="weird", content="a")  # type: ignore[arg-type]


class TestAgentState:
    def test_create_minimal(self):
        state = AgentState(
            session_id=uuid4(),
            user_id=uuid4(),
            messages=[],
            turn_count=0,
            mode=AgentMode.ONBOARDING,
            execution_status=ExecutionStatus.RUNNING,
        )
        assert state.draft_spec is None
        assert state.node_candidates == []

    def test_turn_count_max(self):
        with pytest.raises(ValidationError):
            AgentState(
                session_id=uuid4(),
                user_id=uuid4(),
                messages=[],
                turn_count=26,
                mode=AgentMode.GENERAL,
                execution_status=ExecutionStatus.RUNNING,
            )

    def test_turn_count_at_limit(self):
        state = AgentState(
            session_id=uuid4(),
            user_id=uuid4(),
            messages=[],
            turn_count=25,
            mode=AgentMode.GENERAL,
            execution_status=ExecutionStatus.RUNNING,
        )
        assert state.turn_count == 25

    def test_personal_memory_defaults_empty(self):
        state = AgentState(
            session_id=uuid4(),
            user_id=uuid4(),
            messages=[],
            turn_count=0,
            mode=AgentMode.ONBOARDING,
            execution_status=ExecutionStatus.RUNNING,
        )
        assert state.personal_memory == []

    def test_personal_memory_carries_entries(self):
        uid = uuid4()
        entry = MemoryEntry(user_id=uid, memory_type="preference", content="Slack 우선")
        state = AgentState(
            session_id=uuid4(),
            user_id=uid,
            messages=[],
            turn_count=1,
            mode=AgentMode.SKILL_BUILDER,
            execution_status=ExecutionStatus.RUNNING,
            personal_memory=[entry],
        )
        assert state.mode == AgentMode.SKILL_BUILDER
        assert len(state.personal_memory) == 1
        assert state.personal_memory[0].content == "Slack 우선"
