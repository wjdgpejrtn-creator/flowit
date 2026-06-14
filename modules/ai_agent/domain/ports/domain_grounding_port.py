"""도메인 그라운딩 검색 포트 (ADR-0029) — skill builder 전용.

composer의 `OntologyRetrieverPort`와 **완전 별개**다(다른 라벨/쿼리/어댑터). skill builder
추출 use case가 이 포트만 사용하고 Neo4j에 직접 의존하지 않는다. 구현체
`Neo4jDomainGroundingAdapter`는 ai_agent가 소유한다(ADR-0013 EmbedderPort 예외 패턴 —
Neo4j 호출 어댑터는 호출 모듈 보유). 도메인 서브그래프(Domain/Playbook/Stage/Rule)만 질의한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.domain_grounding import DomainGroundingBundle


class DomainGroundingPort(ABC):
    """도메인(업종/직무) 그라운딩 묶음을 회수하는 검색 포트.

    skill builder 추출(SOP/인터뷰)이 이 묶음으로 프롬프트를 그라운딩한다 — 도메인 최적화
    프로세스(레일) + 단계별 주요 포인트 + LLM 지침(필수/금지/포커스)을 LLM에 주입해
    구조를 자유롭게 상상하지 않게 한다.
    """

    @abstractmethod
    async def get_domain_grounding(self, domain_code: str) -> DomainGroundingBundle | None:
        """도메인 코드로 그라운딩 묶음 회수. 미등록 도메인이면 None(추출은 그라운딩 없이 진행 가능).

        composer 라벨(:Node/:Skeleton/:Pattern)은 건드리지 않고 도메인 서브그래프
        (:Domain/:Playbook/:Stage/:Rule)만 MATCH한다.
        """
        ...
