"""Skills Builder — 산업 표준 default → NodeDefinition 로드.

TODO: 구현 — 박아름
Modal app: agent-skills-builder
참조: docs/specs/plan/sprint-3.md §2 멀티 에이전트 구조
"""
from __future__ import annotations


class BuildFromIndustryDefaultUseCase:
    """IndustryCode(제조/서비스/도소매/음식점/IT) → seed에서 NodeDefinition 로드.

    Sprint 3 v1: seed 5개 산업 하드코딩.
    v2: LLM 자유 생성.
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 박아름 — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
