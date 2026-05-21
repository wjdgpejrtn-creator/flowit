# Sprint 3 Week 2 — 2026-05-20 (수) 박아름 Skills Builder SkillDocument 생성 (ADR-0017)

## 작업 요약

`BuildFromSOPUseCase`가 LLM으로 `NodeDefinition`(메타)만 추출하던 것을, ADR-0017 이중 저장 정책에 따라 **`SkillDocument`(SKILL.md 지침서) 데이터도 동시 생성**하도록 확장. 사용자가 대화 중 스킬을 옵션으로 제시받을 때 읽는 "사람이 읽는 지침서"(`instructions` markdown)를 LLM이 메타와 함께 한 번에 뽑는다.

- **branch**: `feature/req-004-skills-builder` (Skills Builder = REQ-004, 새 sub-branch 미생성 — [[feedback_branch_strategy]] 룰 정합)
- **방식**: (A) LLM이 SkillDocument도 함께 생성 (박아름 5/20 결정 — NodeDefinition 파생 아닌 LLM 직접 생성)
- **TDD**: Red(4 실패) → Green(23 passed)

## 배경

- **ADR-0017**: Skills Builder 산출물 = `NodeDefinition`(메타, DB) + `SkillDocument`(지침서, GCS) 이중 저장. SkillDocument 소비자 = "Main Agent (사용자 대화 중 옵션 제시)"
- **5/20 대화 흐름 UX 결정** ([[project_skills_builder_customization_v2]]): Skills Builder는 별도 페이지가 아니라 대화창 내 `intent=build_skill` 라우팅. SkillDocument가 그 대화 중 옵션 제시의 핵심 산출물

## 변경 (2 파일)

### `build_from_sop_use_case.py`

| 위치 | 변경 |
|------|------|
| `_ExtractedSkillNode` | `instructions: str = Field(min_length=1)` 필드 추가 (SKILL.md markdown body, 필수) |
| `_build_prompt` instruction 텍스트 | instructions 필드 생성 지시 추가 (`## When to use`/`## Steps`/`## Inputs·Outputs` 섹션) |
| `_build_prompt` output_schema | items.properties + required에 `instructions` 추가 (grammar-level 강제 정합) |
| `_build_prompt` few_shot_example | 2개 예시 노드에 instructions markdown 추가 |
| `execute` 루프 | upsert **성공분만** `skill_documents.append({node_type, name, description, instructions})` |
| `ResultFrame.payload` | `"skill_documents"` 키 추가 |

### `test_build_from_sop_use_case.py`

- `_make_extracted` 헬퍼에 `instructions` 파라미터 추가
- 신규 테스트 4건: instructions 필드 존재 / 프롬프트 instructions 요청 / payload skill_documents 반환 / 실패 노드 제외
- 기존 `test_embedder_failure_isolated...`의 inline `_ExtractedSkillNode`에 instructions 보강

## 설계 결정 — import 규칙 (조장 리뷰 #98 준수)

`ai_agent`는 `skills_marketplace.SkillDocument`(domain/entities)를 **직접 import하지 않는다**. LLM 추출 결과를 **dict**(`{node_type, name, description, instructions}`)로 `ResultFrame.payload`에 담아 반환만 하고, 실제 `SkillDocument` 모델 조립 + GCS 저장은 후속(skills_marketplace use case 경유 + `SkillDocumentStore` 구현)에서 wiring. → 조장 리뷰 #98 "ai_agent는 use case 경유" 결정과 정합, ai_agent → skills_marketplace 직접 의존 0.

## 셀프 리뷰 (박아름 4축 룰)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 의존성 위반 | ✅ 0건 (ai_agent application 레이어, skills_marketplace domain 직접 import 안 함) |
| 타 모듈 import 문제 | ✅ 0건 (dict 반환 — skills_marketplace 의존 미생성) |
| 스펙 정합 | ✅ ADR-0017 이중 저장 + SkillDocument 구조(name/description/instructions) 정합 |
| SSOT | ✅ SkillDocument 소유 = skills_marketplace (ai_agent는 데이터만 생성·반환) |

## 검증

- [x] `pytest test_build_from_sop_use_case.py` — **23 passed** (신규 4 + 기존 19)
- [x] `pytest skills_builder/` 전체 — **121 passed (회귀 0)**
- [x] ruff — 추가분 0 (기존 lint 5건: import 정렬 2 + E501 3은 본 작업 무관, 별도)

## 범위 / 한계

| 항목 | 상태 |
|------|------|
| `BuildFromSOPUseCase` (LLM 기반) | ✅ 본 작업 |
| `BuildFromIndustryDefault` / `BuildFromFunctionalDomain` (seed 기반, LLM 없음) | ⏳ 후속 — seed JSON에 instructions 추가 vs 별도 처리 결정 필요 |
| GCS 저장 (`SkillDocumentStore.save` via skills_marketplace use case) | ⏳ 후속 (GCS adapter + use case wiring) |
| scripts/templates 생성 | ⏳ 후속 (조장 리뷰 #98 6번 — `_ScriptFile` 스키마 조이기 포함) |

## Impact Assessment

| 영역 | 영향 |
|------|------|
| `build_from_sop_use_case.py` | 본 작업 (instructions 생성 + payload) |
| `ResultFrame` 소비자 (Orchestrator/프론트) | payload에 `skill_documents` 키 추가 (기존 키 유지, additive) |
| `skills_marketplace` | 0 (직접 의존 미생성) |
| `common_schemas` / spec / 다른 sub-agent | 0 |

## 관련 메모리

- [[project_skills_builder_customization_v2]] — 대화 흐름 UX 결정 + SkillDocument 소비 경로
- [[project_skills_marketplace_creation]] — ADR-0017 이중 저장 + 조장 리뷰 #98 (use case 경유)
- [[project_skillsmp_compatibility_2026_05_19]] — ADR-0017 신설 배경
