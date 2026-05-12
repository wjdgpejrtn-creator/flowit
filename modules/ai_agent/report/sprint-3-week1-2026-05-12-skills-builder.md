# ai_agent (REQ-004) Sprint 3 1주차 Skills Builder 작업 보고서 (2026-05-12)

**작업일**: 2026-05-12 (화)
**담당자**: 박아름 (Skills Builder Agent 분장)
**전일 보고서**: `sprint-3-week1-2026-05-11-skills-builder.md` 참조

---

## 1. 작업 개요

5/11 첫 작업분(PR #41 nodes_graph 카탈로그 + PR #42 BuildFromIndustryDefaultUseCase) 머지 후 후속 작업 + 5/12 daily sync 결과 반영.

박아름이 5/11 결정대로 5/13~5/17 plan을 압축 진행했으나, 5/12 추가 변경이 발생:

1. 조장 + 신정혜의 큰 push (PR #46 머지) — common_schemas SSOT 이관 + llm-base Modal app
2. 조장 카톡 합의로 baseline 재구성 — e-commerce 산업 + 직무 영역 5종
3. 박아름 브랜치 전략 확정 — REQ-004 새 sub-branch 만들지 말기
4. 가원 / 신정혜와 inter-agent 통신 계약 협의

---

## 2. 박아름 5/12 OPEN PR 3개

| # | 브랜치 | 내용 | 상태 |
|---|--------|------|------|
| **#44** | `feature/req-004-skills-builder-followup` | PR #42 후속 — uuid5(industry_code) 결합 + 부분 실패 격리 정책 | APPROVED |
| **#45** | `feature/req-004-build-from-sop-skeleton` | BuildFromSOPUseCase skeleton — LLM 의존 분리 + Mock 테스트 16건 | 리뷰 대기 |
| **#47** | `feature/req-004-skills-builder-ecommerce` | alpha (e-commerce + 5종 비활성화) + beta (직무 영역 5종 baseline) 통합 | 리뷰 대기 |

### 2.1 PR #44 — Followup (uuid5 + 부분 실패 격리)

조장이 PR #42 리뷰에서 "별도 PR 권장"한 후속 패치 2건 반영:

- **uuid5 namespace 명시 결합**: `uuid5(_NS, f"{industry_code}:{node_type}")` — 산업 간 node_type 우연 충돌 namespace 레벨 차단
- **부분 실패 격리 정책**:
  - convert 실패 (seed JSON broken) → fail-fast `E_SEED_ENTRY_INVALID`
  - embed/upsert 실패 (외부 의존성 runtime 오류) → 격리, 다른 노드 계속, `ResultFrame.failed_node_types`에 기록
  - 신규 에러 코드 `E_EMBEDDING_FAILED`, `E_UPSERT_FAILED`
- 테스트 5건 신규 (격리 시나리오 + idempotent 재실행)

조장 권고 #1 (`AgentMode.SKILL_BUILDER` enum 추가)는 본 PR 범위 외 — 황대원 common_schemas 5/12 작업으로 처리됨.

### 2.2 PR #45 — BuildFromSOPUseCase skeleton

5/16 plan 본격 구현 사전 작업. LLM 호출 부분은 LLMPort stub으로 격리해서 Mock 테스트 16건.

**흐름**:
```
DocumentBlock + personal_memory (list[MemoryEntry])
  → JSON prompt 구성 (XML 금지 — 메모리 룰)
  → LLM.generate_structured(prompt, _ExtractedSkillNodeList)
  → SkillNode 검증 + NodeDefinition 변환 + embedding
  → NodeDefinitionRepository.upsert()
  → SSE 프레임 yield
```

**구성 요소**:
- `_ExtractedSkillNode` / `_ExtractedSkillNodeList` — LLM structured output 래퍼 (Pydantic frozen)
- `_build_prompt`: personal_memory + document.blocks(text/heading/table만 필터) → JSON 직렬화 + 출력 스키마 명시
- `_convert_to_node_definition`: category DB CHECK 8영문 검증 + SkillNode 검증 + `uuid5(NS, f"sop:{document_id}:{node_type}")` deterministic
- 부분 실패 격리 정책 (embed/upsert 실패는 격리, convert 실패는 fail-fast)

**임시 의존성** (대기 중 → 5/12 황대원 push로 해소):
- `MemoryEntry` 이관: 초기엔 `from ai_agent.domain.entities import MemoryEntry` 임시 사용, shim 호환으로 그대로 동작 (정식 경로 `from common_schemas import MemoryEntry`)

**에러 코드 6종**: E_DOCUMENT_EMPTY / E_LLM_GENERATION_FAILED / E_LLM_RESPONSE_INVALID / E_NO_SKILLS_EXTRACTED / E_EMBEDDING_FAILED / E_UPSERT_FAILED.

### 2.3 PR #47 — alpha + beta 통합 (산업 + 직무 영역 baseline)

박아름 브랜치 룰(REQ-004 새 sub-branch 만들지 말기) 적용으로 원래 분리 PR 계획을 한 PR로 통합.

**alpha — e-commerce 산업 1종 추가 + 기존 5종 비활성화**:
- 신규 seed: `seeds/industry_defaults/ecommerce.json` — 5 SkillNode (cart_abandonment_recovery / order_status_notify / inventory_sync / review_collection / refund_approval)
- `BuildFromIndustryDefaultUseCase`: `_ACTIVE_INDUSTRIES = {"ecommerce"}` + `_DEPRECATED_INDUSTRIES = {기존 5종}` 분리
- 신규 에러 코드 `E_INDUSTRY_DEACTIVATED` — 비활성 호출 시 명시적 에러
- seed JSON 5종(manufacturing/service/wholesale_retail/food/it) 보존 (히스토리/복원용)

**beta — 직무 영역 5종 baseline**:
- 신규 디렉토리 `seeds/functional_domain_defaults/`
- 5 JSON 파일 × 5 SkillNode = 25개:
  - `customer_support.json` — VOC 접수/챗봇/CSAT/KB 검색/SLA
  - `it_ops.json` — 배포 승인/권한 요청/장애 페이저/비밀번호/미팅룸
  - `document_data.json` — OCR/양식 파싱/요약/번역/아카이브
  - `hr.json` — 온보딩/휴가/평가/기념일/퇴사
  - `marketing.json` — 캠페인 스케줄/리드 스코어링/A-B/이벤트/리포트
- `SkillNode` entity 확장: `source_type: Literal["sop", "industry_default", "functional_domain"]` (backward compatible)
- 신규 use case `BuildFromFunctionalDomainUseCase` — `uuid5(NS, f"functional:{domain_code}:{node_type}")` namespace 격리

---

## 3. baseline 카탈로그 최종 구성 (PR #47 머지 후)

| 차원 | 활성 | 비활성 (seed 파일 보존) | 활성 SkillNode |
|------|------|------------------------|----------------|
| 산업 | ecommerce | manufacturing / service / wholesale_retail / food / it | 5 |
| 직무 영역 | customer_support / it_ops / document_data / hr / marketing | — | 25 |
| **합계** | **활성 6개 baseline** | **비활성 5개 보존** | **30 SkillNode 활성** |

비활성 25개 SkillNode는 호출 막힘이지만 seed 파일은 보존. 추후 도메인 확장 시 활성화 가능.

---

## 4. 5/12 외부 변경사항 (박아름 영역 외)

### 4.1 황대원 push (PR #46 머지, commit `8b07881` 등)

- `packages/common_schemas/python/common_schemas/agent_protocol.py` 신규 (AgentProtocolRequest/Response)
- `agent.py`에 `MemoryEntry` + `MemoryType` SSOT 이관 (박아름 임시 import는 shim 호환으로 그대로 동작)
- `AgentState.personal_memory: list[MemoryEntry]` 필드 추가
- `IntentResult.intent` Literal에 `"build_skill"` 추가
- 박아름 합의안과 100% 일치

### 4.2 신정혜 push (REQ-011 llm-base Modal app 초기 구현)

- `services/agents/llm-base/main.py` — Gemma 4 26B-A4B + BGE-M3 colocation
- multimodal generate (text/JSON/vision 통합) — **grammar-level JSON 강제** (응답 100% parseable)
- HTTP endpoint: `/v1/embed`, `/v1/embed_batch`, `/v1/health`
- Modal RPC: `modal.Cls.from_name("llm-base", "LLMBase").generate.remote.aio(...)`
- 박아름 BuildFromSOPUseCase의 LLM endpoint 의존성 해소 진행 중 (어댑터 wiring은 5/13 신정혜)

---

## 5. 박아름 결정사항 (2026-05-12)

### 5.1 브랜치 전략 확정
- REQ별 메인 브랜치 영구 보존
- sub-branch는 머지 후 삭제
- OPEN PR 추가 작업 시 새 sub-branch X, 기존 PR 브랜치에 추가 커밋
- **REQ-004는 박아름 메인 담당 아님 — 새 sub-branch 만들지 말기**

### 5.2 baseline 5종 구성 확정
- 산업 1개 (e-commerce) + 직무 영역 5개 (customer_support / it_ops / document_data / hr / marketing)
- 기존 5종 산업은 비활성화 + seed 파일 보존
- 시장 리서치 근거 (Zapier 2021 SOBA + Workato 2022/2024) — 노션 정리 완료

### 5.3 임베딩 차원 768 유지
- BGE-M3 실제 모델은 1024차원이지만 박아름 영역에서는 768 유지
- spec / DB schema(`vector(768)`) / 박아름 코드 정합 우선
- 신정혜 어댑터(`ModalEmbeddingAdapter`)에서 어떻게 처리할지는 박아름 영역 외

### 5.4 LLM 입력 JSON 강제
- LLM 프롬프트 컨텍스트는 무조건 JSON, XML 사용 금지
- BuildFromSOPUseCase의 `_build_prompt`가 `json.dumps()` 출력
- 신정혜 llm-base가 grammar-level JSON 강제 지원 — 정합

---

## 6. 5/12 sync 결과

### 김진형 sync (DocumentBlock 인터페이스)
- `DocumentBlock`이 이미 common_schemas에 정의되어 있어 별도 확인 불필요 (코드 직접 확인 결과)
- 박아름 BuildFromSOPUseCase가 사용할 필드 다 명확 (text/heading/page_number/metadata)
- 김진형 SSOT 이관 일정은 박아름 5/16 작업과 무관 (DocumentBlock만 사용)

### 신정혜 + 햄햄 sync (agent_protocol)
- `AgentProtocolRequest` / `AgentProtocolResponse` 박아름 합의안 그대로 황대원이 common_schemas에 추가 (PR #46)
- 가원 답: LoadUserMemoryUseCase → personal_memory 매핑 합의 OK
- 가원 답: Skills Builder도 personal_memory 수신 합의 OK
- 가원 역질문: session_summary 타입 → spec(REQ-004 §2.2 line 137) `dict`로 확정

---

## 7. 테스트

| 모듈 | 테스트 수 |
|------|---------|
| ai_agent (전체) | **123 passed** |
| └ skills_builder | 89 (seed validation 57 + use case 32) |
| └ workflow_composer / personalization / orchestrator / domain | 34 |
| nodes_graph (회귀) | 109 passed |
| **합계** | **232 passed** |

회귀 0건.

---

## 8. 커밋 이력 (2026-05-12)

| Branch | Hash | 메시지 |
|--------|------|--------|
| `feature/req-004-skills-builder-followup` | `3bb3c01` | refactor(skills_builder): PR #42 리뷰 후속 — uuid5 industry_code 결합 + 부분 실패 격리 정책 |
| `feature/req-004-build-from-sop-skeleton` | `000ec72` | feat(skills_builder): BuildFromSOPUseCase skeleton (LLM 의존 분리, Mock 테스트) |
| `feature/req-004-skills-builder-ecommerce` | `41d02a2` | feat(skills_builder): e-commerce 산업 추가 + 기존 5종 비활성화 (alpha) |
| `feature/req-004-skills-builder-ecommerce` | `c77ea33` | feat(skills_builder): 직무 영역 5종 baseline 추가 (beta, PR #47에 흡수) |

---

## 9. 후속 작업

### 박아름 영역 (대기 필요)

| 작업 | 의존 |
|------|------|
| `BuildFromSOPUseCase` 본격 wiring | 신정혜 `ModalLLMAdapter` (5/13) |
| `agent-skills-builder` Modal app 배포 | Modal workspace 권한 (5/17 plan) |
| 실제 DB UPSERT 검증 | 황대원 `PgNodeDefinitionRepository` (5/15) + `ModalEmbeddingAdapter` (5/13) |
| 박아름 OPEN PR 3개 머지 후 후속 패치 | 조장 리뷰 + 머지 |

### 박아름 영역 외 (다른 멤버 작업)

| 작업 | 책임자 |
|------|-------|
| `PgNodeDefinitionRepository` 구현체 | 황대원 (REQ-008 storage) |
| `ModalEmbeddingAdapter` (BGE-M3) | 신정혜 (REQ-004) |
| `AgentMode.SKILL_BUILDER` enum 추가 | 황대원 (REQ-012) — 본 보고서 작성 시점에 미확인 |

---

## 10. 참조

- spec: `docs/specs/REQ-004-ai-agent.md` §2.1, §2.2, §10
- plan: `docs/specs/plan/sprint-3.md` §4.2 박아름 5/12~5/17
- 카탈로그 plan: `modules/nodes_graph/plan/sprint-3-catalog-plugin-discovery.md`
- 전일 보고서: `sprint-3-week1-2026-05-11-skills-builder.md`
- 박아름 결정 사항 메모리:
  - `feedback_branch_strategy.md` (브랜치 룰)
  - `feedback_embedder_dimension.md` (768 차원)
  - `feedback_llm_input_json.md` (LLM 입력 JSON 강제)
  - `feedback_spec_priority.md` (spec > plan > TASKS.md)
