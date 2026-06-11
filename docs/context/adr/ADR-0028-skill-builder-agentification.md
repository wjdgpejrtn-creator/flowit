# ADR-0028: 스킬빌더 에이전트화 — 툴 정의 + 온톨로지 결정적 스켈레톤 조립(read 경로)

- **Status**: Proposed (박아름 제안자 — REQ-004 Skills Builder / REQ-013 skills_marketplace). 조장(@dhwang0803)·신정혜 리뷰 후 Accepted 승격.
- **Date**: 2026-06-10 (개정 2026-06-11)
- **개정 이력**: 2026-06-11 — **D1~D5 = Phase 1(MVP, in-code 결정적 조립)** 으로 명확화 + **D6(Phase 2 — 온톨로지 GraphRAG 생성단계 통합 고도화)** 추가. 조장 검토(온톨로지 적재 위치) 반영. SSOT 구조도 = `docs/context/skills_builder_architecture.md` §8. 신규 Open Decision O8/O9/O10.
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
| **T2** | `parse_document` | ♻️ 래핑 | doc_parser(REQ-006) `ParseDocumentUseCase`(application/use_cases) → DocumentBlock. **원시 `ParserPort` 아님** — mime 디스패치+정규화+PII 마스킹+품질게이트 파이프라인 재사용(O7 정정, 보안) |
| **T3** | `extract_skill_candidates` | ✅ 기존 | `BuildFromSOPUseCase.extract_metadata` 재사용 |
| **T4** | `search_skeleton` | 🆕 신설 | 스킬 소스(문서+meta) → `SkeletonEntityExtractor.extract(text)` → 스켈레톤 선택 |
| **T5** | `assemble_skill` | ⚠️ 교체 | `SkeletonAssembler` 결정적 슬롯 채움 → 스킬 노드 구조. LLM은 instructions/파라미터만 |

### D2. T4/T5 = composer `SkeletonAssembler` 재사용 (in-code, Neo4j 아님)

- `SkeletonEntityExtractor.extract(text)`는 **순수 키워드 매칭**이라 발화 대신 SOP 본문+스킬 description을 먹이면 그대로 동작(수정 0).
- `SkeletonAssembler`는 **in-code `SKELETONS` 라이브러리**(8종)를 소비한다 — **Neo4j import 없음.** Neo4j의 `:Skeleton` 투영은 미러일 뿐 assembler가 쿼리하지 않는다. → **"온톨로지에서 스켈레톤 검색"의 실체 = in-code 라이브러리 소비.** skill-builder도 동일하게 in-code assembler를 재사용하며, **Neo4j skeleton 쿼리 경로는 신설하지 않는다.**
- 재사용은 **intra-module**(ai_agent application → ai_agent domain/services)이라 의존성 규칙 위반 없음.
- `SkeletonAssembler.assemble()`는 **`AssembledDraft`(순수 node_type 구조 — `DraftNode`: ref+node_type, `DraftEdge`; node_id 미해소)**를 반환한다(신정혜 확인 2026-06-10). `WorkflowSchema`는 `to_workflow_schema()`로 별도 변환되며 **빌더는 사용하지 않는다**. → skill-builder는 **`AssembledDraft`를 COMPOSER.md 구조(node_type 목록 + ref/edge 배선) + 정밀 BINDS + required_connections로 매핑**한다(아래 D4). 입력은 SOP 텍스트를 `SkeletonEntityExtractor`의 "발화" 자리에 넣는 형태.

### D3. 통합 — `extract_detail`을 스켈레톤 조립으로 교체

`extract_metadata`(T3, 스킬 선택) → **T4(스켈레톤 선택)** → **T5(결정적 조립)** → `CreateDraftSkillUseCase`. 현 `extract_detail`의 자유 LLM 추출을 **스켈레톤 결정적 조립 + LLM 보강**으로 대체.

### D4. 정밀 BINDS — coarse(all ai 노드) → 스켈레톤 유래

T5 스캐폴드의 실제 노드만 스킬에 BINDS → 현 `Neo4jSkillProjector`의 "모든 ai 노드 + connection 노드" coarse BINDS를 정밀화(ADR-0026 Follow-ups §6.6 항목의 "skill-binding 정밀화(무관 스킬 오바인딩)" 협의건 해소). composer가 이 정밀 BINDS를 read하는지는 D2(온톨로지 read 경로)와 함께 결정.

### D5. 진입점 = 챗 `intent=build_skill`, 별도 페이지 폐지

