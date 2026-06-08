"""박아름 영역 DB 백필 — company_skills 임베딩 backfill (ADR-0024 Follow-up).

## 배경

PR #343(`database/schemas/025_company_skills_seed.sql`)이 ecommerce 워크플로우 5종을
`company_skills`에 SQL INSERT로 등록하면서 `embedding` 컬럼을 채우지 않았다(BGE-M3
임베딩은 순수 SQL로 계산 불가). 그 결과:

  - `company_skills.embedding = NULL`
  - HNSW 인덱스 `idx_company_skills_embedding ... WHERE embedding IS NOT NULL` 제외
  - `PgMarketplaceSkillRepository.search`가 `where(embedding.isnot(None))`로 NULL 제외
  → Composer가 이 seed 스킬을 **검색으로 발견하지 못함**(마켓 목록엔 보이지만 워크플로우
    생성 파이프라인에서 단절). ADR-0024 D2 #5 명시된 backfill 작업.

## 동작

`company_skills` 중 `embedding IS NULL`인 row를 찾아 **`description`을 BGE-M3로 임베딩**해
채운다. 임베딩 텍스트로 `description`을 쓰는 이유 = Skills Builder `confirm`이
`embedder.embed(description)`으로 스킬을 임베딩하므로(코퍼스 일관성), seed도 동일 기준으로
임베딩해야 검색 랭킹이 공정하다. 멱등 — 이미 채워진 row는 건드리지 않는다.

## 사용법

```powershell
# 사전 조건
gcloud auth application-default login
# 박아름 .env가 공용 SA로 갈아엎혀 있으면 로컬 ADC 사용 위해 임시 override:
$env:DB_IAM_USER = "<TEAM_MEMBER_1>@example.com"  # 박아름 개인 IAM user

# 영향 평가만 (실 write 없음 — NULL 대상 목록만 출력)
PYTHONUTF8=1 python scripts/backfill_company_skill_embeddings.py --dry-run

# 실 backfill
PYTHONUTF8=1 python scripts/backfill_company_skill_embeddings.py
```

## 환경 변수 (.env 또는 shell)

- CLOUD_SQL_INSTANCE
- DB_IAM_USER (박아름 개인 또는 공용 SA)
- DB_NAME
- EMBEDDING_BASE_URL (llm-base Modal `/v1/embed_batch`)

## 안전 / 협의

`company_skills`(skills_marketplace 테이블)의 `embedding` 컬럼만 갱신 — NULL → 벡터로 채우는
비파괴 변경(기존 데이터 덮어쓰기 없음, 멱등). 공유 DB write이므로 [[feedback_db_safety]]에 따라
조장 협의 후 박아름이 실행. bootstrap_node_definitions.py와 동일 운영 절차.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import warnings
from pathlib import Path

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


async def _make_cloud_sql_resources():
    """Cloud SQL Connector + engine + session_factory 생성 (박아름 로컬). bootstrap과 동일 패턴."""
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


async def _make_embedder():
    """ModalEmbeddingAdapter — BGE-M3 GPU cold start 대응 timeout 180s (bootstrap과 동일).

    신정혜 영역 ModalEmbeddingAdapter default timeout 30s인데 BGE-M3 cold start가 45s+라
    박아름 운영 스크립트에서 client만 교체. 영구 수정은 신정혜 후속 PR.
    """
    import httpx
    from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter

    embedder = ModalEmbeddingAdapter()
    await embedder._client.aclose()
    embedder._client = httpx.AsyncClient(timeout=180.0)
    return embedder


async def _print_state(session, label: str) -> None:
    from sqlalchemy import text

    total = await session.scalar(text("SELECT COUNT(*) FROM company_skills"))
    with_emb = await session.scalar(
        text("SELECT COUNT(*) FROM company_skills WHERE embedding IS NOT NULL")
    )
    print(f"  [{label}] company_skills total={total}, embedding NOT NULL={with_emb}/{total}")


async def _backfill(session_factory, embedder, dry_run: bool) -> int:
    """embedding IS NULL인 company_skills를 description 임베딩으로 채운다.

    Returns: 처리(대상) row 수. dry-run이면 대상만 출력하고 write 없음.
    """
    from sqlalchemy import select
    from storage.orm.marketplace_skill_model import CompanySkillModel

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(CompanySkillModel).where(CompanySkillModel.embedding.is_(None))
            )
        ).scalars().all()

        print(f"  embedding NULL company_skills: {len(rows)}건")
        for r in rows:
            print(f"    - {r.skill_id} {r.name}")

        if not rows:
            return 0
        if dry_run:
            print("  [dry-run] write 없음 — 위 대상에 description 임베딩 채울 예정")
            return len(rows)

        # 빌더 confirm과 동일하게 description을 임베딩 (코퍼스 일관성)
        descriptions = [r.description for r in rows]
        vectors = await embedder.embed_batch(descriptions)
        for r, vec in zip(rows, vectors, strict=True):
            r.embedding = vec
        await session.commit()
        print(f"  [backfill] embedding 채움: {len(rows)}건")
        return len(rows)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="실 write 없이 NULL 대상 목록만 출력")
    args = parser.parse_args()

    # 환경변수 점검 (dry-run은 embedder 불필요라 EMBEDDING_BASE_URL 제외)
    required = ["CLOUD_SQL_INSTANCE", "DB_IAM_USER", "DB_NAME"]
    if not args.dry_run:
        required.append("EMBEDDING_BASE_URL")
    for key in required:
        if not os.environ.get(key):
            print(f"[FAIL] 환경변수 누락: {key}")
            return 1

    print(f"  CLOUD_SQL_INSTANCE: {os.environ['CLOUD_SQL_INSTANCE']}")
    print(f"  DB_IAM_USER       : {os.environ['DB_IAM_USER']}")
    print(f"  DB_NAME           : {os.environ['DB_NAME']}")
    print(f"  mode              : {'dry-run' if args.dry_run else 'live'}")
    print()

    connector, engine, session_factory = await _make_cloud_sql_resources()
    embedder = None
    try:
        async with session_factory() as session:
            await _print_state(session, "BEFORE")
        print()

        if not args.dry_run:
            embedder = await _make_embedder()
        count = await _backfill(session_factory, embedder, args.dry_run)
        print(f"  → {'(dry-run) ' if args.dry_run else ''}대상 {count}건")
        print()

        async with session_factory() as session:
            await _print_state(session, "AFTER")
    finally:
        if embedder is not None:
            await embedder.aclose()
        await engine.dispose()
        await connector.close_async()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
