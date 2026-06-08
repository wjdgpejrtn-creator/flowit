"""일회성 backfill — 기존 PUBLISHED 스킬을 Neo4j (:Skill)-[:BINDS]->(:Node)로 투영 (ADR-0026 Phase 2b).

라이브 publish 훅(PublishSkillUseCase → Neo4jSkillProjector)은 PR #401 활성화 이후 신규 게시분만
처리하므로, 활성화 이전에 이미 PUBLISHED된 스킬은 본 스크립트로 1회 backfill한다.

실행(cloud-sql-proxy 127.0.0.1:6544 + NEO4J_* env 필요):
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/backfill_skill_binds.py
"""
from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID

import asyncpg
from ai_agent.adapters.ontology.neo4j_skill_projector import Neo4jSkillProjector
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

_TABLES = {
    SkillScope.PERSONAL: "personal_skills",
    SkillScope.TEAM: "team_skills",
    SkillScope.COMPANY: "company_skills",
}


async def main() -> None:
    if not os.getenv("NEO4J_URI"):
        raise SystemExit("NEO4J_URI 미설정")

    conn = await asyncpg.connect(
        host="127.0.0.1",
        port=6544,
        user=os.environ["DB_USER"],
        password="",  # cloud-sql-proxy --auto-iam-authn 가 토큰 주입
        database=os.environ.get("DB_NAME", "workflow_automation"),
        ssl=False,
    )
    projector = Neo4jSkillProjector()
    total = 0
    try:
        for scope, table in _TABLES.items():
            rows = await conn.fetch(
                f"SELECT skill_id, staging_required_connections "
                f"FROM {table} WHERE lifecycle_state = 'published'"
            )
            print(f"[{table}] PUBLISHED {len(rows)}건")
            for r in rows:
                # staging_required_connections는 JSONB지만 asyncpg가 raw JSON 문자열로 반환 →
                # json.loads로 디코드(이중 인코딩/None/null 방어). 결과가 list가 아니면 빈 리스트.
                raw = r["staging_required_connections"]
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                required = [str(p) for p in parsed] if isinstance(parsed, list) else []
                await projector.project_skill(
                    skill_id=UUID(str(r["skill_id"])),
                    scope=scope,
                    required_connections=required,
                )
                total += 1
                print(f"  ✓ {scope.value} {r['skill_id']} (req_conn={required})")
    finally:
        await conn.close()

    print(f"[backfill] 총 {total}건 BINDS 투영 완료")


if __name__ == "__main__":
    asyncio.run(main())