스킬빌더 에이전트의 **유일 진입점은 AI 챗 발화**("스킬 만들어줘")다. `IntentAnalyzerService` → `BUILD_SKILL` 분류 → `supervisor.py`가 skills 에이전트로 relay(이미 배선, 무신설). **별도 스킬빌더 프론트 페이지는 폐지**(spec §3.1 복귀, redundant 입구 제거). 위저드 HITL 단계(스킬 후보 카드 선택 / detail 폼 편집)는 페이지가 아니라 **챗 안에서 relay 프레임을 inline 렌더**로 처리한다. → 입구 단일화 = 에이전트 진입점 명확화. 백엔드 로직은 동일(이미 있는 경로 재사용).

### D6. (Phase 2 고도화) 온톨로지 GraphRAG를 스킬 *생성* 단계로 통합

> **D1~D5 = Phase 1 (MVP)** = in-code `skeleton_library.SKELETONS`(8종 범용) + `SkeletonEntityExtractor`(키워드 매칭) 결정적 조립. 온톨로지(Neo4j)는 **생성 단계에서 읽지 않음**(D2). → **현재 구현 = Phase 1, ADR 준수.**

**D6 = Phase 2 (고도화)**: 온톨로지를 스킬 생성 단계(detail/assemble)로 확장한다. 조장 검토(온톨로지를 어디에 넣는가) 반영 — SSOT 구조도 = `skills_builder_architecture.md` §8. 세 지점:

- **(가) 도메인 ground truth 적재**: 도메인별 스켈레톤 + **제약/필수/금지 요소**를 온톨로지에 적재한다. 현재는 `(:Node)-[:REQUIRES]->(:Connection)` + `SlotSpec.required`뿐이고, 8종 스켈레톤도 도메인 무관 범용이다 — **도메인 개념·음수(금지) 제약은 신규**(스키마=O8, 적재=O9).
- **(나) 스킬 후보 임베딩 → GraphRAG 탐색 → SKILL.md**: 선택된 스킬 후보를 임베딩(BGE-M3)해 GraphRAG로 도메인·스켈레톤·제약·필수요소를 회수 → 도메인 최적화 구조를 결정 → **SKILL.md**(실행 시 LLM 주입, 도메인 규칙·제약 중심) 생성.
- **(다) composer 온톨로지 조회 → COMPOSER.md**: composer가 쓰는 **동일 Neo4j 조회 경로**(`OntologyRetrieverPort`)로 노드 구조·BINDS 후보를 선택 → **COMPOSER.md**(워크플로우 조립 지침) 생성.

