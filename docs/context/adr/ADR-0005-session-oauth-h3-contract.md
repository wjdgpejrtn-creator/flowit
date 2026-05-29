# ADR-0005: SessionRepository / OAuthConnectionRepository H-3 시그니처 계약

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: @dhwang0803-glitch (REQ-001), REQ-002 (ABC 소유)
- **Tags**: area/database, area/auth, layer/application

## Context

REQ-002 Auth 모듈은 `SessionRepository`와 `OAuthConnectionRepository`의 Port(ABC)를 정의한다. REQ-001 Database는 이 ABC를 구현하는 concrete Repository를 제공한다.

H-3 계약: "Repository는 Port ABC의 메서드명/시그니처를 **그대로** 구현해야 한다. ABC가 계약 기준이며, 구현체가 시그니처를 변경하는 것은 금지."

REQ-001 구현 시점에서 REQ-002의 ABC가 아직 최종 확정되지 않았으므로, 예상 시그니처 기반으로 먼저 구현하고 추후 정합성을 검증하기로 했다.

## Decision

**아래 메서드 시그니처를 H-3 계약으로 확정하고, REQ-002 ABC와 REQ-001 Repository가 이를 준수한다.**

### SessionRepository

```python
class SessionRepository:
    async def create_session(self, user_id: UUID, session_hash: str, **kwargs) -> ChatSessionModel
    async def find_by_hash(self, session_hash: str) -> ChatSessionModel | None
    async def revoke(self, session_id: UUID) -> None
    async def revoke_all_for_user(self, user_id: UUID) -> int
```

### OAuthConnectionRepository

```python
class OAuthConnectionRepository:
    async def get_by_credential_id(self, credential_id: UUID) -> OAuthConnectionModel | None
    async def get_active_for_user(self, user_id: UUID, service: str) -> OAuthConnectionModel | None
    async def update_tokens(self, connection_id: UUID, access_token_encrypted: bytes, refresh_token_encrypted: bytes | None = None) -> None
    async def revoke(self, connection_id: UUID) -> None
```

### 공통 규칙

- 모든 메서드는 `async`
- 반환 타입은 ORM 모델이 아닌 도메인 엔티티로 변환 예정 (서비스 레이어에서 매핑)
- `revoke_all_for_user`는 revoke된 행 수를 반환 (감사 로깅용)
- `**kwargs`는 향후 확장(metadata, device_info 등)을 위해 열어둠

## Consequences

### Positive

- REQ-001/REQ-002 간 명확한 계약으로 병렬 개발 가능
- 시그니처 불일치 시 테스트(`test_session_repo.py`)에서 조기 탐지
- 향후 ABC 추가 메서드 시에도 기존 계약은 변경 없음 (확장 가능)

### Negative / Trade-offs

- REQ-002 ABC 확정 시 시그니처 차이 발생 가능 → 조정 비용
- 현재 반환 타입이 ORM 모델 (`ChatSessionModel`, `OAuthConnectionModel`) — 추후 도메인 엔티티 매핑 레이어 추가 필요
- `**kwargs` 남용 가능성 — 명시적 파라미터 추가 시 ABC 수정 필요

### Follow-ups

- [ ] REQ-002: `auth/domain/ports/SessionRepository` ABC 확정 시 이 ADR 시그니처와 대조
- [ ] REQ-002: `auth/domain/ports/OAuthConnectionRepository` ABC 확정 시 대조
- [ ] 반환 타입 ORM → 도메인 엔티티 전환 (REQ-008 Storage 통합 시)
- [ ] H-3 계약 위반 탐지 CI: mypy Protocol 체크 또는 통합 테스트

## Alternatives Considered

- **Option A: REQ-002 ABC 확정 대기 후 구현** — 기각 사유: REQ-001이 전체 Persistence Layer 기반이므로 병렬 개발 불가 시 프로젝트 일정 지연
- **Option B: 별도 DTO 계층 도입** — Repository가 DTO 반환, UseCase에서 엔티티로 변환. 기각 사유: MVP 단계에서 불필요한 추상화 계층 증가
- **Option C: 시그니처 자유화 (H-3 계약 완화)** — 기각 사유: 모듈 간 통합 시 호환성 보장 불가

## References

- REQ-001 구현: `database/src/repositories/session_repository.py`
- REQ-001 구현: `database/src/repositories/oauth_connection_repository.py`
- H-3 계약 테스트: `database/tests/test_session_repo.py`
- 프로젝트 규칙: "Port(ABC) 메서드명/시그니처가 계약 기준" (CLAUDE.md)
