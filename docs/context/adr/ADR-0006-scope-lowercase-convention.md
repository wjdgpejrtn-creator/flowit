# ADR-0006: scope 값 lowercase 통일 ('private', 'team', 'public')

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: @dhwang0803-glitch (REQ-001)
- **Tags**: area/database, area/common_schemas, convention

## Context

여러 테이블에서 `scope` 컬럼이 리소스의 가시성/접근 범위를 나타낸다:
- `workflows.scope` (001_core.sql)
- `skills.scope` (005_skill_bootstrap.sql)
- `agent_memories.scope` (012_agent_memory.sql)

각 테이블의 CHECK 제약에서 scope 값을 정의하는데, 일관된 네이밍 규칙이 없으면 다음 문제가 발생한다:
- 대소문자 혼용 (`Private` vs `private` vs `PRIVATE`)
- 프론트엔드/백엔드 간 문자열 불일치
- Enum 정의 시 매핑 혼란

## Decision

**모든 테이블의 scope 값은 lowercase로 통일한다: `'private'`, `'team'`, `'public'`.**

### SQL CHECK 제약 (전 테이블 동일)

```sql
CHECK (scope IN ('private', 'team', 'public'))
```

### 적용 범위

| 테이블 | 스키마 파일 | 기본값 |
|--------|-----------|--------|
| `workflows` | 001_core.sql | `'private'` |
| `skills` | 005_skill_bootstrap.sql | `'private'` |
| `agent_memories` | 012_agent_memory.sql | `'private'` |

### 연동 규칙

- **common_schemas Enum**: `class Scope(str, Enum): PRIVATE = "private"; TEAM = "team"; PUBLIC = "public"`
- **API 요청/응답**: lowercase 문자열 그대로 사용
- **프론트엔드**: 표시 시에만 capitalize, 전송 시 lowercase
- **새 테이블 추가 시**: 동일 CHECK 제약 적용 필수

## Consequences

### Positive

- 전 레이어에서 단일 비교 로직 (`scope == "private"`)
- Python `str` Enum과 DB 값이 직접 일치하여 별도 변환 불필요
- 프론트엔드 ↔ API ↔ DB 간 별도 매핑 제거
- 신규 테이블 추가 시 명확한 규칙 제공

### Negative / Trade-offs

- 기존에 다른 형식으로 저장된 데이터가 있다면 마이그레이션 필요 (현재는 초기 구현이므로 해당 없음)
- 향후 scope 값 추가 시 (`'org'` 등) 모든 테이블의 CHECK 제약 수정 필요

### Follow-ups

- [ ] REQ-012: `common_schemas/enums.py`에 `Scope` Enum 추가 (lowercase 값)
- [ ] REQ-010: 프론트엔드에서 scope 필터 UI 구현 시 이 규칙 준수
- [ ] 신규 scope 값 추가 시 이 ADR 업데이트 + 마이그레이션 스크립트 작성

## Alternatives Considered

- **Option A: UPPERCASE ('PRIVATE', 'TEAM', 'PUBLIC')** — 기각 사유: Python Enum은 `.value`가 실제 저장값이므로 API JSON과 불일치, 별도 변환 필요
- **Option B: PascalCase ('Private', 'Team', 'Public')** — 기각 사유: SQL 표준에서 문자열 비교 시 case-sensitive가 기본, 실수 유발
- **Option C: 정수 Enum (1, 2, 3)** — 기각 사유: 가독성 저하, SQL 쿼리 디버깅 시 의미 파악 어려움
- **Option D: PostgreSQL ENUM 타입** — 기각 사유: 값 추가/삭제 시 ALTER TYPE 필요, VARCHAR + CHECK가 유연

## References

- 관련 SQL: `001_core.sql:58`, `005_skill_bootstrap.sql:23`, `012_agent_memory.sql:11`
- 프로젝트 컨벤션: `Enum: str 상속으로 JSON 직렬화 호환` (CLAUDE.md)
