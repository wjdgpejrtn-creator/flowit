from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common_schemas import IntentResult
from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse
from common_schemas.transport import ResultFrame

from ai_agent.application.agents.orchestrator.route_request_use_case import RouteRequestUseCase
from ai_agent.domain.ports.sub_agent_client import SubAgentClient
from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService


def _make_done_response() -> AgentProtocolResponse:
    return AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")


def _make_result_response() -> AgentProtocolResponse:
    return AgentProtocolResponse(
        frames=[ResultFrame(intent="draft", payload={})],
        state_delta={},
        next_action="complete",
    )


class FakeSubAgentClient(SubAgentClient):
    def __init__(self, responses: list[AgentProtocolResponse] | None = None):
        self.sent_requests: list[AgentProtocolRequest] = []
        self._responses = responses or [_make_done_response()]

    async def send(self, request: AgentProtocolRequest) -> AsyncIterator[AgentProtocolResponse]:
        self.sent_requests.append(request)
        for resp in self._responses:
            yield resp


class FailingSubAgentClient(SubAgentClient):
    """send() 호출 시 항상 예외를 발생시키는 테스트용 클라이언트."""

    def __init__(self, exc: Exception | None = None):
        self.sent_requests: list[AgentProtocolRequest] = []
        self._exc = exc or ConnectionError("personalization agent 연결 실패")

    async def send(self, request: AgentProtocolRequest) -> AsyncIterator[AgentProtocolResponse]:
        self.sent_requests.append(request)
        raise self._exc
        # AsyncGenerator protocol — yield 없이 raise만 해도 async generator로 동작
        yield  # type: ignore[misc]


def _make_use_case(intent: str, entities: dict | None = None):
    analyzer = MagicMock(spec=IntentAnalyzerService)
    analyzer.analyze = AsyncMock(
        return_value=IntentResult(
            intent=intent,
            confidence=0.9,
            analyzed_entities=entities or {},
        )
    )
    personalization = FakeSubAgentClient(
        responses=[
            AgentProtocolResponse(
                frames=[],
                state_delta={"personal_memory": []},
                next_action="complete",
            )
        ]
    )
    composer = FakeSubAgentClient([_make_result_response()])
    skills = FakeSubAgentClient([_make_result_response()])

    use_case = RouteRequestUseCase(
        intent_analyzer=analyzer,
        personalization_client=personalization,
        composer_client=composer,
        skills_client=skills,
    )
    return use_case, personalization, composer, skills


async def _collect(use_case, user_id, session_id, message):
    gen = await use_case.execute(user_id, session_id, message)
    frames = []
    async for frame in gen:
        frames.append(frame)
    return frames


@pytest.mark.asyncio
async def test_propose_intent_does_not_call_update_memory():
    """propose intent 시 update_memory_node가 호출되지 않아야 한다."""
    use_case, personalization, _, _ = _make_use_case("propose")
    user_id, session_id = uuid4(), uuid4()

    await _collect(use_case, user_id, session_id, "확정할게요")

    # personalization client에 보낸 요청 중 update_memory action이 없어야 함
    update_calls = [
        r for r in personalization.sent_requests
        if r.payload.get("action") == "update_memory"
    ]
    assert len(update_calls) == 0


@pytest.mark.asyncio
async def test_finally_block_always_calls_cleanup():
    """intent 결과와 관계없이 finally 블록에서 cleanup이 호출되어야 한다."""
    for intent in ("draft", "propose", "build_skill"):
        use_case, personalization, _, _ = _make_use_case(
            intent,
            entities={"source_type": "industry_default", "industry_code": "ecommerce"},
        )
        user_id, session_id = uuid4(), uuid4()

        await _collect(use_case, user_id, session_id, "테스트 메시지")

        cleanup_calls = [
            r for r in personalization.sent_requests
            if r.payload.get("action") == "cleanup"
        ]
        assert len(cleanup_calls) == 1, f"intent={intent}일 때 cleanup 미호출"


@pytest.mark.asyncio
async def test_non_propose_intent_calls_update_memory():
    """propose 외 intent 시 update_memory_node가 호출되어야 한다."""
    for intent in ("draft", "refine", "clarify"):
        use_case, personalization, _, _ = _make_use_case(intent)
        user_id, session_id = uuid4(), uuid4()

        await _collect(use_case, user_id, session_id, "워크플로우 만들어줘")

        update_calls = [
            r for r in personalization.sent_requests
            if r.payload.get("action") == "update_memory"
        ]
        assert len(update_calls) == 1, f"intent={intent}일 때 update_memory 미호출"


