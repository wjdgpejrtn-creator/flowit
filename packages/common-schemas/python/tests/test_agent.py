from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.agent import AgentState, DraftSpec, IntentResult, SlotFillingState, UnresolvedNode
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
        for intent in ("clarify", "draft", "refine", "propose"):
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
