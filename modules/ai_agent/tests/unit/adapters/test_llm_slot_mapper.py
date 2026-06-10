"""LlmSlotMapper 단위테스트 (ADR-0026 §6.6 Phase 2 — 앙상블 LLM voter).

Gemma 호출은 LLMPort mock으로 대체 — 풀 가드/환각 폐기/실패 graceful degrade를 검증.
"""
from __future__ import annotations

import pytest

from ai_agent.adapters.llm.llm_slot_mapper import LlmSlotMapper, _SlotMapResponse, _SlotPick
from ai_agent.domain.value_objects.skeleton import SlotRole


class _StubLLM:
    def __init__(self, resp) -> None:
        self._resp = resp
        self.prompt: str | None = None

    async def generate_structured(self, prompt, schema, max_tokens=None):
        self.prompt = prompt
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


@pytest.mark.asyncio
async def test_maps_role_to_node_within_pool() -> None:
    resp = _SlotMapResponse(slots=[_SlotPick(role="source", node_type="gmail_read", confidence=0.9)])
    out = await LlmSlotMapper(_StubLLM(resp)).map_slots(
        "내 gmail에서 읽어서", {SlotRole.SOURCE: ("gmail_read", "google_sheets_read")}
    )
    assert out == {SlotRole.SOURCE: (("gmail_read", 0.9),)}


@pytest.mark.asyncio
async def test_discards_pick_outside_pool() -> None:
    # 풀 밖 node_type(환각)은 폐기.
    resp = _SlotMapResponse(slots=[_SlotPick(role="source", node_type="nonexistent", confidence=1.0)])
    out = await LlmSlotMapper(_StubLLM(resp)).map_slots("x", {SlotRole.SOURCE: ("gmail_read",)})
    assert out == {}


@pytest.mark.asyncio
async def test_unknown_role_ignored() -> None:
    # 요청 안 한 역할(transform)은 무시 — escalation은 준 역할만.
    resp = _SlotMapResponse(slots=[_SlotPick(role="transform", node_type="anthropic_chat", confidence=1.0)])
    out = await LlmSlotMapper(_StubLLM(resp)).map_slots("x", {SlotRole.SOURCE: ("gmail_read",)})
    assert out == {}


@pytest.mark.asyncio
async def test_llm_failure_returns_empty() -> None:
    # Gemma 호출 실패 = 비치명적 → 빈 매핑(싼 voter 결과가 선다).
    out = await LlmSlotMapper(_StubLLM(RuntimeError("boom"))).map_slots(
        "x", {SlotRole.SOURCE: ("gmail_read",)}
    )
    assert out == {}


@pytest.mark.asyncio
async def test_empty_roles_short_circuits_without_llm_call() -> None:
    stub = _StubLLM(_SlotMapResponse(slots=[]))
    out = await LlmSlotMapper(stub).map_slots("x", {})
    assert out == {}
    assert stub.prompt is None  # 확신 못 한 역할 없음 → LLM 미호출


@pytest.mark.asyncio
async def test_confidence_clamped_to_unit_interval() -> None:
    resp = _SlotMapResponse(slots=[_SlotPick(role="sink", node_type="gmail_send", confidence=1.5)])
    out = await LlmSlotMapper(_StubLLM(resp)).map_slots("x", {SlotRole.SINK: ("gmail_send",)})
    assert out == {SlotRole.SINK: (("gmail_send", 1.0),)}


@pytest.mark.asyncio
async def test_multiple_roles_grouped_and_sorted_by_confidence() -> None:
    resp = _SlotMapResponse(slots=[
        _SlotPick(role="sink", node_type="pdf_generate", confidence=0.6),
        _SlotPick(role="source", node_type="gmail_read", confidence=0.95),
        _SlotPick(role="sink", node_type="gmail_send", confidence=0.8),
    ])
    out = await LlmSlotMapper(_StubLLM(resp)).map_slots(
        "내 gmail에서 모아서 pdf로 gmail로",
        {SlotRole.SOURCE: ("gmail_read",), SlotRole.SINK: ("pdf_generate", "gmail_send")},
    )
    assert out[SlotRole.SOURCE] == (("gmail_read", 0.95),)
    # 같은 역할 복수 픽은 confidence 내림차순.
    assert out[SlotRole.SINK] == (("gmail_send", 0.8), ("pdf_generate", 0.6))
