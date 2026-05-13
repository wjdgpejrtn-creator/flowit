"""박아름 영역 DB seed — 노드 카탈로그 + Skills Builder baseline 등록.

5/13 박아름 점검 결과 node_definitions에 박아름 카탈로그 0건 + embedding
100% NULL 상태. 본 스크립트로 일괄 등록.

### 등록 내용

1. REQ-003 카탈로그 55종 (`catalog_registry.discover_and_register`)
   - 28 도메인 (trigger 6 + condition 8 + data 14)
   - 13 외부 어댑터 (Slack/Gmail/Google Drive/Sheets/Docs/PostgreSQL/MySQL/
     BigQuery/Anthropic/Calendar/Linear/HTTP/PDF)
   - 14 toolset 연결 (햄햄 commit `59f0e26`)
2. REQ-004 Skills Builder baseline 30 SkillNode (is_mvp=False)
   - 산업 활성 1종: ecommerce (5 SkillNode)
   - 직무 영역 5종: customer_support / it_ops / document_data / hr / marketing
     (각 5 SkillNode = 25)

모든 노드에 BGE-M3 768d embedding 자동 채움 (`ModalEmbeddingAdapter` 통해
llm-base Modal `/v1/embed_batch` 호출).

### 사용법

```powershell
# 사전 조건
gcloud auth application-default login
# 박아름 .env가 공용 SA로 갈아엎혀 있으면 박아름 로컬 ADC 사용 위해 임시 override:
$env:DB_IAM_USER = "<TEAM_MEMBER_1>@example.com"  # 박아름 개인 IAM user

# 영향 평가만 (실 등록 없음)
PYTHONUTF8=1 python scripts/bootstrap_node_definitions.py --dry-run

# 카탈로그만 등록
PYTHONUTF8=1 python scripts/bootstrap_node_definitions.py --catalog-only

# Skills Builder baseline만 등록
PYTHONUTF8=1 python scripts/bootstrap_node_definitions.py --skills-only

# 전체 등록 (default)
PYTHONUTF8=1 python scripts/bootstrap_node_definitions.py --all

# placeholder 54건 삭제 후 등록 (조장 합의 후 사용)
PYTHONUTF8=1 python scripts/bootstrap_node_definitions.py --all --cleanup-placeholder
```

### 환경 변수 (.env 또는 shell)

- CLOUD_SQL_INSTANCE
- DB_IAM_USER (박아름 개인 또는 공용 SA)
- DB_NAME
- EMBEDDING_BASE_URL (llm-base Modal)

### 합의 의존

조장 (placeholder 54 처리 방향) + 신정혜 (is_mvp 필터링 정책) 확인 후 실행.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import warnings
from pathlib import Path
from uuid import UUID

warnings.filterwarnings("ignore", category=UserWarning, module="google.auth")

# PYTHONPATH 보강 — 박아름 로컬에서 직접 실행 시 modules/ + packages/common_schemas/python 경로 추가.
_REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (
    _REPO_ROOT / "modules",
    _REPO_ROOT / "packages" / "common_schemas" / "python",
):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# .env 수동 로드 (python-dotenv 미사용 — 의존성 회피)
ENV_PATH = _REPO_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# placeholder seed의 node_type 패턴 (cleanup 시 사용)
PLACEHOLDER_PREFIXES = (
    "trigger_", "action_", "condition_", "transform_",
)
# 박아름 카탈로그 + Skills Builder는 다른 형식 사용:
#   - 카탈로그: schedule_trigger / json_extract / http_request 등 (suffix _trigger)
#   - SkillNode: ecommerce_* / customer_support_* / it_ops_* 등

SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")  # database/seeds/system_user.sql


async def _make_cloud_sql_resources():
    """Cloud SQL Connector + engine + session_factory 생성 (박아름 로컬)."""
    from google.cloud.sql.connector import Connector
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    loop = asyncio.get_running_loop()
    connector = Connector(loop=loop, refresh_strategy="lazy")

    async def _getconn():
        return await connector.connect_async(
            os.environ["CLOUD_SQL_INSTANCE"],
            "asyncpg",
            user=os.environ["DB_IAM_USER"],
            db=os.environ["DB_NAME"],
            enable_iam_auth=True,
        )

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=_getconn,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return connector, engine, session_factory


async def _print_db_state(session, label: str) -> None:
    from sqlalchemy import text

    total = await session.scalar(text("SELECT COUNT(*) FROM node_definitions"))
    with_emb = await session.scalar(
        text("SELECT COUNT(*) FROM node_definitions WHERE embedding IS NOT NULL")
    )
    print(f"  [{label}] node_definitions total={total}, embedding NOT NULL={with_emb}/{total}")


def _get_arum_node_type_set() -> set[str]:
    """박아름 카탈로그 55 + Skills Builder baseline 30 node_type set."""
    import json

    from nodes_graph.application.catalog_registry import get_all_node_definitions

    types: set[str] = set()
    # 1) 카탈로그 55종
    for n in get_all_node_definitions():
        types.add(n.node_type)

    # 2) Skills Builder baseline SkillNode 30종 (industry_defaults/ecommerce + functional 5)
    seeds_dir = _REPO_ROOT / "modules" / "ai_agent" / "seeds"
    for path in [
        seeds_dir / "industry_defaults" / "ecommerce.json",
        seeds_dir / "functional_domain_defaults" / "customer_support.json",
        seeds_dir / "functional_domain_defaults" / "it_ops.json",
        seeds_dir / "functional_domain_defaults" / "document_data.json",
        seeds_dir / "functional_domain_defaults" / "hr.json",
        seeds_dir / "functional_domain_defaults" / "marketing.json",
    ]:
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("skill_nodes", []):
            types.add(item["node_type"])

    return types


async def _cleanup_placeholder(session) -> int:
    """조장 5/13 합의: placeholder는 박아름 노드 따라간다 → 박아름 카탈로그+SkillNode 외 모두 삭제.

    박아름 카탈로그(55) + SkillNode(30) = 85 node_type set 밖의 row를 DELETE.
    """
    from sqlalchemy import text

    arum_types = _get_arum_node_type_set()
    print(f"  박아름 카탈로그+SkillNode node_type set: {len(arum_types)}건")

    # set 밖의 모든 row 조회
    rows = await session.execute(text("SELECT node_type FROM node_definitions"))
    db_types = [r[0] for r in rows.fetchall()]
    to_delete = [nt for nt in db_types if nt not in arum_types]
    print(f"  DB 현재 node_type: {len(db_types)}건, 삭제 대상: {len(to_delete)}건")

    deleted = 0
    for nt in to_delete:
        r = await session.execute(
            text("DELETE FROM node_definitions WHERE node_type = :nt"),
            {"nt": nt},
        )
        deleted += r.rowcount or 0

    return deleted


async def _register_catalog(session_factory, dry_run: bool) -> int:
    """REQ-003 카탈로그 55종 등록 (discover_and_register)."""
    from nodes_graph.adapters.catalog.registry import (
        discover_and_register,
        discover_node_definitions,
    )

    if dry_run:
        nodes = discover_node_definitions()
        print(f"  [dry-run] 카탈로그 discover: {len(nodes)}종")
        return len(nodes)

    from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
    from storage.repositories.pg_node_definition_repository import (
        PgNodeDefinitionRepository,
    )

    embedder = ModalEmbeddingAdapter()
    try:
        async with session_factory() as session:
            repo = PgNodeDefinitionRepository(session)
            count = await discover_and_register(repo, embedder)
            await session.commit()
            return count
    finally:
        await embedder.aclose()


async def _register_skills_baseline(session_factory, dry_run: bool) -> int:
    """REQ-004 Skills Builder baseline 30 SkillNode 등록.

    BuildFromIndustryDefault("ecommerce") + BuildFromFunctionalDomain × 5.
    """
    if dry_run:
        # 활성 산업 1 (5종) + functional 5종 (각 5종) = 30
        print(f"  [dry-run] Skills Builder baseline: 30 SkillNode (1 industry × 5 + 5 functional × 5)")
        return 30

    from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
    from ai_agent.application.agents.skills_builder.build_from_functional_domain_use_case import (
        BuildFromFunctionalDomainUseCase,
    )
    from ai_agent.application.agents.skills_builder.build_from_industry_default_use_case import (
        BuildFromIndustryDefaultUseCase,
    )
    from common_schemas.transport import ResultFrame
    from storage.repositories.pg_node_definition_repository import (
        PgNodeDefinitionRepository,
    )

    total_upserted = 0
    embedder = ModalEmbeddingAdapter()
    try:
        # 산업 활성 1종
        async with session_factory() as session:
            repo = PgNodeDefinitionRepository(session)
            uc = BuildFromIndustryDefaultUseCase(repo, embedder)
            async for frame in uc.execute(SYSTEM_USER_ID, "ecommerce"):
                if isinstance(frame, ResultFrame):
                    upserted = frame.payload.get("upserted_count", 0)
                    total_upserted += upserted
                    print(f"  [ecommerce] upserted={upserted}, failed={frame.payload.get('failed_count', 0)}")
            await session.commit()

        # 직무 영역 5종
        for domain_code in ("customer_support", "it_ops", "document_data", "hr", "marketing"):
            async with session_factory() as session:
                repo = PgNodeDefinitionRepository(session)
                uc = BuildFromFunctionalDomainUseCase(repo, embedder)
                async for frame in uc.execute(SYSTEM_USER_ID, domain_code):
                    if isinstance(frame, ResultFrame):
                        upserted = frame.payload.get("upserted_count", 0)
                        total_upserted += upserted
                        print(
                            f"  [{domain_code}] upserted={upserted}, "
                            f"failed={frame.payload.get('failed_count', 0)}"
                        )
                await session.commit()
    finally:
        await embedder.aclose()

    return total_upserted


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--catalog-only", action="store_true", help="REQ-003 카탈로그 55종만")
    group.add_argument("--skills-only", action="store_true", help="REQ-004 Skills Builder 30종만")
    group.add_argument("--all", action="store_true", help="카탈로그 + Skills Builder 모두 (default)")
    parser.add_argument("--dry-run", action="store_true", help="실 등록 없이 영향 평가만")
    parser.add_argument(
        "--cleanup-placeholder",
        action="store_true",
        help="기존 placeholder seed(database/seeds/node_definitions.json) 삭제 후 등록",
    )
    args = parser.parse_args()

    if not (args.catalog_only or args.skills_only or args.all):
        args.all = True

    # 환경변수 점검
    for key in ("CLOUD_SQL_INSTANCE", "DB_IAM_USER", "DB_NAME", "EMBEDDING_BASE_URL"):
        if not os.environ.get(key):
            print(f"[FAIL] 환경변수 누락: {key}")
            return 1

    print(f"  CLOUD_SQL_INSTANCE: {os.environ['CLOUD_SQL_INSTANCE']}")
    print(f"  DB_IAM_USER       : {os.environ['DB_IAM_USER']}")
    print(f"  DB_NAME           : {os.environ['DB_NAME']}")
    print(f"  EMBEDDING_BASE_URL: {os.environ['EMBEDDING_BASE_URL'][:50]}...")
    print(f"  mode              : {'dry-run' if args.dry_run else 'live'} / "
          f"{'catalog' if args.catalog_only else ('skills' if args.skills_only else 'all')} / "
          f"cleanup={args.cleanup_placeholder}")
    print()

    connector, engine, session_factory = await _make_cloud_sql_resources()

    try:
        async with session_factory() as session:
            await _print_db_state(session, "BEFORE")
        print()

        # 1) placeholder cleanup (조장 합의 후)
        if args.cleanup_placeholder:
            if args.dry_run:
                print("  [dry-run] placeholder 54건 삭제 예정 (database/seeds/node_definitions.json)")
            else:
                async with session_factory() as session:
                    deleted = await _cleanup_placeholder(session)
                    await session.commit()
                    print(f"  [cleanup] placeholder 삭제: {deleted}건")
            print()

        # 2) 카탈로그 등록
        if args.catalog_only or args.all:
            print("[A] REQ-003 카탈로그 55종 등록...")
            count = await _register_catalog(session_factory, args.dry_run)
            print(f"  → {'(dry-run) ' if args.dry_run else ''}완료: {count}종")
            print()

        # 3) Skills Builder baseline 등록
        if args.skills_only or args.all:
            print("[B] REQ-004 Skills Builder baseline 30 SkillNode 등록...")
            count = await _register_skills_baseline(session_factory, args.dry_run)
            print(f"  → {'(dry-run) ' if args.dry_run else ''}완료: {count}종")
            print()

        # 4) 검증
        async with session_factory() as session:
            await _print_db_state(session, "AFTER")

    finally:
        await engine.dispose()
        await connector.close_async()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
