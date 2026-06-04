# Skills Builder Agent — 작업 명세

**담당자**: 박아름
**Modal app**: `agent-skills-builder`
**관련 ADR**: [`ADR-0020`](../../../../../docs/context/adr/ADR-0020-skills-builder-publish-lifecycle-gate.md) (게시 lifecycle 게이트 + 추출 wizard), [`ADR-0017`](../../../../../docs/context/adr/ADR-0017-skills-builder-skill-document-dual-storage.md) (NodeDefinition + SkillDocument 이중 저장)

> ⚠️ 이 문서는 **ADR-0020(2026-05-21 Accepted)** 기준으로 갱신됨. 초기 설계(SOP → `NodeDefinition` 즉시 upsert)는 폐기 — SOP 경로는 **추출 wizard + DRAFT 게시 lifecycle**(Option B)로 전환됐다.

## 목적

회사 내부 SOP 문서(doc_parser 출력) 또는 산업/직무 표준 default를 워크플로우 스킬로 변환:

- **SOP** → LLM 추출 → 사용자 검토·수정(wizard) → personal **DRAFT** 스킬 생성. `NodeDefinition`은 게시(PUBLISHED) 시점에 생성(Option B).
- **seed(산업/직무)** → 사전 큐레이션이라 카탈로그에 직접 upsert (Q7 자동 PUBLISHED 게이트, 리뷰 생략).

## 게시 lifecycle 분기 (ADR-0020)

| source_type | 경로 | NodeDefinition 생성 시점 |
|-------------|------|--------------------------|
| `sop` | wizard 3단계(metadata → 사용자 선택 → detail → 사용자 편집 → confirm) → personal DRAFT (Q8 + 옵션 1 2단계 분리) → Marketplace lifecycle | **PUBLISHED 시점** (skills_marketplace `PublishSkillUseCase`, Option B) |
| `industry_default` / `functional_domain` | seed JSON → `SkillNode` 검증 → 즉시 upsert | **upsert 시점** (Q7 큐레이션 자동 PUBLISHED) |

- **Q3 promotion-only**: Skills Builder는 **personal DRAFT만** 생성. team/company 스킬은 Marketplace `PromoteToTeam/Company` 승격으로만 도달(직접 생성 경로 없음).
- **옵션 1 (2026-06-04, LLM JSON 잘림 해소)**: 1회 호출에 노드 N개 × (긴 inputs/outputs JSON Schema + instructions markdown) 전체를 받아 `max_tokens=4096`을 초과하던 문제(line 220~250 col 부근 EOF) 해결. extract를 메타 5필드 추출(`extract_metadata`) + 선택된 메타에 detail 추출(`extract_detail`) 2단계로 분리하고, 안전망으로 `_STRUCTURED_MAX_TOKENS`를 8192로 상향.

## 인터페이스

입력: `AgentProtocolRequest`
- `payload.source_type` ∈ `{"sop", "industry_default", "functional_domain"}`
- `sop`은 `payload.step` ∈ `{"metadata", "detail", "confirm"}` 추가 (wizard 3단계, 기본 `metadata`)
- `step=detail`은 `payload.meta` 필수 (1차 응답에서 사용자가 선택한 메타 dict)

출력: `AsyncGenerator[SSEFrame]` — `AgentNodeFrame`(진행) + `ResultFrame`/`ErrorFrame`(결과)

라우팅: `services/agents/agent-skills-builder/main.py`가 `source_type`(+sop `step`) 기준 분기.

## Work items

- [x] `BuildFromSOPUseCase` — wizard 3단계 (PR #151 + 2026-06-04 옵션 1 2단계 분리)
  - `extract_metadata`: `DocumentBlock` + personal_memory → LLM 메타 5필드 추출(node_type/name/description/category/risk_level) → 카드 그리드용 (**저장 X**)
  - `extract_detail`: `DocumentBlock` + 선택된 meta dict → LLM detail 5필드 추출(inputs/outputs/required_connections/service_type/instructions) + `NodeSpecStaging` 변환 → 폼 prefill용 (**저장 X**)
  - `confirm`: 사용자 편집 결과 → `CreateDraftSkillUseCase`로 personal DRAFT (NodeDefinition 미생성)
  - 입력은 JSON 프롬프트 강제(XML 금지), category(영문 8종)/risk_level 검증, confirm 신뢰경계 격리(`E_SKILL_INVALID`)
  - `_STRUCTURED_MAX_TOKENS` 4096 → 8192 (안전망, 2단계 분리로 응답당 토큰 자체도 줄어듦)
- [x] `BuildFromIndustryDefaultUseCase` — 산업 seed JSON → `SkillNode` 검증 → `NodeDefinition` upsert (idempotent, uuid5 deterministic)
- [x] `BuildFromFunctionalDomainUseCase` — 직무 seed JSON → upsert (동일 패턴, `source_type="functional_domain"`)
- [x] seed JSON 작성
  - 산업 6종 (`seeds/industry_defaults/`): ecommerce / food / it / manufacturing / service / wholesale_retail
  - 직무 5종 (`seeds/functional_domain_defaults/`): customer_support / document_data / hr / it_ops / marketing
- [x] Modal app (`services/agents/agent-skills-builder/main.py`) — source_type 분기 + sop step(metadata/detail/confirm) 라우팅
- [x] Modal 배포 — `agent-skills-builder` `/v1/health` 200 (GCP Secret Manager 패턴, 2026-05-19 검증)
- [x] 단위 테스트 — skills_builder 116 passed (wizard 정상/실패경로 격리 + confirm instructions 전달/누락 포함)
- [x] integration test — `tests/integration/test_agent_skills_builder.py`
- [x] ADR-0017 SkillDocument 이중 저장 배선 (PR #164/#165) — `confirm`이 `instructions`(SKILL.md 본문)를 `CreateDraftSkillUseCase.execute(instructions=)`로 전달(신뢰경계 str/빈값 None 격리). 실제 GCS 저장은 use case가 주입받은 `SkillDocumentStore`(storage `GcsSkillDocumentStore`, `save()→str`)가 수행
  - [ ] **잔여**: `services/agents/agent-skills-builder/main.py`(`main.py:350` CreateDraftSkillUseCase 조립부) composition root에서 `doc_store` 주입 → GCS 저장 활성화 (미주입 시 문서 미저장, 하위호환. api_server엔 호출부 없음)

## 의존성

- `common_schemas` — `DocumentBlock`, `MemoryEntry`, `RiskLevel`, transport frames(`AgentNodeFrame`/`ResultFrame`/`ErrorFrame`)
- `skills_marketplace.application.use_cases.CreateDraftSkillUseCase` — SOP DRAFT 생성
- `skills_marketplace.domain.value_objects.NodeSpecStaging` — DRAFT 입력 계약 VO (CLAUDE.md 교차 import 허용)
- `nodes_graph.domain.ports` — `EmbedderPort`(임베딩) / `NodeDefinitionRepository`(seed upsert 경로 전용)
- `ai_agent.domain.ports.LLMPort` — SOP 추출 (`ModalLLMAdapter`, `llm-base`)
- `doc_parser` 출력 schema — `DocumentBlock`

## 완료 기준 (충족)

- SOP 1건 → wizard 추출 → 사용자 편집 → confirm → personal DRAFT 생성 ✅
- seed(산업 6 / 직무 5) → source_type별 카탈로그 upsert + 조회 ✅
- Modal 배포 + `/v1/health` 정상 ✅
