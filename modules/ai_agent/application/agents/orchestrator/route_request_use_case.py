"""Main Orchestrator — sub-agent 라우팅 use case.

TODO: 구현 — 신정혜
Modal app: orchestrator
참조: docs/specs/plan/sprint-3.md §2 멀티 에이전트 구조
"""
from __future__ import annotations


class RouteRequestUseCase:
    """LangGraph supervisor 패턴으로 sub-agent를 라우팅하는 main orchestrator.

    흐름 (spec §3.1 supervisor diagram):
        세션 시작
          → load_memory_node      (HTTP → agent-personalization: LoadUserMemoryUseCase)
          → intent_node           (IntentAnalyzerService)
          → 분기:
              intent=draft/refine/clarify → composer_node       (HTTP → agent-composer)
              intent=build_skill          → skills_node          (HTTP → agent-skills-builder)
              intent=propose              → finalize_node
          → update_memory_node    (HTTP → agent-personalization: UpdateUserMemoryUseCase, 완료 후)
          → SSE 통합 yield
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 신정혜 — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
