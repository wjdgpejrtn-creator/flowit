# ADR-0028: 스킬빌더 에이전트화 — 툴 정의 + 온톨로지 결정적 스켈레톤 조립(read 경로)

- **Status**: Proposed (박아름 제안자 — REQ-004 Skills Builder / REQ-013 skills_marketplace). 조장(@dhwang0803)·신정혜 리뷰 후 Accepted 승격.
- **Date**: 2026-06-10
- **Deciders**: @billionaireahreum (박아름, 제안) + @dhwang0803-glitch (조장, 온톨로지 스키마/ETL·프레임워크) + 신정혜 (REQ-004 Composer·SkeletonAssembler 오너)
- **Tags**: area/skills_builder, area/ai_agent, layer/application, layer/domain
- **관련**: ADR-0026(온톨로지 GraphRAG·§6.6 결정적 스켈레톤), ADR-0024(SkillDocument 2-md), 이슈 #372(스킬 바인딩 결함)

## Context

조장 검토(2026-06-10 카톡)에서 현 스킬빌더의 구조적 한계가 확정됐다. 코드 검증 결과:

- **현 스킬빌더 = 고정 위저드**(`BuildFromSOPUseCase`: `extract_metadata → extract_detail → confirm`), LLM 추출 1회씩. **자율 Plan→Tool→Act→Evaluate 에이전트가 아님.**
- **LLM tool-calling 0건**(`bind_tools`/`tool_use`/`tool_choice` 전무) — 도구를 LLM이 골라 호출하는 경로 없음.
- **온톨로지(ADR-0026)는 composer/skill-builder 둘 다 대상**이나, composer read 경로(`expand_candidates`+`SkeletonAssembler`)만 채워졌고 **skill-builder read 경로는 미구현.** 박아름이 만든 `(:Skill)-[:BINDS]->(:Node)`는 **write-only**(게시 시 투영, planning에서 0건 read).
- **9섹션 SKILL.md 프롬프트**(2026-06-10 무배포 실측, Gemma 26B가 Anthropic급 생성 확인)는 **instructions 내용 층**일 뿐, "스킬이 실제로 엮이고 돌아가는가(구현)"는 별개.
- **진입점은 이미 챗 라우팅으로 배선됨**: `IntentAnalyzerService`가 발화를 `BUILD_SKILL`로 분류하고 `supervisor.py`가 skills 에이전트로 relay(복합 발화 `skill_then_compose` 포함). 그런데 **별도 스킬빌더 프론트 페이지**가 이 챗 경로를 우회하는 redundant 입구로 존재 — spec §3.1("대화 흐름 intent 라우팅, 별도 페이지 X")과 어긋남.

조장 요구: 스킬빌더를 **"사용자 의도에 맞는 스킬을 만드는 에이전트"** 로 — 툴(문서검색/업로드/추출/스켈레톤검색/조립)을 정의하고, 온톨로지를 검색 툴로 활용해 **구조적으로 valid한 스킬**을 만들어야 한다. "프롬프트만 넣는 건 에이전트가 아니다."

### 결정적 전제 — §6.6/#416 교훈

