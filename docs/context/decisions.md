# Architecture Decision Records (ADR)

> 설계 결정의 **배경과 맥락**을 남기는 문서.
> 개별 ADR은 [`adr/`](./adr/) 하위에 `ADR-NNNN-slug.md` 형식으로 작성하고, 본 파일은 **인덱스**로만 사용한다.

## 작성 규칙

1. 새 결정은 `adr/ADR-NNNN-slug.md` 파일로 추가 (NNNN은 4자리 zero-padded, 1부터 순차).
2. 기존 결정을 **뒤집는** 경우: 원본 ADR에 `Superseded by ADR-NNNN` 표기 + 새 ADR 추가. **삭제 금지**.
3. 본 인덱스에 `Status / Title / Date` 한 줄을 추가한다.
4. 템플릿: [`adr/ADR-0000-template.md`](./adr/ADR-0000-template.md) 복사 후 작성.

## Status 정의

- `Proposed` — 검토 중
- `Accepted` — 적용됨 (현행)
- `Deprecated` — 더 이상 권장되지 않음 (대체 없음)
- `Superseded` — 다른 ADR로 대체됨

## Index

| # | Title | Status | Date |
|---|-------|--------|------|
| 0001 | [브랜치-per-모듈에서 모노레포 구조로 전환](./adr/ADR-0001-monorepo-structure.md) | Accepted | 2026-05-03 |
| 0002 | [pgvector HNSW 인덱스 설정 (m=16, ef_construction=64)](./adr/ADR-0002-pgvector-hnsw-index.md) | Accepted | 2026-05-05 |
| 0003 | [node_logs RANGE 파티션 (월별) + 자동 생성 스크립트](./adr/ADR-0003-node-logs-range-partition.md) | Accepted | 2026-05-05 |
| 0004 | [BaseCipher typing.Protocol 기반 DI 인터페이스](./adr/ADR-0004-base-cipher-protocol.md) | Accepted | 2026-05-05 |
| 0005 | [SessionRepository / OAuthConnectionRepository H-3 시그니처 계약](./adr/ADR-0005-session-oauth-h3-contract.md) | Accepted | 2026-05-05 |
| 0006 | [scope 값 lowercase 통일 ('private', 'team', 'public')](./adr/ADR-0006-scope-lowercase-convention.md) | Accepted | 2026-05-05 |
| 0007 | [Python 최소 버전 3.12로 상향](./adr/ADR-0007-python-312-minimum.md) | Accepted | 2026-05-05 |
| 0008 | [NodeExecutionState를 common-schemas 공유 타입으로 도입](./adr/ADR-0008-node-execution-state-shared-type.md) | Accepted | 2026-05-07 |
| 0009 | [UtcDatetime 공용 타입 도입 — naive datetime 자동 UTC 변환](./adr/ADR-0009-utc-datetime-type.md) | Accepted | 2026-05-08 |
| 0010 | [Storage 모듈 아키텍처 — Mapper 패턴 + 타 모듈 Port ABC 구현](./adr/ADR-0010-storage-module-architecture.md) | Accepted | 2026-05-07 |