**§6.6 제약 (필수)**: GraphRAG 회수 결과를 LLM 프롬프트 *힌트*로 주입하면 효과 0(#416, 측정 확정). 반드시 **"결정적 구조 선택"에 사용**하고 LLM은 파라미터/설명만 — Phase 1 §6.6 원칙을 Phase 2에 그대로 적용한다.

**D2와의 관계**: D2("skill-builder는 Neo4j skeleton 쿼리 신설 안 함")는 **Phase 1 MVP 결정**이며 D6는 **번복이 아니라 후속 단계**다. Phase 1 in-code 결정적 조립은 그대로 유지(폴백)하고, Phase 2에서 온톨로지 조회 경로를 *추가*한다.

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

### O4. (신정혜) `SkeletonAssembler` 재사용/공유 — ✅ **RESOLVED (2026-06-10 신정혜)**
- **재사용 OK**: `SkeletonAssembler`를 그대로 재사용하고 composer는 안 건드린다.
- **assembler에 skill 전용 메서드 추가 금지** — 단일 책임 흐려짐. **어댑팅은 빌더 쪽**에서.
- `assemble()` 반환은 `WorkflowSchema`가 아니라 **`AssembledDraft`(순수 node_type)** → 빌더가 이걸 받아 COMPOSER.md + 정밀 BINDS로 매핑(D2/D4 정정 반영).

### O5. (신정혜) skill 산출물 ↔ composer 소비 정합 — ✅ **RESOLVED (2026-06-10 신정혜)**
**`skeleton_library.py`의 `SKELETONS`가 SSOT** (ETL·assembler가 같은 상수 소비, drift 방지). 빌더도 같은 `SKELETONS`를 보면 **"빌더가 결정적으로 짠 스킬 구조" = "composer가 그 스킬로 만드는 구조"** 가 정합. ADR-0024 model A 일관.

### O6. (가원/조장) 프론트 스킬빌더 페이지 제거 + 챗 inline 렌더 (D5)
별도 페이지 폐지는 frontend 작업. 위저드 HITL(스킬 후보 카드 그리드 / detail 폼)을 **챗의 skills relay 프레임 inline 렌더**로 이관하는 책임·범위. 기존 페이지의 직접 API 호출 경로 정리(챗 경로로 단일화).

### O7. (박아름/김진형) T2 doc_parser 크로스모듈 import 신설 — ✅ **RESOLVED (2026-06-11)**
T2 `parse_document`는 ai_agent → doc_parser 크로스모듈 import를 신설한다. **결정: 원시 `ParserPort`(domain/ports)가 아니라 `ParseDocumentUseCase`(application/use_cases)를 래핑한다.** 이유 = 원시 ParserPort를 쓰면 mime 디스패치·정규화·**PII 마스킹**·품질게이트를 빌더가 재구현해야 하고, 특히 PII 마스킹이 빠지면 SOP 개인정보가 LLM 추출로 새는 **보안 회귀**가 된다. `application/use_cases` 교차 import는 규칙상 허용(이미 `ai_agent → skills_marketplace.CreateDraftSkillUseCase` 선례, CLAUDE.md 표 등재). 조치:
- **CLAUDE.md "modules 간 허용 import" 표에 행 추가 完** (`ai_agent → doc_parser application/use_cases`).
- 구현체(`ParseDocumentUseCase`에 주입되는 parsers/normalizer/pii/quality_gate)는 **api_server/Modal composition root 주입** — 빌더는 use case 인스턴스만 받는다(직접 호출 아님).
- **doc_parser 오너 김진형(REQ-006) 통지 필요** (잔여 — 사후통지: scope=새 소비자 1건, doc_parser 코드 무변경).

### O8. (조장) ground truth 온톨로지 스키마 명명 — Phase 2 (D6-가)
도메인 레이어 노드/관계 신규. **제안(미확정)**: `(:Domain)-[:USES_SKELETON]->(:Skeleton)` / `(:Domain)-[:REQUIRES_NODE]->(:Node)` / `(:Domain)-[:FORBIDS]->(:Node)`. ⚠️ 기존 `REQUIRES`(Node→Connection)와 의미 충돌 회피 위해 도메인 필수는 **`REQUIRES_NODE`로 분리**. 음수 제약(`FORBIDS`)은 현재 온톨로지에 전무 — 신규 도입. 라벨/관계 최종 명명은 조장(온톨로지 스키마 오너) 확정.

### O9. (조장) ground truth 적재 ETL 책임·시점 — Phase 2 (D6-가)
도메인 스켈레톤·제약·필수요소 데이터의 **소유 모듈**과 **적재 ETL 책임·실행시점**. 현재 `scripts/build_ontology.py`가 최상위 스크립트라 계층/실행시점 모호. ground truth 데이터를 어디(seed JSON? DDL? common_schemas?)에 두고 누가 ETL을 돌리는지 확정 — 기존 노드/스켈레톤 투영과 동일 파이프라인 확장 가능.

### O10. (조장/신정혜) OntologyRetrieverPort 확장 — Phase 2 (D6-나/다)
현재 `OntologyRetrieverPort.expand_candidates(seed_node_types)`는 **node_type seed 기반**. Phase 2는 **스킬 후보(텍스트/임베딩)로 도메인·스켈레톤·제약을 회수**해야 함 → 포트 메서드 신설 필요(예: `retrieve_domain_skeleton(embedding)`). composer가 이미 이 포트를 쓰므로(composer↔skill-builder 비대칭 해소 지점) 확장 시그니처는 **양쪽 공용**으로 설계. ai_agent 소유 포트라 의존성 위반 없음(구조도 §8 모듈경계 점검 — application이 DI).

## Consequences

### Positive
- 스킬이 **구조적으로 valid**하게 생성 → "구현되느냐(생성+실행)" 직격. §6.6 결정적 조립 재사용으로 새 엔진 0.
- 정밀 BINDS 부수 해소(O3).
- 9섹션 SKILL.md(내용) + 스켈레톤 구조(구조)의 2층 완성.

### Negative / Trade-offs
- tool-calling 프레임워크 신설 부담(O1) — composer/orchestrator 걸침.
- Gemma tool-calling 신뢰도 미검증(O1).
- `SkeletonAssembler` 출력(`AssembledDraft`) ↔ 스킬 산출물(COMPOSER.md/BINDS) 매핑 비용(O4 해소, 빌더 쪽 어댑팅).

## 빌드 순서 (제안)

1. **T5+T4 결정적 스켈레톤 조립** — 박아름 영역 단독, 프레임 결정과 독립, 최대 효과. ✅ **착수 완료(2026-06-10)**:
   - T4 = `BuildFromSOPUseCase.extract_detail`이 SOP 텍스트(메타 name/description + 문서 본문)를 `_build_skill_utterance`로 합성해 `SkeletonAssembler.assemble("발화")`에 주입(추출기 무수정 재사용, D2).
   - T5 = `SkeletonComposerMapper`(신규 순수 도메인 서비스) — `AssembledDraft` → COMPOSER.md 본문(결정적) + 정밀 BINDS(`bound_node_types`, 스캐폴드 실노드). O4 "빌더 쪽 어댑팅" 지점.
   - 통합 = `extract_detail`의 자유 LLM `composer_instructions`를 스켈레톤 매칭 시 결정적 산출로 대체(미매칭 시 LLM 폴백). `skeleton_name`/`bound_node_types`를 페이로드 노출(영속화·projector 정밀화는 O3 후속).
   - 재사용은 intra-module(ai_agent application → ai_agent domain/services)이라 의존성·CLAUDE.md import 표 변경 0.
2. **T1 문서검색 use case** — chunk 임베딩 재사용. ✅ **착수 완료(2026-06-10)**:
   - `SearchUserDocumentsUseCase`(application/skills_builder) — 발화 → `EmbedderPort.embed`(BGE-M3 재사용) → `UserDocumentSearchPort.search_chunks_by_embedding`(chunk-level 적중) → use case가 `parent_document_id`로 **문서 단위 집계**(`DocumentHit`: best_distance·chunk_hit_count, 랭킹·관련성 컷).
   - `UserDocumentSearchPort`(domain/ports) + `DocumentChunkHit`/`DocumentHit`(domain/value_objects) 신설. 소비자(ai_agent) 소유 포트, **storage 어댑터(`document_chunks` pgvector HNSW 쿼리)는 조장 후속**(AgentMemoryRepository·SkillRepository와 동일 분담). 인가=`documents.user_id` 스코프(IDOR 차단, 포트 docstring 명세).
   - 임베딩 인프라(vector(768) HNSW 인덱스 `006_doc_parser.sql`)·EmbedderPort 재사용 — 신설 0. 테스트 6건.
3. **T2 문서파싱 use case** — doc_parser `ParseDocumentUseCase` 래핑. ✅ **착수 완료(2026-06-11)**:
   - `ParseUserDocumentUseCase`(application/skills_builder) — `execute(file_path, FileMeta) → DocumentBlock`. doc_parser use case에 위임하고 산출 튜플 중 DocumentBlock만 통과(QualityGateResult 폐기 — 품질 강제는 호출자/O1 정책). PII 마스킹·정규화·mime 디스패치·품질게이트는 doc_parser 내부 수행(재구현 0).
   - 파싱 예외(미지원 mime `E0201`, 손상 `E0202` 등)는 삼키지 않고 전파 — 에이전트 루프 wrap이 ErrorFrame 변환. 콜러블 툴(SSE 프레임 미생성, T1과 동일 패턴).
   - O7 RESOLVED: ParserPort가 아닌 `ParseDocumentUseCase` 래핑(보안). CLAUDE.md import 표 행 추가. 김진형 통지 잔여.
   - 테스트 5건(위임·PII 마스킹 통과·QA 폐기·예외 전파). domain+application 480 passed, ruff clean.
4. **(조장/신정혜) tool-calling 프레임** 결정 → T1~T5를 에이전트 루프로 wrap. **T1~T5 콜러블 use case 전부 완료** — 남은 건 O1 프레임 위 wrap뿐.

### Phase 2 (D6 — 온톨로지 GraphRAG 고도화) — O8/O9/O10 합의 후 착수

B. **ground truth 적재** — 도메인 스켈레톤 + 제약/필수/금지 노드 ETL. 조장(온톨로지 스키마·ETL) 협업 (O8/O9).
C. **skill-builder GraphRAG 배선** — `OntologyRetrieverPort`(확장본, O10)를 `BuildFromSOPUseCase`에 DI → 회수 결과를 **결정적 구조 선택**에 반영(§6.6 준수), in-code 결정적 조립은 폴백 유지. 박아름 영역(application DI, 의존성 위반 0).
D. **COMPOSER.md 온톨로지 기반화** — composer 온톨로지 조회로 COMPOSER.md 생성(D6-다). 박아름 + composer(신정혜) 정합.

> Phase 1(T1~T5)과 독립이 아니라 **그 위에 얹는다** — Phase 1 결정적 조립이 폴백이므로 Phase 2 미완성 상태에서도 빌더는 동작한다(점진 고도화).

## References
- ADR-0026 §6.6(결정적 스켈레톤)·Follow-ups(skill-binding 정밀화) — 본 ADR이 skill-builder read 경로로 확장
- ADR-0024(SkillDocument 2-md) — COMPOSER.md가 본 ADR 스켈레톤 구조의 산출 형식
- `docs/context/skills_builder_architecture.md` §8 — **D6(Phase 2)의 SSOT 구조도**(온톨로지 통합 위치 + 현재 코드 갭 표 + 모듈경계 정합성 점검)
- 2026-06-10 무배포 실측(`scripts/test_skill_instructions_quality.py`) — 9섹션 SKILL.md 내용층 검증(별개)
