# 스킬 바인딩 결함(#372) 진단 + ADR-0024 D2 게시측 구현

- **날짜**: 2026-06-05
- **담당**: 박아름 (REQ-013 skills_marketplace)
- **관련**: 이슈 #372 / ADR-0024 (PR #377 머지) / #376 (신정혜) / PR #381 (본 작업)

---

## 1. 배경 — staging 재현

staging 시연에서 "신입 온보딩 절차를 **이메일**로 안내" 워크플로우 생성 시 결함이 두 번 재현됐다.

| | 1차 | 2차 |
|---|---|---|
| 증상 | "바인딩할 LLM 노드 없음" → QA 0~4점 → 에러 | **QA 10점 통과 → 저장** → 실행 시 `requires slack` |
| 위험도 | 에러로 막힘(인지 가능) | **통과로 위장**(저장됐는데 실행 불가) |

공통적으로 스킬 seed `hr_onboarding_workflow`가 **워크플로우 노드로 둔갑**해 slack을 요구 — 사용자는 이메일을 원했으나 "메일→슬랙"이 됐다.

## 2. 진단 — 스킬의 이중 정체성 (3결함)

스킬이 "실행 노드"와 "LLM 노드 주입 지침서"로 동시 구현되어 충돌:

- **결함 A** (Composer): drafter가 스킬 선택을 몰라 LLM 노드(`category=="ai"`) 미포함 → `_bind_skill_node` skip → `skill_id=null`.
- **결함 B** (설계 SSOT): retriever가 스킬 NodeDefinition을 노드 후보로 합산 → drafter가 빈 껍데기 노드로 배치.
- **결함 C** (게시): `category="action"` placeholder → `category=="ai"` 매칭 영구 실패.

추가 규명: `hr_onboarding_workflow`는 nodes_graph 카탈로그(53종)에 **없는** `ai_agent/seeds/hr.json`의 skill_node. 게시 시 NodeDefinition으로 등록되어 일반 노드 검색(`SearchNodesUseCase`, `is_mvp` 필터 없음)에 섞여 들어간 것이 "메일→슬랙"의 게시측 원인.

## 3. 설계 — ADR-0024 (PR #377 머지)

스킬 사용 모델을 **"지침서 묶음"(모델 A)으로 단일화**. `SkillDocument`를 단일 `instructions` → `SKILL.md`(노드 주입) + `COMPOSER.md`(composer 주입) 2-md 디렉토리로. **D2**: 검색 = 스킬 자체 임베딩(`SearchSkillsUseCase`), `node_definition_id` 폐기 → 스킬을 노드로 등록하지 않는다.

## 4. 구현 — D2 게시측 (PR #381)

`PublishSkillUseCase` (`modules/skills_marketplace/application/use_cases/publish_skill_use_case.py`):

- `_build_node_definition` + `node_def_repo.upsert` **제거** — 게시 시 NodeDefinition 미생성, `node_definition_id` None 유지.
- 검색용 **embedding 백필 유지** — 스킬 자체 검색 노출 보존.
- `node_def_repo`: `Optional = None` deprecated (조장 협의 (b) — api_server 시그니처 하위호환, 후속 제거).
- 미사용 import(`NodeDefinition`, `uuid4`) 정리.

## 5. 사후영향 평가

| 항목 | 결과 |
|------|------|
| api_server `use_cases.py:91` | ✅ 무변경 (node_def_repo Optional 호환) |
| execution_engine | ✅ 무영향 (skill_id 바인딩 `_inject_skill` 경로) |
| 스킬 검색 | ✅ `SearchSkillsUseCase`(skill embedding) 유지 |
| 기존 등록 NodeDef | ⏳ 조장 후속 (머지 후 staging DB 정리) |

## 6. 테스트

- `test_publish_node_definition`: "NodeDef 생성" → **"생성 안 함 + node_definition_id None"** 검증 전환.
- `skills_marketplace` 전체 **121 passed**, ruff clean.
- 셀프 3축 리뷰: 머지 차단 없음 (LOW 3건 후속 추적).

## 7. 역할 분담 + 후속

| 영역 | 담당 | 내용 |
|------|------|------|
| 근본(노드 검색/매칭) | 조장 | 그래프 DB 온톨로지 추가 |
| QA/drafter 프롬프트 | 신정혜 | QA 거짓통과(`qa_evaluator`가 node_type 못 봄) enrich |
| node_definition(게시) | 박아름 | **D2 게시측 (PR #381)** ✅ |
| staging DB 기존 NodeDef 정리 | 조장 | PR #381 머지 후 |

**박아름 잔여 후속**: 빌더 2-md(SKILL.md+COMPOSER.md) 합성 추출계약 재설계 + #343 seed embedding backfill (ADR-0024 Follow-up).
