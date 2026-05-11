"""Personalization — 컨텍스트 기반 관련 memory 검색.

TODO: 구현 — 햄햄(이가원)
Modal app: agent-personalization
참조: docs/specs/plan/sprint-3.md §2.5 Personalization Agent
"""
from __future__ import annotations


class RecallPersonalSkillsUseCase:
    """Workflow Composer가 prompt 작성 시 호출 — 관련 personal skill 검색.

    임베딩 유사도(BGE-M3) 또는 키워드 매칭 기반.
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 햄햄(이가원) — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
