# ai_agent (REQ-004) Sprint 3 1주차 Skills Builder 작업 보고서

**작업일**: 2026-05-11 (월)
**담당자**: 박아름 (Skills Builder Agent 분장)
**브랜치**: `feature/req-004-skills-builder-usecase`
**HEAD 커밋**: `e543661`
**PR**: https://github.com/billionaireahreum/Workflow_Automation/pull/42
**상태**: OPEN, 리뷰 대기

---

## 1. 작업 개요

Sprint 3 plan(`docs/specs/plan/sprint-3.md` §4.2)의 박아름 5/15~5/16 작업분(LLM 비의존)을 5/11 일중에 압축 실행. LLM 의존 작업(`BuildFromSOPUseCase`)과 Modal 배포(`agent-skills-builder`)는 본 PR 범위 외 — 신정혜 `llm-base` Modal 배포(5/12 저녁) 후 진행 예정.

박아름은 Sprint 3에서 Skills Builder Agent를 추가 담당하며, 본 작업은 REQ-004 ai_agent 모듈 안의 박아름 영역(`application/agents/skills_builder/`, `seeds/industry_defaults/`, `domain/entities/skill_node.py`)에 한정.

---

## 2. 신규 산출물

### 2.1 SkillNode entity (`domain/entities/skill_node.py`)

REQ-004 spec §2.1 정의 준수. Pydantic frozen 모델.

| 필드 | 타입 | 설명 |
|------|------|------|
| `source_type` | `Literal["sop", "industry_default"]` | 추출 출처 구분 |
| `source_id` | `str` | SOP 문서 ID 또는 산업 코드 |
| `name` | `str` | 사람이 읽을 수 있는 이름 |
| `description` | `str` | 노드 설명 |
| `inputs` | `dict[str, Any]` | JSON Schema |
| `outputs` | `dict[str, Any]` | JSON Schema |
| `risk_level` | `RiskLevel` | common_schemas Enum |

### 2.2 산업 default seed 5종 (`seeds/industry_defaults/`)

각 파일 = 1 산업 = 5개 SkillNode. 총 25 SkillNode.

| 파일 | 산업명 | 핵심 노드 5종 |
|------|--------|--------|
| `manufacturing.json` | 제조 | 작업지시서 발행 / 품질검사 기록 / 출고 알림 / 불량률 리포트 / 협력사 발주 |
| `service.json` | 서비스 | 예약 확정 메일 / 노쇼 리마인드 / 후기 요청 / 멤버십 갱신 안내 / 응대 통계 |
| `wholesale_retail.json` | 도소매 | 재고 알림 / 발주 자동화 / 일일 매출 리포트 / 가격 변동 공지 / 정산서 발송 |
| `food.json` | 음식점 | 예약 알림 / 재료 발주 / 메뉴 변경 공지 / 일매출 정산 / 단골 쿠폰 발송 |
| `it.json` | IT | 배포 알림 / 장애 리포트 / PR 리뷰 요청 / 일일 빌드 상태 / 온콜 인계 |

**seed 항목 필드** (NodeDefinition 변환용 메타 포함):
- `node_type` (산업 prefix snake_case)
- `name` / `description` (한글)
- `category` (DB CHECK 영문 8종 안에서 매핑)
- `inputs` / `outputs` (JSON Schema: type=object + properties)
- `risk_level` (Low/Medium/High/Restricted)
- `required_connections` (slack/google/linear 등)
- `service_type` (snake_case 식별자)

### 2.3 BuildFromIndustryDefaultUseCase (`application/agents/skills_builder/`)

기존 skeleton 교체. 본격 구현.

**시그니처**:
```python
async def execute(
    self,
    user_id: UUID,
    industry_code: str,
) -> AsyncGenerator[SSEFrame, None]
```

**의존성**:
- `NodeDefinitionRepository` (nodes_graph.domain.ports) — DI
- `EmbedderPort` (nodes_graph.domain.ports) — DI
- `seeds_dir` (Path, 기본 `modules/ai_agent/seeds/industry_defaults`)

**흐름**:
1. `industry_code` 검증 — 5개 산업 화이트리스트
2. `{seeds_dir}/{industry_code}.json` 로드
3. 각 항목 SkillNode로 검증 → NodeDefinition 변환
4. `embedder.embed(description)` 호출 (768d BGE-M3)
5. `repo.upsert(node_def)` 호출 (idempotent)
6. `AgentNodeFrame` 진행 yield + 최종 `ResultFrame`

**Idempotency**:
- `node_id = uuid5(SKILLS_BUILDER_NS, node_type)` — deterministic
- 2회 실행해도 DB row 수 동일 (덮어쓰기)

**구분 필드**:
- `is_mvp=False` — 사용자 도메인 노드 (MVP 카탈로그와 구분)

**에러 코드 4종**:
| 코드 | 의미 |
|------|------|
| `E_INDUSTRY_NOT_SUPPORTED` | 5개 화이트리스트 외 산업 코드 |
| `E_SEED_NOT_FOUND` | seed JSON 파일 없음 |
| `E_SEED_INVALID_JSON` | JSON 파싱 실패 |
| `E_SEED_ENTRY_INVALID` | 필수 필드 누락 등 항목 검증 실패 |

