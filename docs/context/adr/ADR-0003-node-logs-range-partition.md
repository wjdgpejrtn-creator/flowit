# ADR-0003: node_logs RANGE 파티션 (월별) + 자동 생성 스크립트

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: @dhwang0803-glitch (REQ-001)
- **Tags**: area/database, layer/infrastructure

## Context

워크플로우 실행 엔진(REQ-007)은 각 노드 실행마다 로그를 `node_logs` 테이블에 기록한다. 이 테이블은 프로덕션에서 가장 높은 INSERT 빈도를 가지며, 시간 기반 조회(최근 N일 로그, 기간별 통계)가 주요 쿼리 패턴이다.

단일 테이블로 운영 시:
- 수백만 행 이후 INSERT 성능 저하
- 시간 범위 쿼리에서 전체 테이블 스캔
- VACUUM 부하 증가
- 오래된 데이터 정리(DROP) 어려움

## Decision

**`node_logs` 테이블을 `started_at` 컬럼 기준 RANGE 파티션(월별)으로 구성하고, `create_partition.py` 스크립트로 파티션을 자동 생성한다.**

### 테이블 구조

```sql
CREATE TABLE node_logs (
    id            UUID NOT NULL DEFAULT gen_random_uuid(),
    execution_id  UUID NOT NULL,
    node_id       VARCHAR(100) NOT NULL,
    ...
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, started_at)
) PARTITION BY RANGE (started_at);
```

### 파티션 명명 규칙

`node_logs_{YYYY}_{MM}` (예: `node_logs_2026_05`)

### 자동 생성 스크립트

`database/scripts/create_partition.py` — 향후 N개월 파티션을 CREATE IF NOT EXISTS로 생성. cron 또는 Cloud Scheduler에서 월 1회 실행.

```bash
DATABASE_URL=postgresql+asyncpg://... python -m database.scripts.create_partition --months 3
```

### Default 파티션

`node_logs_default` — 정의된 범위 외의 행을 수용하여 INSERT 실패를 방지.

## Consequences

### Positive

- 시간 범위 쿼리 시 partition pruning으로 월별 파티션만 스캔
- 오래된 데이터 정리: `DROP TABLE node_logs_2026_01` 한 줄로 완료 (DELETE + VACUUM 불필요)
- 각 파티션의 인덱스 크기가 작아 INSERT 성능 유지
- VACUUM이 파티션 단위로 동작하여 부하 분산

### Negative / Trade-offs

- Primary Key에 `started_at` 포함 필수 (파티션 키가 PK에 포함되어야 함)
- 월별 파티션 미생성 시 default 파티션에 축적 → 정기 스크립트 실행 필수
- 파티션 간 cross-partition 조인 시 약간의 오버헤드

### Follow-ups

- [ ] GCP Cloud Scheduler에 `create_partition.py` 월 1회 실행 등록 (REQ-011)
- [ ] 보존 정책 결정: 6개월 이상 파티션 자동 DROP 여부
- [ ] 파티션별 execution_id FK 제약 검토 (현재 FK 미적용 — 파티션 테이블 제약)

## Alternatives Considered

- **Option A: 단일 테이블 + 시간 인덱스** — 기각 사유: 수백만 행 이후 INSERT 성능 저하, 오래된 데이터 정리에 VACUUM 필요
- **Option B: LIST 파티션 (status 기준)** — 기각 사유: 쿼리 패턴이 시간 기반이고, status 값 분포가 불균일(success 90%+)
- **Option C: Hash 파티션** — 기각 사유: 시간 범위 쿼리에서 partition pruning 불가
- **Option D: TimescaleDB 확장** — 기각 사유: Cloud SQL 호환성 불확실, 추가 확장 의존성

## References

- PostgreSQL 공식 문서: Declarative Partitioning
- 관련 SQL: `database/schemas/003_node_logs_partitioned.sql`
- 스크립트: `database/scripts/create_partition.py`
