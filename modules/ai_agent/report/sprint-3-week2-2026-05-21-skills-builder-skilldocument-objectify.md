# Sprint 3 Week 2 — 2026-05-21 (목) ai_agent SkillDocument 객체화 (dict → common_schemas.SkillDocument)

## 작업 요약

PR #111(common_schemas SkillDocument 추가) + PR #113(skills_marketplace shim) 머지 후속. ai_agent 3 use case의 `skill_documents`를 **dict → `common_schemas.SkillDocument` 객체**로 전환 (type-safe). PR #106 dict 우회를 해소하여 SkillDocument SSOT 이동을 end-to-end로 완결.

- **branch**: `feature/req-004-skills-builder` (REQ-004 Skills Builder)
- **선행**: PR #111 머지(common_schemas) + PR #113 머지(skills_marketplace shim)
- **트리거**: 조장 PR #106/#113 리뷰 (dict 우회 → type-safe 객체)

## 변경 (3 use case + 3 test)

| 위치 | 변경 |
|------|------|
| import | `from common_schemas import SkillDocument` |
| 선언 | `skill_documents: list[dict[str, str]]` → `list[SkillDocument]` |
| 수집 | dict → `SkillDocument(skill_id=node_def.node_id, name, description, instructions)` |
| payload | `[doc.model_dump(mode="json") for doc in skill_documents]` (SSE 직렬화) |
| 주석 | dict 시절 주석 → 객체화 정합 |
| 테스트 | `node_type` 매핑 → SkillDocument 필드(`skill_id`/`name`/`description`/`instructions`) 검증 |

## node_type 제거 (조장 PR #113 후속 결정)

조장: *"SkillDocument는 SOP 레퍼런스 저장 + skill builder 불러오기용 지침서인데, node_type 붙이면 node가 아닌데 node로 인식돼 호출되는 문제."*

→ **SkillDocument ≠ Node** (Tool≠Node 원칙처럼). `node_type` 없이 **`skill_id`(=node_def.node_id)로 NodeDefinition과 연결**. 소비자(skills_marketplace는 skill_id 키 GCS 저장 / Main Agent는 name·description·instructions 옵션 제시)가 node_type을 안 쓰므로 손실 없음. `node_type`은 `payload["node_types"]`에 별도 유지.

## 셀프 리뷰 (박아름 3축)

| 축 | 결과 |
|----|------|
| Clean Architecture | ✅ `common_schemas.SkillDocument` import (최내곽). framework 0 |
| SSOT | ✅ SkillDocument 단일 정의 = common_schemas. ai_agent가 객체 생성 — **PR #106 dict 우회 해소** (type-safe) |
| 크로스 모듈 | ✅ common_schemas import (규칙 위반 0). skills_marketplace 직접 의존 미생성 |

## 검증

- [x] `pytest skills_builder/` — **127 passed (회귀 0)**
- [x] ruff — 변경분 0 (`build_from_sop_use_case.py:335` 기존 few_shot `input_sop_snippet` E501은 본 작업 무관)

## SkillDocument SSOT 이동 end-to-end 완결

```
PR #106  ai_agent SkillDocument 생성 (dict)           [머지]
PR #111  common_schemas에 SkillDocument 추가 (SSOT)    [머지]
PR #113  skills_marketplace shim + Port + ADR-0017    [머지]
본 PR    ai_agent dict → common_schemas.SkillDocument 객체 (dict 우회 해소)  ← 마지막 조각
```

## 후속 (별도)

- GCS 저장 wiring (`SkillDocumentStore` 구현 + skills_marketplace use case 경유)
- seed instructions 채우기 (LLM 초안 + 사람 큐레이션 → seed JSON 확정)

## 관련 메모리

- [[project_skills_marketplace_creation]] — SkillDocument SSOT common_schemas 이동
- [[project_skillsmp_compatibility_2026_05_19]] — ADR-0017 이중 저장
