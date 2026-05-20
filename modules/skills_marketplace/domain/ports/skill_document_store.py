from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas import SkillDocument


class SkillDocumentStore(ABC):
    """스킬 지침서(SkillDocument markdown) GCS 저장소 인터페이스 (Port).

    한 스킬의 이중 저장 중 "지침서" 측 Port (메타는 SkillRepository).
    Port 정의는 skills_marketplace(도메인 소유)가 소유하고, GCS 구현체는 후속 PR에서
    제공한다 (2026-05-20 박아름 소유권 결정 — ADR-0017 정정. SkillRepository와 일관 +
    스킬 aggregate 완결).

    ai_agent(Skills Builder)는 이 Port를 직접 import하지 않고 skills_marketplace의
    application/use_cases(후속 RegisterSkillUseCase 등)를 경유해 접근한다 — CLAUDE.md
    "modules 간 허용된 교차 import" 표가 `ai_agent → skills_marketplace/application/use_cases`만
    등재하므로 domain/ports 직접 의존을 만들지 않기 위함 (조장 리뷰 #98). 구현체 DI 주입은
    skills_marketplace use case 생성자에서 받는다.

    NOTE: GCS adapter 구현 위치(storage/adapters vs skills_marketplace/adapters)는
    PR-2d/2e 후속 결정. 경로 패턴: `gs://{bucket}/skills/{skill_id}/SKILL.md`.
    """

    @abstractmethod
    async def save(self, skill_id: UUID, document: SkillDocument) -> None:
        """SkillDocument를 GCS에 SKILL.md(+scripts/templates)로 저장."""
        ...

    @abstractmethod
    async def load(self, skill_id: UUID) -> SkillDocument | None:
        """skill_id의 SkillDocument 조회 (없으면 None)."""
        ...
