# Memory Adapters — 작업 명세

**담당자**: 햄햄(이가원)

## 구현 파일

- `gcs_memory_store.py` — PersonalMemoryStore의 GCS 구현체

## Work items

- [ ] `from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore`
- [ ] google-cloud-storage 클라이언트 의존성 추가 (pyproject.toml)
- [ ] 4개 메서드 구현 (load_index, load_file, save_file, delete_file)
- [x] MEMORY.md frontmatter 파싱 — `_parse_frontmatter` 자체 구현 (`gcs_memory_store.py`)
- [x] 환경변수: `GCS_PERSONAL_BUCKET` (GCP Secret Manager `gcs-personal-bucket`로 주입 — ADR-0016)
- [ ] integration test (storage 모듈의 GCS 테스트 패턴 참조)

## 참조

- `modules/storage/adapters/gcs/` — GCS 어댑터 기존 패턴
- Claude Code memory.md 포맷 정의 (사용자 본인 경험 활용)
