# ADR-0009: UtcDatetime 공용 타입 도입 — naive datetime 자동 UTC 변환

- **Status**: Accepted
- **Date**: 2026-05-08
- **Deciders**: @dhwang0803-glitch
- **Tags**: area/common-schemas, layer/domain, layer/orm

## Context

DDL 48개 timestamp 컬럼이 전부 `TIMESTAMPTZ`이다. SQLAlchemy ORM에서 `DateTime(timezone=True)`를 명시하지 않으면 `TIMESTAMP WITHOUT TIME ZONE`으로 추론되어, Python 코드에서 aware datetime을 INSERT할 때 asyncpg가 `cannot pass tz-aware datetime to tz-naive column` 에러를 발생시킨다.

반대로 Pydantic 도메인 엔티티에서 bare `datetime`을 사용하면 누군가 `datetime.now()`나 `datetime.utcnow()`(Python 3.12 deprecated)로 naive datetime을 넣어도 validation을 통과하고, ORM 레이어에서야 비로소 런타임 에러가 터진다.

Pydantic의 `AwareDatetime`을 검토했으나, naive datetime 입력 시 `ValidationError`를 발생시켜 프로그램이 중단되므로 프로덕션 안정성에 부적합하다고 판단했다.

## Decision

`common_schemas.types.UtcDatetime` 타입을 도입한다.

```python
UtcDatetime = Annotated[datetime, BeforeValidator(_ensure_utc)]
```

- naive datetime이 들어오면 **에러 없이 UTC timezone을 자동 부여**한다.
- aware datetime이 들어오면 그대로 통과시킨다.
- 서버 환경이 전부 UTC이므로 naive → UTC 가정이 안전하다.

적용 범위 (3단계 방어):

| 레이어 | 방식 |
|--------|------|
| Pydantic 도메인 엔티티 | `UtcDatetime` 타입 사용 |
| dataclass 엔티티 | `default_factory=lambda: datetime.now(timezone.utc)` |
| ORM 모델 | `DateTime(timezone=True)` 필수 |

## Consequences

### Positive
- naive datetime 입력이 어느 레이어에서든 에러 없이 UTC로 정규화됨
- `datetime.utcnow()` 같은 deprecated 패턴을 쓰더라도 런타임 크래시 방지
- 전체 모듈이 `common_schemas.types`에서 import하므로 SSOT 유지

### Negative / Trade-offs
- naive datetime이 실제로는 KST 등 다른 시간대였을 경우 UTC로 잘못 해석될 수 있음. 단, 서버 환경이 전부 UTC이고 프론트엔드는 ISO-8601 문자열로 전송하므로 현실적 위험은 낮음.

### Follow-ups
- `datetime.utcnow()` 사용처 0건 확인 완료 (codebase grep)
- CLAUDE.md SSOT 핵심 결정사항에 컨벤션 추가 완료
- TypeScript codegen에 `Annotated` unwrap 지원 추가 완료

## Alternatives Considered

- **Pydantic `AwareDatetime`**: naive 입력 시 `ValidationError` 발생 → 프로그램 중단 → 기각
- **bare `datetime` + 런타임 assert**: 에러 발생 위치가 분산되어 디버깅 어려움 → 기각
- **`datetime.now(timezone.utc)` 컨벤션만 강제**: 사람 실수를 방지할 수 없음 → 기각 (보조 수단으로는 유지)

## References

- PR #26: `fix(cross-module): UtcDatetime 도입 + datetime 안전성 강화`
- CLAUDE.md: "datetime은 반드시 timezone-aware" 섹션
