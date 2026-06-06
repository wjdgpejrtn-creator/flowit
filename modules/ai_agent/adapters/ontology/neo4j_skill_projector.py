from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from skills_marketplace.domain.ports.skill_ontology_projector import SkillOntologyProjector
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

# 멱등 재게시를 위해 기존 BINDS를 먼저 제거(스킬의 required_connections 변경 시 stale edge 정리).
_RESET_BINDS = """
MERGE (s:Skill {id: $skill_id})
SET s.tier = $tier, s.audience = $tier
WITH s
OPTIONAL MATCH (s)-[b:BINDS]->()
DELETE b
"""

# 모델 A(ADR-0024 D2): 스킬은 LLM 노드에 주입되는 지침서 → ai 카테고리 노드에 BINDS.
_BIND_AI_NODES = """
MATCH (s:Skill {id: $skill_id})
MATCH (n:Node {category: 'ai'})
MERGE (s)-[:BINDS]->(n)
"""

# 역량 신호: 스킬이 요구하는 connection을 요구하는 노드에도 BINDS (skill-builder grounding용).
_BIND_CONNECTION_NODES = """
MATCH (s:Skill {id: $skill_id})
MATCH (n:Node)-[:REQUIRES]->(:Connection {provider: $provider})
MERGE (s)-[:BINDS]->(n)
"""


class Neo4jSkillProjector(SkillOntologyProjector):
    """SkillOntologyProjector 구현 — 게시 스킬을 Neo4j에 incremental upsert (ADR-0026 Phase 2b).

    `Neo4jOntologyAdapter`(읽기)와 동일하게 **요청마다 driver 생성·close** 한다 — Modal ASGI
    앱에서 driver를 `@modal.enter`에 1회 만들면 boot≠request 이벤트루프 미스매치로 hang하는
    사고(composer_modal_per_request_engine)를 피하기 위함. 연결 정보는 `NEO4J_URI` /
    `NEO4J_USERNAME` / `NEO4J_PASSWORD` 환경변수에서 읽는다(하드코딩 금지, GCP secret
    `neo4j-*` → Modal `load_secrets_to_env` 런타임 주입).

    skills_marketplace 도메인 포트를 구현하지만 Neo4j 호출 어댑터라 ai_agent가 보유한다
    (ADR-0013 EmbedderPort 예외 패턴). `ai_agent → skills_marketplace.domain.value_objects`
    교차 import는 CLAUDE.md 허용 범위.
    """

    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        driver_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._uri = uri or os.getenv("NEO4J_URI")
        self._username = username or os.getenv("NEO4J_USERNAME")
        self._password = password or os.getenv("NEO4J_PASSWORD")
        self._driver_factory = driver_factory

    def _new_driver(self) -> Any:
        if self._driver_factory is not None:
            return self._driver_factory()
        if not self._uri:
            raise RuntimeError(
                "NEO4J_URI 미설정 — neo4j-uri secret을 load_secrets_to_env로 주입 필요 (ADR-0026)"
            )
        from neo4j import AsyncGraphDatabase  # noqa: PLC0415 — neo4j는 선택 의존(extras), lazy import

        return AsyncGraphDatabase.driver(self._uri, auth=(self._username, self._password))

    async def project_skill(
        self,
        *,
        skill_id: UUID,
        scope: SkillScope,
        required_connections: Sequence[str] = (),
    ) -> None:
        providers = [p for p in dict.fromkeys(required_connections) if p]  # dedup + falsy 제거
        driver = self._new_driver()
        try:
            async with driver.session() as session:
                await session.run(_RESET_BINDS, skill_id=str(skill_id), tier=scope.value)
                await session.run(_BIND_AI_NODES, skill_id=str(skill_id))
                for provider in providers:
                    await session.run(
                        _BIND_CONNECTION_NODES, skill_id=str(skill_id), provider=provider
                    )
        finally:
            await driver.close()