---

## 3. spec 준수 사항

| spec 위치 | 준수 |
|-----------|------|
| REQ-004 §2.1 SkillNode entity 필드 7종 | ✅ 그대로 (Pydantic frozen) |
| REQ-004 §2.2 BuildFromIndustryDefaultUseCase 시그니처 | ✅ `(user_id, industry_code) → AsyncGenerator[SSEFrame]` |
| REQ-004 §10 파일 배치 `modules/ai_agent/seeds/industry_defaults/{code}.json` | ✅ 5개 산업 |
| REQ-003 `NodeDefinitionRepository.upsert()` 호출 | ✅ TASKS.md의 `.save()` 오타 spec 우선 적용 |
| DB CHECK 영문 8종 카테고리 매핑 | ✅ 모든 SkillNode `action`/`integration`/`output` |
| common_schemas SSEFrame (`AgentNodeFrame`/`ResultFrame`/`ErrorFrame`) | ✅ |

---

## 4. 테스트

| 구분 | 건수 |
|------|------|
| seed JSON 검증 | 48 |
| use case 단위 | 13 |
| **소계 (skills_builder 신규)** | **61** |
| 기타 ai_agent 회귀 | 33 |
| **전체 ai_agent** | **94 passed** |

### 4.1 seed 검증 (`test_industry_default_seeds.py`)
- 파일 존재 + JSON 로드
- 최상위 키 (industry_code / industry_name / skill_nodes ≥5)
- SkillNode 필수 필드 9종
- category DB CHECK 8영문 내
- risk_level RiskLevel enum 내
- inputs/outputs JSON Schema (type=object + properties)
- node_type 산업 prefix (충돌 회피)
- 전체 uniqueness (25종 node_type 중복 없음)
- 합계 25~35 (plan 범위)

### 4.2 use case (`test_build_from_industry_default_use_case.py`)
- 5개 산업 각각 정상 upsert + 임베딩 호출 + ResultFrame
- NodeDefinition 필드 검증 (category enum / 768d 임베딩 / JSON schema / is_mvp=False)
- Idempotency (uuid5 deterministic — 2회 실행 후 노드 수 동일)
- 에러 처리 4건 (E_INDUSTRY_NOT_SUPPORTED / E_SEED_NOT_FOUND / E_SEED_INVALID_JSON / E_SEED_ENTRY_INVALID)
- 진행 프레임 (upsert별 AgentNodeFrame)
- Embedder description 호출 확인

---

## 5. 커밋 이력

| Hash | 메시지 |
|------|--------|
| `2d96b91` | feat(skills_builder): 산업 default seed 5종 JSON 추가 (제조/서비스/도소매/음식점/IT) |
| `e543661` | feat(skills_builder): BuildFromIndustryDefaultUseCase 본격 구현 + SkillNode entity |

---

## 6. 후속 작업

### 박아름 영역 (대기 필요)

| 작업 | 의존 |
|------|------|
| `BuildFromSOPUseCase` 본격 구현 | LLM — 5/12 저녁 신정혜 `llm-base` Modal 배포 후 |
| `agent-skills-builder` Modal app 배포 | Modal workspace 권한 — 5/17 plan |

### 박아름 영역 아님 (다른 멤버 작업)

| 작업 | 책임자 | ETA |
|------|-------|-----|
| `PgNodeDefinitionRepository` (NodeDefinitionRepository ABC 구현체) | 황대원 | 5/15 |
| `ModalEmbeddingAdapter` (EmbedderPort 구현체, BGE-M3) | 신정혜 | 5/12 저녁 (`llm-base` Modal 배포 후) |
| Modal app 진입점 위치 (TASKS.md vs spec) | 조장 | sprint plan/REQ-011 추후 처리 |

→ 위 두 작업 완료 후 박아름의 `BuildFromIndustryDefaultUseCase` 실제 라이브 DB upsert 동작 가능.

---

## 7. 알려진 제약 / 가정

- Sprint 3 v1: seed 5개 산업 하드코딩. LLM 자유 생성은 v2(Sprint 4+).
- SkillNode → NodeDefinition 변환 시 `is_mvp=False` 고정 (사용자 도메인 노드 구분).
- seed JSON은 데이터 파일 — 실행 영향 없음. 검증은 단위 테스트에서.
- `BuildFromSOPUseCase`의 input(DocumentBlock)은 5/12 김진형 sync에서 필드 확정.

---

## 8. 참조

- spec: `docs/specs/REQ-004-ai-agent.md` §2.1, §2.2, §10
- plan: `docs/specs/plan/sprint-3.md` §4.2 박아름 5/15~5/16
- TASKS: `modules/ai_agent/application/agents/skills_builder/TASKS.md` (PR #41에서 spec 정합 수정)
- 관련 PR: #41 (`feature/req-003-plugin-discovery`) — 같은 박아름 Sprint 3 작업, 독립 머지 가능
