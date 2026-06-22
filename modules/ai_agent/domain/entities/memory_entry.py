"""MemoryEntry는 common_schemas의 SSOT를 재노출만 한다.

REQ-004 spec §1: ``from common_schemas import MemoryEntry``가 정식 경로.
ai_agent.domain.entities 경로는 기존 코드 호환성을 위해 유지하지만 신규 코드는
common_schemas에서 직접 import할 것.
"""
from __future__ import annotations

from common_schemas import MemoryEntry, MemoryType

__all__ = ["MemoryEntry", "MemoryType"]
