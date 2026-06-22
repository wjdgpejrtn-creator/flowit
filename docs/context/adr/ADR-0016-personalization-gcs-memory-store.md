# ADR-0016: Personalization GCS MemoryStore — Port 소유권 · 저장 경로 · Embedding 분리

- **Status**: Accepted
- **Date**: 2026-05-18
- **Deciders**: @이가원
- **Reviewers/Informed**: @billionaireahreum (박아름)
- **Tags**: area/personalization, layer/adapter

## Context

REQ-004 Personalization sub-agent는 사용자 패턴을 파일 기반으로 저장해야 했다. 이때 세 가지 설계 결정이 필요했다.

1. **Port 소유권**: `PersonalMemoryStore` Port를 어느 모듈에 두고, 구현체를 어디에 두는가
2. **GCS 저장 경로**: `users/{user_id}/` 하위 파일 명명 규칙
3. **Embedding 저장 위치**: `.md` frontmatter 내부에 둘 것인가, 별도 파일로 분리할 것인가

## Decision

### 1. Port 소유권 — ai_agent 자체 어댑터 (storage 모듈 경유 X)

`PersonalMemoryStore` Port(ABC)와 `GCSMemoryStore` 구현체 모두 `modules/ai_agent/` 내에 위치한다.

- Port: `ai_agent/domain/ports/personal_memory_store.py`
- 구현체: `ai_agent/adapters/memory/gcs_memory_store.py`

`modules/storage/`는 RDB(PostgreSQL) Repository에 한정한다. GCS 파일 기반 저장은 Personalization 전용 관심사이며, storage 모듈을 경유할 이유가 없다.

### 2. GCS 저장 경로 규칙

```
gs://{GCS_PERSONAL_BUCKET}/users/{user_id}/
  MEMORY.md              # 인덱스 (- [name](name.md) — description)
  {name}.md              # 개별 메모리 파일 (frontmatter + body)
  {name}.emb.json        # 임베딩 벡터 (BGE-M3 768d)
```

버킷명은 환경 변수 `GCS_PERSONAL_BUCKET`으로 주입한다. 하드코딩 금지.

### 3. Embedding 분리 저장 (`.emb.json`)

임베딩 벡터(768d float list)를 `.md` frontmatter에서 제거하고 `{name}.emb.json`으로 별도 저장한다.

```json
[0.1, 0.2, ..., 0.9]
```

`PersonalMemoryStore` Port에 `load_embedding` / `save_embedding` 메서드를 추가하여 명시적으로 분리한다.

## Consequences

### Positive
- `.md` 파일이 사람이 읽을 수 있는 크기로 유지됨 (768d float 제거)
- 임베딩만 재계산 시 `.md`를 건드리지 않아도 됨
- storage 모듈이 GCS 의존성을 갖지 않아 단일 책임 유지

### Negative / Trade-offs
- `PersonalMemoryStore`가 ai_agent 내부 Port임에도 외부(Personalization agent)에서 직접 DI 조립 — Composition Root(`main.py`)가 어댑터 세부를 알아야 함
- 파일이 `.md` + `.emb.json` 두 개로 분리되어 삭제/이동 시 두 파일을 함께 관리해야 함

### Follow-ups
- E2E 통합 테스트: `GCSMemoryStore` 실 버킷 연동 (`tests/integration/test_gcs_memory_store.py`)
- Terraform GCS 버킷 생성 (2026-05-25 예정, REQ-011)

## Alternatives Considered

- **storage 모듈에 GCSRepository 추가**: storage가 RDB 전용이라는 원칙 위반. 기각.
- **frontmatter에 embedding 유지**: `.md` 파일 크기가 수십 KB로 커짐. 가독성·전송 비용 문제로 기각.

## References

- PR #76 (`feature/req-004-personalization`) — GCSMemoryStore 구현 + embedding 분리 반영
- `docs/specs/REQ-004-ai-agent.md` §6 — GCS 저장 패턴 명세
- ADR-0013 — EmbedderPort SSOT (ai_agent 어댑터 예외 패턴과 유사한 맥락)
