# Sprint 3 Week 2 — 2026-05-20 (수) skills_marketplace SkillDocument common_schemas SSOT shim 전환

## 작업 요약

PR #111(조장, common_schemas에 `SkillDocument` 추가) 머지 후속. skills_marketplace의 `SkillDocument`(PR #98 자체 정의)를 **common_schemas 재노출 shim**으로 전환하고, `SkillDocumentStore` Port가 `common_schemas.SkillDocument`를 사용하도록 정정. ADR-0017 소유권 문구도 재정정.

- **branch**: `feature/req-013-skills-marketplace` (REQ-013)
- **선행**: PR #111 (common_schemas SkillDocument, 머지 완료) — `SkillDocument` SSOT를 skills_marketplace → common_schemas 승격
- **트리거**: PR #106 조장 리뷰 (dict 우회 → common_schemas type-safe SSOT)

## 배경

PR #106 리뷰에서 조장이 지적: `SkillDocument`는 **생산자 ai_agent(Skills Builder) + 저장자 skills_marketplace(SkillDocumentStore)** 양쪽이 쓰는 공유 타입. skills_marketplace 도메인 소유로는 ai_agent가 import 규칙상 직접 참조 불가 → PR #106이 dict 우회(type 안전성 상실)를 강제당했다. → common_schemas로 SSOT 승격(PR #111) → 양쪽 type-safe 공유.

## 변경 (5 파일)

| 파일 | 변경 |
|------|------|
| `domain/entities/skill_document.py` | 자체 정의 → **common_schemas 재노출 shim** (`from common_schemas import SkillDocument`). 기존 `from skills_marketplace.domain.entities import SkillDocument` 경로 하위호환 유지 |
| `domain/ports/skill_document_store.py` | `from ..entities.skill_document import` → `from common_schemas import SkillDocument` (직접) |
| `docs/context/adr/ADR-0017` | §"SkillDocument SSOT 재정정" 추가 — skills_marketplace 소유 → common_schemas 승격 근거 (DDD 응집도보다 공유 타입 SSOT 우선) |
| `README.md` / `plan/REQ-013-*.md` | SkillDocument SSOT = common_schemas 정합 |

## 셀프 리뷰 (박아름 4축)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 | ✅ skills_marketplace → common_schemas 의존 (최내곽, 정합). shim은 재노출만 |
| 타 모듈 import | ✅ `common_schemas.SkillDocument` (모든 모듈 import 가능, 규칙 위반 0) |
| 스펙 정합 | ✅ ADR-0017 재정정 + README/plan |
| SSOT | ✅ SkillDocument 단일 정의 = common_schemas. skills_marketplace는 shim |

## 검증

- [x] `pytest modules/skills_marketplace/tests` — **20 passed** (shim 전환 후 기존 테스트 무변경 통과)
- [x] `skills_marketplace.domain.entities.SkillDocument is common_schemas.SkillDocument` → **True** (shim이 SSOT 가리킴 확인)
- [x] ruff — All checks passed (UP042 str·Enum 컨벤션 제외)

## 후속 (별도, ai_agent REQ-004)

- ai_agent 3 use case(SOP/functional/industry)의 `skill_documents` dict → `common_schemas.SkillDocument` 객체 (type-safe) — PR #106 dict 우회 해소
- GCS adapter(`SkillDocumentStore` 구현) — 위치 미정

## 관련 메모리

- [[project_skills_marketplace_creation]] — skills_marketplace 신설 + ADR-0017
- [[project_skillsmp_compatibility_2026_05_19]] — ADR-0017 이중 저장 배경
