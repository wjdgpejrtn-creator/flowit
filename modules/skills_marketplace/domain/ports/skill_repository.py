from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.approval_workflow import ApprovalWorkflow
from ..entities.marketplace_company_skill import MarketplaceCompanySkill
from ..entities.marketplace_personal_skill import MarketplacePersonalSkill
from ..entities.marketplace_team_skill import MarketplaceTeamSkill
from ..value_objects.skill_scope import SkillScope
from ..value_objects.skill_state import SkillState


class SkillRepository(ABC):
    """Skills Marketplace 3계층 스킬 저장소 인터페이스 (Port).

    Port 정의는 skills_marketplace(소비 모듈)가 소유하고, 구현체는 `storage/repositories/`가
    제공한다 (auth/nodes_graph 일반 패턴 정합 — ADR-0017 + 5/20 박아름·조장 합의).
    CLAUDE.md L146(storage 소유)은 본 결정으로 정정됨.

    NOTE: 메서드 시그니처는 깊이 1(뼈대) 기준. 실제 쿼리/제약은 PR-2d 구현 + PR-2e DDL 시 확정.
    하이브리드 검색(`search`)은 BGE-M3 embedding 코사인 유사도 + 키워드(TSVECTOR) 결합 예정.
    """

    @abstractmethod
    async def save_personal(self, skill: MarketplacePersonalSkill) -> MarketplacePersonalSkill:
        """개인 스킬 생성/갱신 (upsert)."""
        ...

    @abstractmethod
    async def save_team(self, skill: MarketplaceTeamSkill) -> MarketplaceTeamSkill:
        """팀 스킬 생성/갱신 (승격 결과 저장)."""
        ...

    @abstractmethod
    async def save_company(self, skill: MarketplaceCompanySkill) -> MarketplaceCompanySkill:
        """전사 스킬 생성/갱신 (승격 결과 저장)."""
        ...

    @abstractmethod
    async def get_personal(self, skill_id: UUID) -> MarketplacePersonalSkill | None:
        """개인 스킬 단일 조회."""
        ...

    @abstractmethod
    async def get_team(self, skill_id: UUID) -> MarketplaceTeamSkill | None:
        """팀 스킬 단일 조회."""
        ...

    @abstractmethod
    async def get_company(self, skill_id: UUID) -> MarketplaceCompanySkill | None:
        """전사 스킬 단일 조회."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        scope: SkillScope,
        limit: int = 10,
        include_promoted: bool = False,
        lifecycle_state: SkillState | None = None,
    ) -> list[MarketplacePersonalSkill | MarketplaceTeamSkill | MarketplaceCompanySkill]:
        """하이브리드 검색 — scope 범위 내 embedding 유사도 top-k.

        ai_agent Workflow Composer가 사용자 의도(intent)와 유사한 스킬 후보를 옵션 제시할 때 호출
        (CLAUDE.md L148, ADR-0017 §Composer 검색 흐름).

        include_promoted=False(기본): 상위 scope로 승격 완료된 원본(`promoted_to_*` 존재)은
        검색 결과에서 제외 — 같은 스킬이 personal+team 중복 노출되는 것을 방지 (승격=복제 정책,
        조장 리뷰 #98). 실제 WHERE 필터(`promoted_to_* IS NULL`)는 storage 구현 시 적용.

        lifecycle_state(ADR-0020 (b)): 지정 시 해당 게시 상태만 반환(예: PUBLISHED). None이면
        전체 상태. Composer 노드 후보 검색은 PUBLISHED만 보도록 SearchSkillsUseCase가 PUBLISHED를
        전달한다(미검토 DRAFT/REVIEW 오염 방지). 실제 WHERE 필터는 storage 구현 시 적용.
        """
        ...

    @abstractmethod
    async def list_by_scope(
        self,
        scope: SkillScope,
        lifecycle_state: SkillState | None = SkillState.PUBLISHED,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplaceTeamSkill | MarketplaceCompanySkill]:
        """마켓플레이스 탐색(browse) 목록 — scope(team/company) 게시 스킬을 쿼리 없이 나열.

        `search`(embedding 코사인 유사도)와 별개. 마켓플레이스 UI의 Team/Company 탭은 검색어
        없이 게시된 스킬 전체를 최신순으로 보여주므로 embedding이 필요 없다 — 본 메서드가 그 경로.

        scope=PERSONAL은 본 메서드 대상 아님(개인 스킬은 owner 범위라 `list_personal_by_user`
        사용) — 구현체는 PERSONAL이 오면 ValueError를 던진다.

        lifecycle_state 기본 PUBLISHED(ADR-0020 (b)): 미검토 DRAFT/REVIEW를 마켓플레이스에 노출하지
        않는다. None이면 전체 상태(관리/디버그).

        승격 완료 원본(team의 `promoted_to_company_id` 존재)은 제외 — 승격=복제이므로 상위 scope에
        같은 스킬이 이미 존재해 중복 노출 방지(`search`의 include_promoted=False 정책과 동일).
        company는 최상위라 승격 마킹 컬럼이 없어 해당 필터 없음. 정렬은 구현에서 `updated_at DESC`.
        """
        ...

    @abstractmethod
    async def save_approval(self, approval: ApprovalWorkflow) -> ApprovalWorkflow:
        """게시 승인 워크플로우 레코드 저장 (ADR-0020 + 감사 추적).

        `ApproveSkillUseCase`가 REVIEW→APPROVED/DRAFT 전이 시 reviewer_id/status/comment를
        레코드로 남긴다. 저장 대상 = skill_approvals 테이블(PR-2e DDL). 구현은 storage.
        """
        ...

    # ── personal 미리보기/편집 UI 지원 (REQ-013, 가원 요청) ──────────────────────
    # 구현은 storage(PgMarketplaceSkillRepository, 조장). 인가/lifecycle 제약은 use case에서.

    @abstractmethod
    async def list_personal_by_user(
        self,
        user_id: UUID,
        lifecycle_state: SkillState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplacePersonalSkill]:
        """소유자(owner_user_id)의 개인 스킬 목록 — 미리보기 UI용.

        `lifecycle_state` 지정 시 해당 게시 상태만(예: DRAFT). None이면 전체.
        `limit`/`offset` 페이지네이션. 정렬은 구현(storage)에서 `updated_at DESC` 권장.
        승격 완료분(`promoted_to_team_id`) 포함 여부는 소유자 본인 목록이므로 필터하지 않는다.
        """
        ...

    @abstractmethod
    async def list_personal_by_state(
        self,
        lifecycle_state: SkillState,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplacePersonalSkill]:
        """게시 상태별 **전체 소유자**의 개인 스킬 목록 — 관리자 리뷰 큐용 (REQ-013).

        `list_personal_by_user`(소유자 범위)와 달리 owner 필터가 없다 — 관리자가 REVIEW 상태의
        리뷰 요청을 소유자 무관하게 모아 보기 위함. 인가(Admin only)는 use case
        (`ListReviewQueueUseCase`)가 enforce한다. 정렬은 구현(storage)에서 `updated_at DESC`.
        """
        ...

    @abstractmethod
    async def delete_personal(self, skill_id: UUID) -> None:
        """개인 스킬 단건 삭제 (DB row). GCS SkillDocument 삭제는 use case가 `SkillDocumentStore`로 별도 수행.

        존재하지 않는 skill_id면 no-op(멱등) — storage 계층의 방어적 속성(재시도/경합 안전).
        다만 정상 흐름에선 `DeletePersonalSkillUseCase`가 `get_personal`로 선검증 후 미존재 시
        `NotFoundError`를 먼저 던지므로, 이 메서드에 미존재 skill_id가 도달하지는 않는다.
        인가/lifecycle 검증도 use case에서 선행.
        """
        ...
