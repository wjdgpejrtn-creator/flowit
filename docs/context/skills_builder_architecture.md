# Skills Builder — 총체적 구조도 (현재 설계 기준)

> 작성: 2026-06-11 / 기준 브랜치: `feature/req-004-skills-builder` (development 머지 후, #483 포함)
> 담당: 박아름 (REQ-004 Skills Builder Agent / REQ-013 skills_marketplace)
> 관련 ADR: ADR-0020(게시 lifecycle·wizard), ADR-0017(SkillDocument 이중저장), ADR-0024(2-md), ADR-0026(온톨로지 BINDS), **ADR-0028(에이전트화 — 진행 중)**

이 문서는 "스킬빌더가 **지금 실제로** 어떻게 설계·구현돼 있는가"를 코드 기준으로 정리한다. 미구현/대기 항목은 상태 마크로 구분한다(✅ 가동 / ⏳ 정의만·미연결 / ❌ 없음 / 🔜 계획). **단 §8은 현재 구현이 아니라, 조장 검토를 반영한 온톨로지 고도화 목표 설계와 현재 코드 갭을 별도로 정리한다.**

---

## 0. 한 장 요약

스킬빌더는 **두 종류의 입력**(① 사용자 SOP 문서 ② 업종/직무 seed)을 받아 **personal DRAFT 스킬**을 만들고, 마켓플레이스 lifecycle(제출→승인→게시)을 거쳐 **PUBLISHED**되면 그 시점에 `NodeDefinition`(노드 카탈로그) + `SkillDocument`(GCS 지침서) + Neo4j `(:Skill)-[:BINDS]->(:Node)`(온톨로지)로 투영된다.

현재는 **고정 위저드**(metadata→detail→confirm 3단계, LLM 1회씩)다. ADR-0028은 이를 **자율 에이전트(tool-calling)** 로 전환하려는 진행 중 작업이다.

온톨로지(Neo4j) 활용은 **현재 PUBLISHED 시점의 `(:Skill)-[:BINDS]->(:Node)` 투영 중심**(생성 단계에선 미사용)이고, 조장 검토에 따라 향후 **스킬 문서 생성 단계(detail/assemble)** 에서 도메인별 스켈레톤·ground truth·GraphRAG 탐색으로 SKILL.md/COMPOSER.md를 생성하는 방향으로 고도화한다(→ §8 목표 설계).

---

## 1. 진입점 (3종, 챗 단일화 방향)

```
① AI 챗 발화 "스킬 만들어줘"   ← 정식 진입점 (spec §3.1)
     → IntentAnalyzerService 가 IntentType.BUILD_SKILL 분류
     → supervisor.py / supervisor_router 가 skills 에이전트로 relay
        (복합 발화 "문서로 스킬 만들고 바로 워크플로우까지" = skill_then_compose)

② 프론트 스킬빌더 페이지 (services/frontend/src/app/skills/builder)
     → ADR-0028 D5 가 "폐지" 방향 (redundant 입구, 챗으로 단일화)

③ api_server REST (skills.py 라우트)  ← 위 ①②가 결국 호출하는 백엔드
```

상태: ① 배선됨 ✅ / ② 존재(폐지 검토) ⏳ / ③ 가동 ✅

---

## 2. source_type 3종 + "문서 있음/없음" 분기

스킬빌더 Modal app(`agent-skills-builder/main.py`)은 `payload.source_type`으로 분기한다.

```
source_type
├── "sop"               ← 문서/seed 기반, wizard 3단계 (metadata→detail→confirm)
├── "industry_default"  ← 업종 seed JSON → 즉시 upsert (큐레이션, 리뷰 생략)
└── "functional_domain" ← 직무 seed JSON → 즉시 upsert
```

`sop` 경로는 다시 **api_server(skills.py extract)** 에서 "SOP 문서가 있나?"로 갈린다:

```
POST /api/v1/skills/extract  (skills.py:418)
│
├── ① 문서 있음:  body.source_document_id
│     → doc_repo.get_by_id()        # 이미 분석된 문서를 DB에서 읽음
│     → blocks 없으면 409 "먼저 문서 분석을 완료하세요"   ◄ 사전 분석 강제
│     → doc_repo.get_chunks()       # document_chunks 읽기 (#483)
│
└── ② 문서 없음:  body.template_code  (업종/직무 seed)
      → synthesize_sop_document()   # seed를 SOP DocumentBlock으로 "합성" (영속 X)
      → chunks = []                 # 합성이라 청크 없음 → use case 전체문서 폴백
│
└─(합류)→ DocumentBlock(+chunks) 를 payload로 skills-builder Modal 전달
```

> **핵심**: 두 갈래 **어디에도 "빌더가 파일을 즉석 파싱"하는 단계가 없다.** "있음"은 사전 분석된 DB 문서를 읽고, "없음"은 seed 합성이다.

---

## 3. 파싱은 어디서? (별도 선행 흐름)

문서 파싱은 **스킬빌더가 아니라 문서 업로드/분석 워커**가 담당한다(REQ-006 doc_parser / REQ-009).

```
사용자 SOP 파일 업로드 (POST /api/v1/documents …)
   → 분석 워커(Celery)가 GCS download
   → doc_parser ParseDocumentUseCase.execute()   ◄── 파싱은 "여기서" 1회 (PII 마스킹·정규화·품질게이트 포함)
   → repo.save(DocumentBlock) + document_chunks(임베딩 포함) 저장 (DB)
```

이 단계가 끝나야 §2의 ① 경로(`source_document_id`)에서 참조 가능하다.

상태: 가동 ✅ (documents.py:238 / README)

---

## 4. SOP wizard 3단계 (build_from_sop_use_case.py)

```
[metadata]  extract_metadata(user_id, document, personal_memory, chunks)
   → 입력 블록: chunks 있으면 청크(map-reduce 배치), 없으면 document.blocks 폴백   ← #483
   → 배치별 LLM 추출 → node_type 기준 병합·dedup
   → 메타 5필드(node_type/name/description/category/risk_level)만 (저장 X, 카드 그리드용)
        │  사용자가 카드 1건 선택
        ▼
[detail]    extract_detail(user_id, document, meta, personal_memory, chunks)
   → 선택 메타 임베딩으로 관련 청크 cosine top-k RAG (예산 절단)   ← #483
   → LLM detail 5필드(inputs/outputs/instructions/composer_instructions/...) (저장 X, 폼 prefill용)
   → T4/T5(ADR-0028):
        · 현재: SOP 텍스트를 SkeletonEntityExtractor "발화"로 결정적 스켈레톤 조립(in-code SKELETONS)
              - 매칭 성공 → SkeletonComposerMapper: COMPOSER.md(결정적) + 정밀 BINDS(bound_node_types)
              - 매칭 실패 → LLM 자유 composer_instructions 폴백
        · 목표(§8): 스킬 후보 임베딩으로 GraphRAG 탐색 → 도메인별 스켈레톤 + ground truth(제약·필수요소)
              회수 → "구조 선택"에 결정적 반영(프롬프트 힌트 아님, §6.6)
        │  사용자가 폼 편집·확정
        ▼
[confirm]   confirm(user_id, skills)
   → embed(description) + CreateDraftSkillUseCase.execute(...)
   → personal DRAFT 생성 (NodeDefinition은 아직 미생성 — Option B)
```

상태: metadata/detail/confirm 가동 ✅ / T4/T5 스켈레톤 조립 가동 ✅ (#483 청크 흐름과 공존)

---

## 5. 저장 — 이중 저장 (ADR-0017 / ADR-0024)

```
CreateDraftSkillUseCase.execute(
    name, description, node_spec_staging,         ← DB(skills 테이블)
    embedding,                                    ← pgvector (의미검색용)
    instructions,                                 ← SkillDocument SKILL.md   (실행 시 LLM 주입)
    composer_instructions,                        ← SkillDocument COMPOSER.md (워크플로우 생성 시 Composer 주입)
)
   → SkillRepository(PgMarketplaceSkillRepository) : DB 행
   → SkillDocumentStore(GcsSkillDocumentStore)     : GCS gs:// (SKILL.md + COMPOSER.md 2-md)
```

상태: 가동 ✅ (GCS 저장은 `SKILLS_MARKETPLACE_BUCKET` 주입 시 활성, 미설정 시 doc_store=None 하위호환)

---

## 6. 게시 lifecycle (ADR-0020, skills.py)

스킬빌더는 **personal DRAFT만** 만든다. team/company는 승격(promote)으로만 도달(Q3 promotion-only).

```
DRAFT ──submit──▶ PENDING_REVIEW ──approve──▶ APPROVED ──publish──▶ PUBLISHED
                                                                      │
   (archive ◀──▶ restore 는 보조 전이)                                 ▼
                                          ┌──────────────────────────────────────┐
                                          │ PUBLISHED 시점에 비로소:               │
                                          │  · NodeDefinition 생성(노드 카탈로그)   │  Option B
                                          │  · Neo4j (:Skill)-[:BINDS]->(:Node)    │  ADR-0026 Phase 2b
                                          │    투영 (Neo4jSkillProjector)          │
                                          └──────────────────────────────────────┘

promote: PUBLISHED personal → team/company 승격
```

REST 라우트(skills.py): `/extract` `/extract/detail` `/personal`(생성) `/personal/{id}`(조회·수정·삭제) `/personal/{id}/document` `/{id}/submit` `/{id}/approve` `/{id}/publish` `/{id}/archive` `/{id}/restore` `/{id}/promote` `/templates` `/review-queue` `/marketplace` …

상태: lifecycle 라우트 가동 ✅

---

## 7. ADR-0028 에이전트화 — 현재 vs 목표

| | 현재 (구현됨) | 목표 (ADR-0028) |
|---|---|---|
| 흐름 | **고정 위저드** metadata→detail→confirm, LLM 1회씩 | LLM이 툴을 골라 호출하는 **tool-calling 루프** |
| 툴 | 없음 (use case 직접 호출) | T1~T5 5종 |
| 구조 결정 | (detail에 T4/T5 결정적 조립 일부 적용) | 코드가 결정적 조립, LLM은 파라미터/설명만 |

### T1~T5 툴 상태

| 툴 | 정의 | 현 흐름 연결 | 비고 |
|----|------|------------|------|
| **T1** `search_user_documents` | ✅ use case | ⏳ **미연결** | 발화로 사용자 문서 의미검색. storage 어댑터(document_chunks 쿼리)는 조장 후속 대기 |
| **T2** `parse_document` | ✅ use case (이번 작업) | ❌ **연결 지점 없음** | §2~3 분석: 빌더는 파일을 즉석 파싱하지 않음(분석 워커 전담). **현 설계에서 호출 자리 없음 → 재검토 대상** |
| **T3** `extract_skill_candidates` | ✅ (=extract_metadata) | ✅ 가동 | 기존 위저드 1단계 재사용 |
| **T4** `search_skeleton` | ✅ | ✅ 가동 | extract_detail에 통합 |
| **T5** `assemble_skill` | ✅ (SkeletonComposerMapper) | ✅ 가동 | extract_detail에 통합 |

### 미해결(O-시리즈, 남의 결정 대기)

- **O1** (조장/신정혜): tool-calling 프레임워크 — 최우선 블로커. T1~T5 콜러블은 됐으나 에이전트 루프 wrap은 프레임 결정 후.
- **O3** (조장): 정밀 BINDS 영속화 + composer read 경로.
- **O6** (가원/조장): 프론트 스킬빌더 페이지 폐지 + 챗 inline 렌더.

---

## 8. 온톨로지(GraphRAG) 통합 위치 — 목표 설계와 현재 코드 갭

> **주의: 본 섹션은 현재 구현이 아니라 목표 설계다.** 현재 스킬빌더는 in-code `skeleton_library.py`(`SKELETONS` 8종) + `SkeletonEntityExtractor`(키워드 매칭) 기반 **결정적 조립**이며, Neo4j 온톨로지를 **생성 단계에서 읽지 않는다**(ADR-0028 D2 준수). 아래는 조장 검토를 반영해 온톨로지를 스킬 문서 *생성 경로*로 확장하기 위한 목표 설계와 현재 코드 갭이다.

조장 검토의 핵심 질문은 "온톨로지는 어디에 들어가는가"다. 답은 **PUBLISHED 시점의 `(:Skill)-[:BINDS]->(:Node)` 투영(현재 유일)에만 두지 않고, 스킬 *생성* 단계(detail/assemble)에 온톨로지 조회를 넣는 것**이다. 온톨로지는 스킬 문서 생성 파이프라인에 **세 지점**으로 통합한다.

### ① 도메인별 스켈레톤 + ground truth (필수·금지 요소)

- 스킬 문서 생성 시 **반드시 들어가야 하는 구조**를 **도메인별 스켈레톤**으로 정의하고, 도메인별 **제약사항·필수요소·금지요소**를 **ground truth**로 온톨로지에 적재한다. → LLM이 구조를 자유롭게 상상하지 않도록 도메인별 "정답 구조"를 그래프가 보유한다.

**현재 실재하는 Neo4j 스키마** (조사 기준 — 이게 출발점):
```
(:Node)-[:REQUIRES]->(:Connection)                          # 노드 필수 연결(google, slack…)
(:Node)-[:IN_CATEGORY]->(:Category)
(:Node)-[:CAN_FOLLOW]->(:Node)                              # 휴리스틱 후행 호환
(:Skeleton)-[:HAS_SLOT]->(:SlotSpec)-[:FILLED_BY]->(:Node)  # 8종 범용 스켈레톤
(:Skill)-[:BINDS]->(:Node)                                  # 게시 시 투영
```
→ ground truth 측면에서 현재 있는 건 `REQUIRES`(필수 연결) + `SlotSpec.required`(슬롯 필수)뿐. **도메인 개념·도메인 제약·금지(음수) 제약은 없다.** 8종 스켈레톤도 도메인 무관 범용 모티프다.

**확장 제안(미확정 — 실제 명명은 조장/신정혜 합의 필요)**: 기존 `:Skeleton`/`:SlotSpec` 위에 도메인 레이어를 얹는다.
```
(:Domain)-[:USES_SKELETON]->(:Skeleton)   # 도메인별 권장/필수 스켈레톤
(:Domain)-[:REQUIRES]->(:Node)            # 도메인 필수 노드/요소 (또는 SlotSpec.domain 속성)
(:Domain)-[:FORBIDS]->(:Node)             # 음수 제약 (현재 전무 — 신규)
```
> ⚠️ `:Domain`/`:FORBIDS`는 **현재 코드에 없는 신규 제안**이다. 기존 `REQUIRES`(Node→Connection)와 의미가 겹치지 않게 명명을 정리해야 한다(예: 도메인 필수는 `REQUIRES_NODE`로 분리).

### ② 스킬 후보 임베딩 → GraphRAG 탐색 → SKILL.md 생성

- metadata 단계에서 사용자가 **선택한 스킬 후보를 임베딩**한다(BGE-M3, `EmbedderPort` 재사용).
- 그 임베딩으로 **GraphRAG 탐색**을 돌려 관련 도메인·스켈레톤·제약·필수요소(①의 ground truth)를 회수한다.
- 회수 결과로 **도메인 최적화 구조를 결정**하고, 그에 맞춰 **SKILL.md(실행 시 LLM 주입 지침서 — 도메인 규칙·실행 제약 중심)** 를 생성한다.

> ⚠️ **§6.6 제약 (필수 준수)**: ADR-0026 §6.6은 *"soft 온톨로지 힌트를 LLM 프롬프트에 주입해도 작은 LLM(Gemma)은 구조를 안 바꾼다 — 효과 0(#416). 코드가 결정적으로 강제해야 qa_pass 0.45→0.75"* 를 측정으로 못박았다. 따라서 GraphRAG 회수 결과는 **(a) LLM 프롬프트 힌트로만 주입하면 효과 0(금지)**, **(b) 어떤 스켈레톤/노드를 결정적으로 박을지 "구조 선택"에 써야 정합**하다. → **GraphRAG는 결정적 구조 선택에, LLM은 여전히 파라미터/설명만.**

### ③ composer가 쓰는 온톨로지 조회로 워크플로우 구조 선택 → COMPOSER.md

- 워크플로우 조립을 위해, **해당 스킬을 워크플로우로 만들 때 선택돼야 하는 노드 구조·BINDS 후보**를 **composer가 사용하는 동일 온톨로지(Neo4j) 조회 경로**(`OntologyRetrieverPort.expand_candidates` 등)로 선택한다 → 산출물 = **COMPOSER.md**.
- → **SKILL.md** = 도메인 지식/제약/필수요소(①) 중심 / **COMPOSER.md** = 워크플로우 조립용 노드 구조·BINDS·스켈레톤 탐색 결과 중심. 둘은 **같은 온톨로지의 다른 측면**을 본다.

> 📌 **인프라 = Neo4j 1개 인스턴스·1개 database (확인 완료 2026-06-11)**: 코드/terraform 직접 확인 — composer(`Neo4jOntologyAdapter`)·skill publish(`Neo4jSkillProjector`)가 **같은 Neo4j 1개**(`neo4j-uri`/`username`/`password` secret 1세트, 두 adapter 모두 `driver.session()`에 `database` 파라미터 없음=default db)를 공유하고 `skeleton_library.SKELETONS`가 양쪽 SSOT다. 조장이 언급한 "처음 2개 별도 파이프라인"은 **DB 2개가 아니라 투영 경로 2개**(정적 카탈로그 배치 ETL `scripts/build_ontology.py` + 게시 시 실시간 훅 `Neo4jSkillProjector`)를 뜻한 것으로 확인됨 — **DB는 1개**. → "같은 Neo4j 1개 공유"는 코드상 정확. node_type 어휘 SSOT(`SKELETONS`) 공유 필요(COMPOSER.md ↔ composer 정합).

### 도식

```
사용자 선택 문서 → 스킬 후보 추출
        │
        ▼ 임베딩
   ┌────────────────────── 온톨로지 (GraphRAG / 그래프 DB) ──────────────────────┐
   │  ① 도메인별 스켈레톤 라이브러리 (필수 구조) + ground truth(제약·필수요소)        │
   │                                                                            │
   │  ② 스킬 후보 임베딩으로 GraphRAG 탐색                                         │
   │       → 도메인 최적화 구조 ──────────────▶ SKILL.md (LLM 지침서)              │
   │                                                                            │
   │  ③ composer가 쓰는 동일 온톨로지 조회로 워크플로우 구조 선택                   │
   │       → 조립 구조 ───────────────────────▶ COMPOSER.md (Composer 지침서)     │
   └────────────────────────────────────────────────────────────────────────────┘
```

### 현재 코드 상태와의 갭 (= 고도화 작업 내용)

| 박아름 설계 | 현재 코드 | 갭 |
|------------|----------|----|
| ① 도메인별 스켈레톤 + **ground truth(제약·필수요소)** | `skeleton_library.py`의 in-code `SKELETONS`(구조만) | **ground truth(도메인 제약/필수요소) 레이어 없음** — 스켈레톤에 구조는 있으나 "이 도메인은 무엇을 반드시/금지" 규칙층 미존재 |
| ② 스킬 후보 임베딩 → **GraphRAG 탐색** → 도메인 최적화 | extract_detail은 SOP 텍스트를 `SkeletonEntityExtractor`(키워드 매칭)로 결정적 조립 | **임베딩 기반 GraphRAG 탐색 미적용** (composer엔 `expand_candidates` GraphRAG 있음 — ADR-0026, skill-builder 추출엔 미연결) |
| ③ composer 그래프 DB에서 구조 선택 → COMPOSER.md | `SkeletonComposerMapper`가 in-code `AssembledDraft` → COMPOSER.md | **그래프 DB 쿼리가 아니라 in-code 라이브러리 소비** (ADR-0028 D2: Neo4j 미사용, `:Skeleton` 투영은 미러) |

> **요약**: 현재는 **in-code 스켈레톤 결정적 조립**(키워드 매칭, ADR-0028 D2 준수)이고, 목표 설계는 **온톨로지에 ground truth 적재 + 스킬 후보 임베딩 GraphRAG 탐색**으로 도메인 최적화하는 것이다. 이 전환이 "고도화"의 실체다.

### 정합성 점검 (조사 결과)

- **모듈 경계 — 위반 없음 ✅**: skill-builder가 GraphRAG를 쓰는 것은 의존성 규칙 위반이 아니다. `OntologyRetrieverPort`(ai_agent 소유)를 application이 DI로 쓰면 되고(composer가 이미 동일 패턴), COMPOSER.md 생성도 `SkillDocumentStore` Port import로 허용된다. **다만 ① ground truth 적재 ETL**(`scripts/build_ontology.py`)의 책임 모듈/실행 시점이 모호 → 계층 정리 필요.
- **§6.6 제약 — 설계 성패 좌우**: GraphRAG 결과를 LLM 프롬프트 힌트로 쓰면 효과 0(이미 실패 판명). **반드시 "결정적 구조 선택"에 써야** §6.6과 정합(②의 경고 참조).
- **composer ↔ skill-builder 비대칭**: 현재 composer만 GraphRAG(`expand_candidates`)를 쓰고 skill-builder는 in-code만. skill-builder도 **같은 포트를 쓰면 비대칭이 자연 해소**된다(별도 인프라 불요).
- **ADR-0028 정합**: D2/O2("skill-builder는 in-code, Neo4j skeleton 쿼리 신설 안 함")는 **현재 MVP 결정**, 본 §8은 **다음 고도화 단계**다. 문서상 모순으로 읽히지 않게 ADR-0028에 **"D2 = MVP / §8 = 고도화 / GraphRAG는 결정적 구조 선택에만(프롬프트 힌트 금지, §6.6)"** 를 명문화해야 한다.

---

## 9. ⚠️ T2 위치 쟁점 (미결)

T2 `parse_document`는 ADR-0028 D1 표에 "doc_parser 래핑"으로 들어갔으나, §2~3에서 보듯 **현재 설계의 SOP 두 갈래(문서 있음=사전분석 DB 문서 / 문서 없음=seed 합성) 어디에도 빌더가 파일을 즉석 파싱하는 자리가 없다.** 파싱은 항상 문서 업로드/분석 워커가 선행한다.

T2가 의미를 가지려면 **"사용자가 챗 중에 파일을 즉석 업로드하면 에이전트가 그 자리에서 파싱"** 하는 O1 wrap 시나리오가 실제 설계여야 한다. 그 시나리오를 채택할지, 아니면 업로드=항상 분석 워커 선행으로 유지할지 = **박아름(설계자) 미결 판단.**

- 채택 시: T2 유지(미래 wrap에서 wiring)
- 미채택 시: T2 되돌리기(현 설계에서 dead tool)

---

## 부록 — 핵심 파일 맵

| 역할 | 경로 |
|------|------|
| Modal 라우팅(composition root) | `services/agents/agent-skills-builder/main.py` |
| api_server REST | `services/api_server/app/routers/skills.py` |
| 문서 업로드/분석 | `services/api_server/app/routers/documents.py` |
| SOP wizard use case | `modules/ai_agent/application/agents/skills_builder/build_from_sop_use_case.py` |
| seed use case | `build_from_industry_default_use_case.py` / `build_from_functional_domain_use_case.py` |
| T1 문서검색 | `search_user_documents_use_case.py` |
| T2 파싱(쟁점) | `parse_document_use_case.py` |
| T5 매퍼 | `modules/ai_agent/domain/services/skeleton_composer_mapper.py` |
| 스켈레톤 조립 | `modules/ai_agent/domain/services/skeleton_assembler.py` + `skeleton_library.py` |
| DRAFT 생성 | `skills_marketplace/application/use_cases/CreateDraftSkillUseCase` |
| 진입 분류 | `modules/ai_agent/domain/services/intent_analyzer_service.py` + `adapters/supervisor.py` |
