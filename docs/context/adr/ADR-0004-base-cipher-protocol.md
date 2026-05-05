# ADR-0004: BaseCipher typing.Protocol 기반 DI 인터페이스

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: @dhwang0803-glitch (REQ-001), REQ-002 (구현 담당)
- **Tags**: area/database, area/auth, layer/domain

## Context

REQ-001 Database 레이어의 `CredentialStore`는 사용자 OAuth 토큰과 API 키를 암호화하여 저장한다. 암호화 구현체(AES-GCM)는 REQ-002 Auth 모듈이 소유하지만, Database 레이어는 Auth에 직접 의존해서는 안 된다 (Clean Architecture 의존성 방향 규칙).

문제:
- Database(REQ-001)는 암호화/복호화 기능이 필요
- 구현체(AESGCMCipher)는 Auth(REQ-002) 소유
- Domain 레이어에서 구체 구현 import 금지

## Decision

**`database/src/protocols.py`에 `BaseCipher`를 `typing.Protocol`로 정의하고, REQ-002가 이 프로토콜을 만족하는 구현체를 제공한다.**

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BaseCipher(Protocol):
    """Symmetric encryption interface for credential data (REQ-002 DI)."""
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
```

### DI 흐름

```
database/src/protocols.py     → BaseCipher (Protocol 정의)
database/src/repositories/    → BaseCipher를 생성자 주입으로 사용
auth/adapters/cipher/         → AESGCMCipher (Protocol 구현체, REQ-002 담당)
services/api-server/          → Composition Root에서 AESGCMCipher → BaseCipher 주입
```

### @runtime_checkable 사용 이유

테스트에서 `isinstance(cipher, BaseCipher)` 검증을 가능하게 하여, DI 설정 오류를 조기에 탐지.

## Consequences

### Positive

- Database 레이어가 Auth 모듈에 비의존 (의존성 역전 원칙 준수)
- 테스트 시 mock cipher 주입 용이 (`encrypt = lambda b: b` 등)
- `typing.Protocol`은 ABC 상속 없이 구조적 서브타이핑으로 구현체를 검증
- REQ-002가 독립적으로 암호화 알고리즘을 변경 가능 (인터페이스 불변)

### Negative / Trade-offs

- REQ-002 구현체가 반드시 `encrypt(bytes) → bytes`, `decrypt(bytes) → bytes` 시그니처를 맞춰야 함
- Protocol은 런타임 타입 체크 비용이 약간 있음 (서비스 시작 시 1회)
- ABC 대비 IDE 자동완성이 약간 제한될 수 있음

### Follow-ups

- [ ] REQ-002: `auth/adapters/cipher/aes_gcm.py`에 `AESGCMCipher` 구현 (이 Protocol 만족)
- [ ] REQ-002: `auth/domain/ports/CipherPort` ABC와 이 Protocol의 시그니처 일치 검증
- [ ] services/api-server DI 설정에서 `AESGCMCipher` → `BaseCipher` 바인딩

## Alternatives Considered

- **Option A: ABC 상속 (auth/domain/ports/CipherPort)** — Database가 Auth의 ports를 직접 import. 기각 사유: Database → Auth 의존성 발생, Clean Architecture 위반
- **Option B: 단순 Callable 타입** — `Callable[[bytes], bytes]` 두 개(encrypt, decrypt). 기각 사유: 의미론적 명확성 부족, 타입 힌트에서 용도 구분 어려움
- **Option C: 암호화 로직을 Database 내부에 구현** — 기각 사유: 암호화는 Auth 도메인 소유권, 키 관리 책임 분리 필요

## References

- Python `typing.Protocol` PEP 544
- 프로젝트 의존성 방향 규칙: `CLAUDE.md` 참조
- 관련 코드: `database/src/protocols.py`
- SSOT: `auth/domain/ports/CipherPort`가 도메인 소유, `BaseCipher`는 Database 측 structural typing 인터페이스
