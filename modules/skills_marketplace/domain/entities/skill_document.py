"""SkillDocument — common_schemas SSOT 재노출 shim (ADR-0017 / PR #106·#111 리뷰).

SkillDocument는 ai_agent(생산) + skills_marketplace(저장) 양쪽이 쓰는 공유 타입이라
common_schemas로 SSOT 이동(PR #111). 본 모듈은 하위호환 재노출 shim — 기존
`from skills_marketplace.domain.entities import SkillDocument` import 경로를 유지한다.
신규 코드는 `from common_schemas import SkillDocument` 직접 import 권장.
"""
from __future__ import annotations

from common_schemas import SkillDocument

__all__ = ["SkillDocument"]
