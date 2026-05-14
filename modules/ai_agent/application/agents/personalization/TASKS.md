# Personalization Agent — 작업 명세

**담당자**: 햄햄(이가원)
**Modal app**: `agent-personalization`

## 목적

Claude Code memory.md 패턴으로 사용자별 워크플로우 패턴/선호도를 GCS에 누적 저장.
세션 시작 시 로드해 Orchestrator state에 주입, 워크플로우 완료 시 LLM이 패턴 추출해 갱신.

## 저장 구조

```
gs://workflow-automation-personal/users/{user_id}/
  MEMORY.md              # 인덱스 (Claude Code 패턴)
  user_role.md           # type: user
  workflow_patterns.md   # type: feedback
  favorite_nodes.md      # type: project
  integrations.md        # type: reference
```

각 .md 파일 frontmatter: `name`, `description`, `type` (user/feedback/project/reference)

## Work items

- [ ] `domain/ports/personal_memory_store.py` 정의 (PersonalMemoryStore ABC)
  - `load_index(user_id) -> list[MemoryFileRef]`
  - `load_file(user_id, filename) -> MemoryFile`
  - `save_file(user_id, file: MemoryFile) -> None`
  - `delete_file(user_id, filename) -> None`
- [ ] `domain/entities/memory_file.py` 정의 (MemoryFile entity)
- [ ] `adapters/memory/gcs_memory_store.py` 구현 (google-cloud-storage 기반)
- [ ] `LoadUserMemoryUseCase` 구현 — 세션 시작 시 호출
- [ ] `UpdateUserMemoryUseCase` 구현 — 워크플로우 완료 시 LLM이 패턴 추출 → 새 .md 또는 기존 갱신
- [ ] `RecallPersonalSkillsUseCase` 구현 — 특정 컨텍스트에서 관련 메모리 검색
- [ ] Modal app 작성 (`adapters/modal/personalization_app.py`)
- [ ] Modal 배포
- [ ] integration test: GCS에 .md 저장/로드/갱신 흐름

## 의존성

- GCS 버킷 `workflow-automation-personal` (Terraform이 5/25 시점 생성, 그 전엔 dev 버킷 사용)
- `llm-base` Modal endpoint (UpdateUserMemoryUseCase에서 패턴 추출용)
- `agent_protocol.py` schema

## 완료 기준

- 신규 사용자 → MEMORY.md 자동 생성
- 워크플로우 완료 후 새 패턴이 워크플로우_patterns.md에 추가됨
- 다음 세션 시작 시 해당 패턴이 Orchestrator state에 주입
- Phase A 게이트 통과
