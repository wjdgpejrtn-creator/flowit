"""Personalization — 워크플로우 완료 후 사용자 memory 갱신.

TODO: 구현 — 햄햄(이가원)
Modal app: agent-personalization
참조: docs/specs/plan/sprint-3.md §2.5 Personalization Agent

NOTE: 기존 SaveMemoryUseCase 흡수 예정. 햄햄이 구현 시 SaveMemoryUseCase를
      이 UseCase의 단순 케이스로 변환하거나 폐기 결정.
"""
from __future__ import annotations


class UpdateUserMemoryUseCase:
    """LLM이 워크플로우 패턴 추출 → MEMORY.md 인덱스 + 개별 .md 갱신/생성.

    Claude Code memory.md 패턴:
        - frontmatter: name, description, type(user/feedback/project/reference)
        - 본문: 패턴 + Why + How to apply
    """

    def __init__(self) -> None:
        raise NotImplementedError("TODO: 햄햄(이가원) — Sprint 3 Phase A 구현")

    async def execute(self, *args, **kwargs):
        raise NotImplementedError
