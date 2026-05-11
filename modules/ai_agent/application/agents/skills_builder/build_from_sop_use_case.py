"""Skills Builder — 회사 SOP 문서 → NodeDefinition 변환.

TODO: 구현 — 박아름
Modal app: agent-skills-builder
참조: docs/specs/plan/sprint-3.md §2 멀티 에이전트 구조
"""
from __future__ import annotations


class BuildFromSOPUseCase:
    """DocumentBlock(doc_parser 출력) → NodeDefinition 목록 변환.

    LLM으로 SOP 문서에서 단계별 작업을 추출해 nodes_graph 카탈로그에 등록.
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 박아름 — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