@pytest.mark.asyncio
async def test_build_skill_industry_default_payload():
    """build_skill + industry_default → skills client에 industry_code payload 전달."""
    use_case, _, _, skills = _make_use_case(
        "build_skill",
        entities={"source_type": "industry_default", "industry_code": "ecommerce"},
    )
    await _collect(use_case, uuid4(), uuid4(), "이커머스 스킬 만들어줘")

    assert len(skills.sent_requests) == 1
    payload = skills.sent_requests[0].payload
    assert payload["source_type"] == "industry_default"
    assert payload["industry_code"] == "ecommerce"


@pytest.mark.asyncio
async def test_build_skill_functional_domain_payload():
    """build_skill + functional_domain → skills client에 domain_code payload 전달."""
    use_case, _, _, skills = _make_use_case(
        "build_skill",
        entities={"source_type": "functional_domain", "domain_code": "hr"},
    )
    await _collect(use_case, uuid4(), uuid4(), "HR 팀용 스킬 만들어줘")

    assert len(skills.sent_requests) == 1
    payload = skills.sent_requests[0].payload
    assert payload["source_type"] == "functional_domain"
    assert payload["domain_code"] == "hr"


@pytest.mark.asyncio
async def test_load_memory_failure_continues_session_with_empty_memory():
    """personalization 클라이언트 장애 시 빈 메모리로 세션을 계속 진행해야 한다."""
    analyzer = MagicMock(spec=IntentAnalyzerService)
    analyzer.analyze = AsyncMock(
        return_value=IntentResult(intent="draft", confidence=0.9, analyzed_entities={})
    )
    failing_personalization = FailingSubAgentClient(ConnectionError("Modal app stopped"))
    composer = FakeSubAgentClient([_make_result_response()])

    use_case = RouteRequestUseCase(
        intent_analyzer=analyzer,
        personalization_client=failing_personalization,
        composer_client=composer,
        skills_client=FakeSubAgentClient(),
    )

    frames = await _collect(use_case, uuid4(), uuid4(), "워크플로우 만들어줘")

    # 세션이 죽지 않고 정상적으로 frame들이 수집되어야 함
    frame_types = [f.frame_type for f in frames]
    assert "session" in frame_types
    assert "agent_node" in frame_types
    # load_memory_node frame이 존재하고, 그 이후 intent_node로 진행
    agent_node_names = [
        f.agent_node_name for f in frames if f.frame_type == "agent_node"
    ]
    assert "load_memory_node" in agent_node_names
    assert "intent_node" in agent_node_names


@pytest.mark.asyncio
async def test_update_memory_failure_does_not_crash_session():
    """update_memory 실패 시 세션이 에러 없이 종료되어야 한다."""
    analyzer = MagicMock(spec=IntentAnalyzerService)
    analyzer.analyze = AsyncMock(
        return_value=IntentResult(intent="draft", confidence=0.9, analyzed_entities={})
    )

    call_count = 0

    class SelectiveFailClient(SubAgentClient):
        async def send(self, request: AgentProtocolRequest) -> AsyncIterator[AgentProtocolResponse]:
            nonlocal call_count
            call_count += 1
            action = request.payload.get("action")
            if action == "update_memory":
                raise RuntimeError("GCS write 타임아웃")
            # load_memory / cleanup은 정상 응답
            yield AgentProtocolResponse(
                frames=[],
                state_delta={"personal_memory": []},
                next_action="complete",
            )

    use_case = RouteRequestUseCase(
        intent_analyzer=analyzer,
        personalization_client=SelectiveFailClient(),
        composer_client=FakeSubAgentClient([_make_result_response()]),
        skills_client=FakeSubAgentClient(),
    )

    # 예외가 전파되지 않고 정상 완료되어야 함
    frames = await _collect(use_case, uuid4(), uuid4(), "워크플로우 만들어줘")
    assert len(frames) > 0


@pytest.mark.asyncio
async def test_build_skill_sop_payload_document_block_structure():
    """build_skill + sop → DocumentBlock 구조(Optional 필드 None 포함) 검증."""
    use_case, _, _, skills = _make_use_case(
        "build_skill",
        entities={"source_type": "sop"},
    )
    await _collect(use_case, uuid4(), uuid4(), "ITSM 티켓 처리 절차로 스킬 만들어줘")

    assert len(skills.sent_requests) == 1
    payload = skills.sent_requests[0].payload
    assert payload["source_type"] == "sop"

    doc = payload["document"]
    assert "document_id" in doc
    assert "file_meta" in doc
    assert "blocks" in doc
    assert len(doc["blocks"]) == 1
    assert doc["blocks"][0]["block_type"] == "text"
    assert doc["blocks"][0]["content"] == "ITSM 티켓 처리 절차로 스킬 만들어줘"
    # Optional 필드 누락 없이 None으로 처리 가능한지 확인
    assert doc.get("workflow_id") is None
    assert doc.get("parser") is None
