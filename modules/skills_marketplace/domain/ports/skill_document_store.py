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

    ai_agent(Skills Builder)의 **쓰기 경로**(스킬 생성)는 이 Port를 직접 import하지 않고
    skills_marketplace의 application/use_cases(후속 RegisterSkillUseCase 등)를 경유해 접근한다
    (조장 리뷰 #98). 구현체 DI 주입은 skills_marketplace use case 생성자에서 받는다.

    반면 ai_agent **Composer의 읽기 경로**는 ADR-0024 D5에서 이 Port를 직접 import해 런타임
    소비한다 — `composer_graph._drafter_node`가 선택된 게시 스킬의 COMPOSER.md
    (`composer_instructions`)를 `load()`해 drafter에 주입한다(#372 결함 A — drafter↔스킬 단절
    해소). Port ABC만 참조하고 구현체(GcsSkillDocumentStore)는 composition root에서 주입하므로
    execution_engine 런타임 주입 패턴과 동일하다. CLAUDE.md "modules 간 허용된 교차 import" 표의
    `ai_agent → skills_marketplace/domain/ports/SkillDocumentStore` 행 참조.

    GCS adapter 구현 위치 = `storage/adapters/`, 담당 = 조장 (2026-05-24 협의 — "스킬이 결국
    md 문서 저장이라 storage"). 기존 ObjectStoragePort(GCSAdapter/LocalStorageAdapter)를 조합한다.
    경로 패턴: `gs://{bucket}/skills/{skill_id}/SKILL.md`.
    """

    @abstractmethod
    async def save(self, skill_id: UUID, document: SkillDocument) -> str:
        """SkillDocument를 GCS에 SKILL.md(+scripts/templates)로 저장하고 저장 URI를 반환.

        반환: `gs://{bucket}/skills/{skill_id}/SKILL.md`. 호출부(skills_marketplace use case)가
        이 URI를 skill metadata의 `skill_document_uri`로 세팅한다. bucket은 어댑터(storage)만
        알기 때문에 URI는 어댑터가 반환한다 (호출부가 bucket을 알면 인프라 설정 누수 — 2026-05-24 결정).
        """
        ...

    @abstractmethod
    async def load(self, skill_id: UUID) -> SkillDocument | None:
        """skill_id의 SkillDocument 조회 (없으면 None)."""
        ...

    @abstractmethod
    async def delete(self, skill_id: UUID) -> None:
        """skill_id의 SkillDocument(SKILL.md) 삭제. 멱등 — 객체가 없으면 no-op.

        `DeletePersonalSkillUseCase`가 개인 스킬 삭제 시 GCS 잔여물(orphan)을 함께 정리하기 위해
        호출한다 (2026-05-26 조장 결정 — 삭제 시 GCS SKILL.md도 제거). 구현은 storage.
        """
        ...