ADR-0026 측정: **soft 온톨로지/모티프 힌트는 작은 LLM(Gemma)의 구조 출력을 못 바꾼다(#416, 효과 0).** 반면 코드가 도메인 노드를 결정적으로 강제 포함하면 끊긴 워크플로우 23%→0%, qa_pass 0.45→0.75(#418). → **구조는 코드가 결정적으로 조립, LLM은 파라미터/설명만.** 스킬빌더도 동일 원칙을 따른다("스켈레톤을 프롬프트에 넣어 Gemma가 conform" 금지).

## Decision (제안)

### D1. 스킬빌더 툴 5종 정의

| # | 툴 | 상태 | 메커니즘 |
|---|----|------|----------|
| **T1** | `search_user_documents` | 🆕 신설 use case | 발화 → BGE-M3 임베딩 → `document_chunks`(vector(768), HNSW 기존) chunk hit 집계 → 문서 리스트. **임베딩 인프라 재사용, 검색 use case만 신설** |
| **T2** | `parse_document` | ♻️ 래핑 | doc_parser(REQ-006) `ParserPort` → DocumentBlock |
| **T3** | `extract_skill_candidates` | ✅ 기존 | `BuildFromSOPUseCase.extract_metadata` 재사용 |
| **T4** | `search_skeleton` | 🆕 신설 | 스킬 소스(문서+meta) → `SkeletonEntityExtractor.extract(text)` → 스켈레톤 선택 |
| **T5** | `assemble_skill` | ⚠️ 교체 | `SkeletonAssembler` 결정적 슬롯 채움 → 스킬 노드 구조. LLM은 instructions/파라미터만 |

### D2. T4/T5 = composer `SkeletonAssembler` 재사용 (in-code, Neo4j 아님)

- `SkeletonEntityExtractor.extract(text)`는 **순수 키워드 매칭**이라 발화 대신 SOP 본문+스킬 description을 먹이면 그대로 동작(수정 0).
- `SkeletonAssembler`는 **in-code `SKELETONS` 라이브러리**(8종)를 소비한다 — **Neo4j import 없음.** Neo4j의 `:Skeleton` 투영은 미러일 뿐 assembler가 쿼리하지 않는다. → **"온톨로지에서 스켈레톤 검색"의 실체 = in-code 라이브러리 소비.** skill-builder도 동일하게 in-code assembler를 재사용하며, **Neo4j skeleton 쿼리 경로는 신설하지 않는다.**
- 재사용은 **intra-module**(ai_agent application → ai_agent domain/services)이라 의존성 규칙 위반 없음.
- ⚠️ `SkeletonAssembler.assemble()`는 **`WorkflowSchema` 스캐폴드**를 반환 → skill-builder는 이를 **스킬 산출물(COMPOSER.md 구조 + 정밀 BINDS + required_connections)로 어댑팅**한다(아래 D4).

### D3. 통합 — `extract_detail`을 스켈레톤 조립으로 교체

`extract_metadata`(T3, 스킬 선택) → **T4(스켈레톤 선택)** → **T5(결정적 조립)** → `CreateDraftSkillUseCase`. 현 `extract_detail`의 자유 LLM 추출을 **스켈레톤 결정적 조립 + LLM 보강**으로 대체.

### D4. 정밀 BINDS — coarse(all ai 노드) → 스켈레톤 유래

T5 스캐폴드의 실제 노드만 스킬에 BINDS → 현 `Neo4jSkillProjector`의 "모든 ai 노드 + connection 노드" coarse BINDS를 정밀화(ADR-0026 §132 "skill-binding 정밀화" 협의건 해소). composer가 이 정밀 BINDS를 read하는지는 D2(온톨로지 read 경로)와 함께 결정.

### D5. 진입점 = 챗 `intent=build_skill`, 별도 페이지 폐지

스킬빌더 에이전트의 **유일 진입점은 AI 챗 발화**("스킬 만들어줘")다. `IntentAnalyzerService` → `BUILD_SKILL` 분류 → `supervisor.py`가 skills 에이전트로 relay(이미 배선, 무신설). **별도 스킬빌더 프론트 페이지는 폐지**(spec §3.1 복귀, redundant 입구 제거). 위저드 HITL 단계(스킬 후보 카드 선택 / detail 폼 편집)는 페이지가 아니라 **챗 안에서 relay 프레임을 inline 렌더**로 처리한다. → 입구 단일화 = 에이전트 진입점 명확화. 백엔드 로직은 동일(이미 있는 경로 재사용).

## ⚠️ 합의 필요 (Open Decisions) — 조장/신정혜 리뷰 대상

이 ADR의 핵심. 아래는 **박아름 단독 결정 불가**.

### O1. (조장) tool-calling 프레임워크 — **최우선 블로커**
T1~T5를 LLM이 골라 호출하는 planning 루프가 코드에 0건. 결정:
- **프레임**: LangGraph tool node / 자체 ReAct 루프 / orchestrator 확장 중 무엇?
- **모델 역량**: Gemma 26B가 tool-calling을 안정적으로 수행하는가? (소형 LLM 신뢰도 — 안 되면 "agentic"의 전제 붕괴)
- **오너십**: 프레임워크=조장/신정혜, 툴=박아름. composer·orchestrator에도 걸치는 프레임 결정.
- **분리 가능**: T1~T5는 use case로 **먼저** 구현(콜러블), 에이전트 루프 wrap은 프레임 결정 후.

### O2. (조장) "온톨로지 검색"의 실체 정렬
조장 멘탈모델("온톨로지에서 스켈레톤 검색")과 실제 메커니즘(**in-code `SKELETONS` 소비, Neo4j 미사용**)을 정렬. → skill-builder가 **Neo4j skeleton 쿼리를 신설할 필요가 없음**을 확인(불필요 작업 방지). Neo4j skeleton 투영의 용도/존속도 정리.

### O3. (조장) 정밀 BINDS 전환 + read 경로
coarse→정밀 BINDS 교체(D4)의 착수 주체·시점, 그리고 그 BINDS를 composer가 read하는 경로를 신설할지(현 write-only).

### O4. (신정혜) `SkeletonAssembler` 재사용/공유
skill-builder 재사용 시 composer 동작 불변 보장 + 공유 리팩토링 필요 여부. `assemble()` 반환(`WorkflowSchema`)을 skill 산출물로 어댑팅하는 책임 위치.

### O5. (신정혜) skill 산출물 ↔ composer 소비 정합
T5가 스켈레톤으로 만든 스킬 구조(COMPOSER.md)를 **composer가 그 스킬을 쓸 때 재현/소비**하는지 — ADR-0024 model A(지침서 주입)와 정합 확인.

### O6. (가원/조장) 프론트 스킬빌더 페이지 제거 + 챗 inline 렌더 (D5)
별도 페이지 폐지는 frontend 작업. 위저드 HITL(스킬 후보 카드 그리드 / detail 폼)을 **챗의 skills relay 프레임 inline 렌더**로 이관하는 책임·범위. 기존 페이지의 직접 API 호출 경로 정리(챗 경로로 단일화).

## Consequences

### Positive
- 스킬이 **구조적으로 valid**하게 생성 → "구현되느냐(생성+실행)" 직격. §6.6 결정적 조립 재사용으로 새 엔진 0.
- 정밀 BINDS 부수 해소(O3).
- 9섹션 SKILL.md(내용) + 스켈레톤 구조(구조)의 2층 완성.

### Negative / Trade-offs
- tool-calling 프레임워크 신설 부담(O1) — composer/orchestrator 걸침.
- Gemma tool-calling 신뢰도 미검증(O1).
- `SkeletonAssembler` 출력(WorkflowSchema) ↔ 스킬 산출물 어댑팅 비용(O4).

## 빌드 순서 (제안)

1. **T5+T4 결정적 스켈레톤 조립** — 박아름 영역 단독, 프레임 결정과 독립, 최대 효과. **즉시 착수 가능.**
2. **T1 문서검색 use case** — chunk 임베딩 재사용.
3. **(조장/신정혜) tool-calling 프레임** 결정 → T1~T5를 에이전트 루프로 wrap.

## References
- ADR-0026 §6.6(결정적 스켈레톤)·§132(skill-binding 정밀화) — 본 ADR이 skill-builder read 경로로 확장
- ADR-0024(SkillDocument 2-md) — COMPOSER.md가 본 ADR 스켈레톤 구조의 산출 형식
- 2026-06-10 무배포 실측(`scripts/test_skill_instructions_quality.py`) — 9섹션 SKILL.md 내용층 검증(별개)
