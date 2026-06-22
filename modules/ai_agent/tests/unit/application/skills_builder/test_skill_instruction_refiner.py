"""SkillInstructionRefiner 단위 테스트 — SKILL.md draft→critique→refine 품질 루프.

Gemma 1샷 초안을 같은 모델에게 루브릭으로 자기 채점·재작성시켜 끌어올린다. 어느 단계든
실패/형태불일치면 초안 그대로 반환(graceful) — 추출 자체를 깨지 않는다.
"""
from __future__ import annotations

from typing import Any

import pytest

from ai_agent.application.agents.skills_builder.skill_instruction_refiner import (
    SkillInstructionRefiner,
    _RefinedInstructions,
    build_critique_prompt,
    build_refine_prompt,
)
from ai_agent.domain.ports.llm_port import LLMPort

_DRAFT = "## When to use\n환불 시.\n## Steps\n1. 알림"  # 얕은 3섹션 초안
_REFINED = (
    "# 환불 알림\n## 목적\n...\n## 언제 사용하나\n...\n## 사전 조건\n...\n"
    "## 처리 절차\n1. 확인한다\n## 판단 규칙\n50000원 초과 시 승인\n"
    "## 입력/출력\n...\n## 예시\n정상/엣지\n## 제약·주의\nPII 금지"
)


class _ScriptedLLM(LLMPort):
    """generate(critique)와 generate_structured(refine)를 각각 스크립트해 반환."""

    def __init__(
        self,
        *,
        critique: str | Exception = "1. 섹션 누락 — 9섹션으로 보강하라",
        refined: Any = None,
        structured_raise: Exception | None = None,
    ) -> None:
        self._critique = critique
        self._refined = refined if refined is not None else _RefinedInstructions(instructions=_REFINED)
        self._structured_raise = structured_raise
        self.generate_calls: list[str] = []
        self.structured_calls: list[str] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.generate_calls.append(prompt)
        if isinstance(self._critique, Exception):
            raise self._critique
        return self._critique

    async def generate_structured(self, prompt: str, schema: type, max_tokens: int | None = None) -> Any:
        self.structured_calls.append(prompt)
        if self._structured_raise:
            raise self._structured_raise
        return self._refined


@pytest.mark.asyncio
async def test_refine_returns_rewritten_instructions():
    llm = _ScriptedLLM()
    refiner = SkillInstructionRefiner(llm)

    out = await refiner.refine("환불 알림", _DRAFT)

    assert out == _REFINED
    # critique → refine 2패스 모두 호출
    assert len(llm.generate_calls) == 1
    assert len(llm.structured_calls) == 1
    # critique 프롬프트에 초안과 루브릭이 실렸다
    assert _DRAFT in llm.generate_calls[0]
    # refine 프롬프트에 초안 + 비평이 실렸다
    assert _DRAFT in llm.structured_calls[0]
    assert "섹션 누락" in llm.structured_calls[0]


@pytest.mark.asyncio
async def test_empty_draft_returns_as_is_without_llm():
    llm = _ScriptedLLM()
    refiner = SkillInstructionRefiner(llm)

    assert await refiner.refine("x", "") == ""
    assert await refiner.refine("x", "   ") == "   "
    assert llm.generate_calls == []  # 빈 초안은 LLM 미호출


@pytest.mark.asyncio
async def test_critique_failure_falls_back_to_draft():
    llm = _ScriptedLLM(critique=RuntimeError("modal timeout"))
    refiner = SkillInstructionRefiner(llm)

    out = await refiner.refine("환불 알림", _DRAFT)

    assert out == _DRAFT  # 비평 실패 → 초안 유지
    assert llm.structured_calls == []  # refine 미진입


@pytest.mark.asyncio
async def test_empty_critique_falls_back_to_draft():
    llm = _ScriptedLLM(critique="   ")
    refiner = SkillInstructionRefiner(llm)

    assert await refiner.refine("환불 알림", _DRAFT) == _DRAFT
    assert llm.structured_calls == []


@pytest.mark.asyncio
async def test_refine_failure_falls_back_to_draft():
    llm = _ScriptedLLM(structured_raise=RuntimeError("refine boom"))
    refiner = SkillInstructionRefiner(llm)

    assert await refiner.refine("환불 알림", _DRAFT) == _DRAFT


@pytest.mark.asyncio
async def test_refine_wrong_shape_falls_back_to_draft():
    # generate_structured가 _RefinedInstructions 아닌 형태 반환 → 초안 폴백
    llm = _ScriptedLLM(refined={"not": "a model"})
    refiner = SkillInstructionRefiner(llm)

    assert await refiner.refine("환불 알림", _DRAFT) == _DRAFT


@pytest.mark.asyncio
async def test_refine_empty_instructions_falls_back_to_draft():
    llm = _ScriptedLLM(refined=_RefinedInstructions(instructions="   "))
    refiner = SkillInstructionRefiner(llm)

    assert await refiner.refine("환불 알림", _DRAFT) == _DRAFT


def test_prompt_builders_carry_rubric_and_structure():
    crit = build_critique_prompt("환불 알림", _DRAFT)
    # 9개 루브릭 + 초안이 채점 프롬프트에 있다
    assert "채점" in crit and "환각" in crit and _DRAFT in crit
    # 데이터 소스/획득 루브릭(9번째 축)이 채점 기준에 포함된다
    assert "데이터 소스" in crit
    ref = build_refine_prompt("환불 알림", _DRAFT, "섹션 보강")
    # 9섹션 구조 + 비평 + JSON 출력 지시
    assert "## 처리 절차" in ref and "## 판단 규칙" in ref
    assert "섹션 보강" in ref and "JSON" in ref
    # 데이터 소스 명시 + 1단계 데이터 획득 요구가 구조/원칙에 들어간다
    assert "데이터 소스" in ref and "데이터 획득" in ref
