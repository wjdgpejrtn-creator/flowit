"""agent-skills-builder Modal app composition root integration test.

services/agents/agent-skills-builder/main.py의 modal runtime-free 영역 검증.

검증 범위 (PR #51 자체 리뷰 후속 권장 항목):
- `_classify_next_action`: SSEFrame → Literal["continue", "complete", "error"]
- `_sse_bytes`: AgentProtocolResponse → SSE "data: <json>\\n\\n" bytes 직렬화
- `AgentProtocolRequest` payload 시그니처 (3 source_type)
- `AgentProtocolResponse` next_action Literal 값
- 3 use case import + main.py route() 시그니처 정합

modal/fastapi/asyncpg 의존성 없음 — pure helpers 직접 호출.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from common_schemas.agent import AgentState
from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse
from common_schemas.enums import AgentMode, ExecutionStatus
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame

# ----------------------------------------------------------------------
# Inline 헬퍼 (conftest 미사용 정책)
# ----------------------------------------------------------------------


def _make_agent_state(session_id: UUID, user_id: UUID) -> AgentState:
    """AgentProtocolRequest.state 최소 필드 헬퍼.

    AgentState는 6 필수 필드(session_id/user_id/messages/turn_count/mode/execution_status)
    + Optional 필드. Skills Builder 호출 패턴은 mode=SKILL_BUILDER + execution_status=RUNNING.
    """
    return AgentState(
        session_id=session_id,
        user_id=user_id,
        messages=[],
        turn_count=0,
        mode=AgentMode.SKILL_BUILDER,
        execution_status=ExecutionStatus.RUNNING,
    )


# ----------------------------------------------------------------------
# main.py 동적 import — agent 디렉터리 이름에 하이픈이 있어 일반 import 불가
# ----------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[4]
_AGENT_MAIN_PATH = _REPO_ROOT / "services" / "agents" / "agent-skills-builder" / "main.py"


def _load_agent_main():
    spec = importlib.util.spec_from_file_location("agent_skills_builder_main", _AGENT_MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_main = _load_agent_main()


# ======================================================================
# _classify_next_action — SSEFrame → AgentProtocolResponse.next_action
# ======================================================================


def test_classify_next_action_result_frame_returns_complete():
    frame = ResultFrame(
        intent="build_skill",
        payload={"industry_code": "ecommerce", "upserted_count": 5, "failed_count": 0, "failed_node_types": []},
    )
    assert agent_main._classify_next_action(frame) == "complete"


def test_classify_next_action_error_frame_returns_error():
    frame = ErrorFrame(code="E_INDUSTRY_DEACTIVATED", message="비활성 산업")
    assert agent_main._classify_next_action(frame) == "error"


def test_classify_next_action_progress_frame_returns_continue():
    frame = AgentNodeFrame(agent_node_name="skills_builder.upsert_skill_node")
    assert agent_main._classify_next_action(frame) == "continue"


# ======================================================================
# _sse_bytes — AgentProtocolResponse → SSE 데이터 라인
# ======================================================================


def test_sse_bytes_returns_bytes_type():
    response = AgentProtocolResponse(frames=[], state_delta={}, next_action="continue")
    assert isinstance(agent_main._sse_bytes(response), bytes)


def test_sse_bytes_follows_sse_data_line_format():
    """SSE 포맷: 'data: <json>\\n\\n'."""
    response = AgentProtocolResponse(frames=[], state_delta={}, next_action="continue")
    raw = agent_main._sse_bytes(response).decode("utf-8")
    assert raw.startswith("data: ")
    assert raw.endswith("\n\n")


def test_sse_bytes_json_body_is_parseable_and_round_trips():
    response = AgentProtocolResponse(
        frames=[
            ResultFrame(
                intent="build_skill",
                payload={"industry_code": "ecommerce", "upserted_count": 5, "failed_count": 0, "failed_node_types": []},
            )
        ],
        state_delta={"key": "value"},
        next_action="complete",
    )
    raw = agent_main._sse_bytes(response).decode("utf-8")
    json_body = raw[len("data: "):-len("\n\n")]
    parsed = json.loads(json_body)
    assert parsed["next_action"] == "complete"
    assert parsed["state_delta"] == {"key": "value"}
    assert len(parsed["frames"]) == 1


def test_sse_bytes_preserves_korean_text_utf8():
    """한국어/em-dash 등 비-ASCII 문자가 UTF-8로 보존되어야 한다."""
    response = AgentProtocolResponse(
        frames=[ErrorFrame(code="E_TEST", message="한글 메시지 — em dash 포함")],
        state_delta={},
        next_action="error",
    )
    decoded = agent_main._sse_bytes(response).decode("utf-8")
    assert "한글 메시지" in decoded
    assert "em dash" in decoded


def test_sse_bytes_handles_progress_frame():
    response = AgentProtocolResponse(
        frames=[AgentNodeFrame(agent_node_name="skills_builder.embed_skill_node")],
        state_delta={},
        next_action="continue",
    )
    decoded = agent_main._sse_bytes(response).decode("utf-8")
    assert "skills_builder.embed_skill_node" in decoded


# ======================================================================
# _done_frame_bytes — dual 종결 패턴 종료 시그널 (2026-05-14 결정)
# ======================================================================


def test_done_frame_bytes_emits_complete_terminator():
    """종료 시그널: frames=[], state_delta={}, next_action='complete'.

    dual 종결 패턴(2026-05-14)에서 모든 종결 path가 마지막 frame으로 발송하는
    contract. frontend는 이 frame을 받으면 스트림 종료로 간주.
    """
    raw = agent_main._done_frame_bytes()
    json_body = raw.decode("utf-8")[len("data: "):-len("\n\n")]
    parsed = json.loads(json_body)
    assert parsed["next_action"] == "complete"
    assert parsed["frames"] == []
    assert parsed["state_delta"] == {}


def test_done_frame_bytes_follows_sse_data_line_format():
    """SSE 포맷: 'data: <json>\\n\\n'."""
    raw = agent_main._done_frame_bytes().decode("utf-8")
    assert raw.startswith("data: ")
    assert raw.endswith("\n\n")


def test_done_frame_bytes_independent_of_business_payload():
    """매 호출이 동일한 종료 시그널을 발생시켜야 한다 (정상/에러 종결 무관).

    종료 시그널의 의미는 "스트림 끝"이므로 비즈니스 결과(성공/실패)와 분리되어야
    한다. ResultFrame/ErrorFrame은 결과 정보 전달용으로 _stream의 yield 흐름에서
    별도 처리. _done_frame_bytes는 항상 동일한 빈 종결 frame을 반환.
    """
    a = agent_main._done_frame_bytes()
    b = agent_main._done_frame_bytes()
    assert a == b


# ======================================================================
# AgentProtocolRequest payload 시그니처 — source_type별
# ======================================================================


def test_agent_protocol_request_industry_default_payload_valid():
    """main.py 분기: payload['industry_code']."""
    session_id, user_id = uuid4(), uuid4()
    req = AgentProtocolRequest(
        session_id=session_id,
        user_id=user_id,
        state=_make_agent_state(session_id, user_id),
        personal_memory=[],
        payload={"source_type": "industry_default", "industry_code": "ecommerce"},
    )
    assert req.payload["source_type"] == "industry_default"
    assert req.payload["industry_code"] == "ecommerce"


def test_agent_protocol_request_functional_domain_payload_valid():
    """main.py 분기: payload['domain_code']."""
    session_id, user_id = uuid4(), uuid4()
    req = AgentProtocolRequest(
        session_id=session_id,
        user_id=user_id,
        state=_make_agent_state(session_id, user_id),
        personal_memory=[],
        payload={"source_type": "functional_domain", "domain_code": "customer_support"},
    )
    assert req.payload["source_type"] == "functional_domain"
    assert req.payload["domain_code"] == "customer_support"


def test_agent_protocol_request_sop_payload_valid():
    """main.py 분기: payload['document'] + req.personal_memory."""
    session_id, user_id = uuid4(), uuid4()
    req = AgentProtocolRequest(
        session_id=session_id,
        user_id=user_id,
        state=_make_agent_state(session_id, user_id),
        personal_memory=[],
        payload={
            "source_type": "sop",
            "document": {
                "document_id": str(uuid4()),
                "blocks": [],
                "metadata": {},
            },
        },
    )
    assert req.payload["source_type"] == "sop"
    assert "document" in req.payload


# ======================================================================
# AgentProtocolResponse.next_action Literal 정합
# ======================================================================


@pytest.mark.parametrize("next_action", ["continue", "complete", "error"])
def test_agent_protocol_response_next_action_literal_values(next_action: str):
    response = AgentProtocolResponse(frames=[], state_delta={}, next_action=next_action)
    assert response.next_action == next_action


# ======================================================================
# Use case 시그니처 정합 — main.py route() 분기 호출과 정합
# ======================================================================


def test_build_from_industry_default_use_case_signature_compat():
    """main.py: use_case.execute(req.user_id, payload['industry_code'])."""
    from ai_agent.application.agents.skills_builder.build_from_industry_default_use_case import (
        BuildFromIndustryDefaultUseCase,
    )

    sig = inspect.signature(BuildFromIndustryDefaultUseCase.execute)
    params = list(sig.parameters.keys())
    assert params[:3] == ["self", "user_id", "industry_code"]


def test_build_from_functional_domain_use_case_signature_compat():
    """main.py: use_case.execute(req.user_id, payload['domain_code'])."""
    from ai_agent.application.agents.skills_builder.build_from_functional_domain_use_case import (
        BuildFromFunctionalDomainUseCase,
    )

    sig = inspect.signature(BuildFromFunctionalDomainUseCase.execute)
    params = list(sig.parameters.keys())
    assert params[:3] == ["self", "user_id", "domain_code"]


def test_build_from_sop_use_case_signature_compat():
    """main.py wizard 3단계(ADR-0020 Q8 + 옵션 1 2단계 분리) 호출 시그니처 정합:
    metadata: use_case.extract_metadata(req.user_id, document, req.personal_memory)
    detail:   use_case.extract_detail(req.user_id, document, meta, req.personal_memory)
    confirm:  use_case.confirm(req.user_id, skills)
    """
    from ai_agent.application.agents.skills_builder.build_from_sop_use_case import (
        BuildFromSOPUseCase,
    )

    metadata_params = list(inspect.signature(BuildFromSOPUseCase.extract_metadata).parameters.keys())
    assert metadata_params[:4] == ["self", "user_id", "document", "personal_memory"]

    detail_params = list(inspect.signature(BuildFromSOPUseCase.extract_detail).parameters.keys())
    assert detail_params[:5] == ["self", "user_id", "document", "meta", "personal_memory"]

    confirm_params = list(inspect.signature(BuildFromSOPUseCase.confirm).parameters.keys())
    assert confirm_params[:3] == ["self", "user_id", "skills"]
