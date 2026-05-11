"""Personalization — 세션 시작 시 사용자 memory 로드.

TODO: 구현 — 햄햄(이가원)
Modal app: agent-personalization
참조: docs/specs/plan/sprint-3.md §2.5 Personalization Agent
"""
from __future__ import annotations


class LoadUserMemoryUseCase:
    """GCS users/{user_id}/MEMORY.md 인덱스 + 관련 .md 파일 로드.

    Orchestrator가 세션 시작 시 호출, state에 주입.
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 햄햄(이가원) — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
