"""Main Orchestrator — sub-agent 라우팅 use case.

TODO: 구현 — 신정혜
Modal app: orchestrator
참조: docs/specs/plan/sprint-3.md §2 멀티 에이전트 구조
"""
from __future__ import annotations


class RouteRequestUseCase:
    """LangGraph supervisor 패턴으로 sub-agent를 라우팅하는 main orchestrator.

    흐름:
        세션 시작 → personal_memory 로드 → intent 분류 →
        sub-agent 라우팅 (workflow_composer / skills_builder) →
        결과 통합 → SSE 스트림 yield
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 신정혜 — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
