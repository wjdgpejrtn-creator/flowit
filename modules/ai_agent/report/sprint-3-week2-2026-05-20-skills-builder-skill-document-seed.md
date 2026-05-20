# Sprint 3 Week 2 — 2026-05-20 (수) 박아름 Skills Builder SkillDocument — seed 기반 (functional/industry)

## 작업 요약

SOP(LLM 생성, 커밋 `8ad0b57`)에 이어 **seed 기반 use case(`BuildFromFunctionalDomain` / `BuildFromIndustryDefault`)도 ADR-0017 SkillDocument(`skill_documents` payload)를 반환**하도록 확장. seed use case는 LLM이 없으므로 `instructions`를 **선택 필드**로 받아 점진 적용한다.

- **branch**: `feature/req-004-skills-builder` (Skills Builder = REQ-004)
- **TDD**: Red(functional 3 + industry 3) → Green
- **선행**: SOP SkillDocument 생성 (`8ad0b57`)

## 배경 — 박아름 결정 (LLM 초안 + 사람 큐레이션)

seed 기반 instructions를 채우는 방식:
```
[빌드타임 — seed 준비, ② 별도]
seed 노드 → LLM 초안 생성 → 사람이 검토·보완 → seed JSON에 instructions 확정

[런타임 — 본 작업 ①]
use case가 seed의 instructions를 읽기만 → skill_documents payload (LLM 의존 0, 결정적 유지)
```
→ 런타임 use case는 LLM을 안 쓰고(결정적 구조 유지), LLM은 seed 채우는 일회성 도구로만(②).

## 변경 (4 파일)

### `build_from_functional_domain_use_case.py` / `build_from_industry_default_use_case.py` (동일 패턴)

| 위치 | 변경 |
|------|------|
| 루프 선언 | `skill_documents: list[dict[str, str]] = []` 추가 |
| upsert 성공 후 | `entry.get("instructions")` 있으면 `skill_documents.append({node_type, name, description, instructions})` |
| `ResultFrame.payload` | `"skill_documents"` 키 추가 |

### 테스트 (functional / industry 각 3건)

- seed에 instructions 있으면 skill_documents 포함
- seed에 instructions 없으면 skill_documents 비움 (NodeDefinition은 정상 upsert)
- 실제 seed(instructions 미포함)도 안 깨짐 — skill_documents 비고 NodeDefinition만

## 설계 결정 — `instructions` 선택 필드 (점진 안전)

| | 필수로 했다면 | 선택으로 (채택) |
|--|-------------|----------------|
| ② seed 채우기 전 | 실제 seed 전부 `E_SEED_ENTRY_INVALID`로 깨짐 | NodeDefinition 정상 upsert, skill_documents만 비움 |
| ② seed 채운 후 | — | 자동으로 skill_documents 활성 |

SOP는 LLM이 항상 instructions 생성하므로 필수였지만, seed는 데이터를 점진 채우므로 선택이 안전. import 규칙은 SOP와 동일 — `skills_marketplace.SkillDocument` 직접 import 안 하고 dict 반환 (조장 리뷰 #98 "use case 경유" 준수).

## 셀프 리뷰 (박아름 4축 룰)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 의존성 위반 | ✅ 0건 (skills_marketplace domain 직접 import 안 함) |
| 타 모듈 import 문제 | ✅ 0건 (dict 반환) |
| 스펙 정합 | ✅ ADR-0017 이중 저장 + SkillDocument 구조 정합 |
| SSOT | ✅ SkillDocument 소유 = skills_marketplace (ai_agent는 데이터만 생성·반환) |

## 검증

- [x] `pytest skills_builder/` 전체 — **127 passed (회귀 0)**
- [x] functional/industry 신규 테스트 각 3건
- [x] ruff — 추가분 0 (기존 lint 6건: import 정렬 4 + E501 2는 본 작업 무관, 별도)

## 범위 / 한계

| 항목 | 상태 |
|------|------|
| SOP / functional / industry SkillDocument payload 반환 | ✅ (3 use case 모두 완료) |
| **② seed instructions 채우기** (LLM 초안 + 사람 큐레이션 → seed JSON 확정) | ⏳ 후속 — 별도 작업 (LLM 인프라 + 검토 시간) |
| GCS 저장 (`SkillDocumentStore.save` via skills_marketplace use case) | ⏳ 후속 (GCS adapter + use case wiring) |
| scripts/templates 생성 | ⏳ 후속 (조장 리뷰 #98 6번) |

## 관련 메모리

- [[project_skills_builder_customization_v2]] — 대화 흐름 UX + SkillDocument 소비 경로
- [[project_skills_marketplace_creation]] — ADR-0017 이중 저장 + 조장 리뷰 #98 (use case 경유)
