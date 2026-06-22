# ADR-0024: SkillDocument 2-md 디렉토리 (노드 지침서 SKILL.md + Composer 지침서 COMPOSER.md) — 스킬 사용 모델 단일화

- **Status**: Proposed (박아름 제안자 — 조장 2026-06-05 카톡 위임). **D3·D4 토대는 [PR #374](https://github.com/billionaireahreum/Workflow_Automation/pull/374)(조장)로 선구현·머지 완료** — 본 ADR이 그 결정을 확정 문서화하며, **D2(검색 경로) + 결함 B·C(게시 재검토)는 박아름 실행 대상**으로 남는다. 4영역 합의 후 Accepted 승격.
- **Date**: 2026-06-05
- **Deciders**: @billionaireahreum (박아름, 제안자 — REQ-004 Skills Builder / REQ-013 skills_marketplace) + @dhwang0803-glitch (조장, common_schemas/storage/execution_engine) + 신정혜 (REQ-004 Composer) + 햄햄 (참고)
- **Tags**: area/skills_builder, area/skills_marketplace, area/ai_agent, layer/domain, layer/storage
- **관련 이슈**: [#372](https://github.com/billionaireahreum/Workflow_Automation/issues/372) 스킬 바인딩 결함 (본 ADR이 결함 A·B·C의 상위 설계)

## Context

REQ-013 staging 시연(2026-06-05)에서 **게시된 스킬을 워크플로우 생성에서 선택해도 구조적으로 바인딩되지 않는** 결함이 발견됐다(이슈 #372). 근본 원인은 스킬이 "워크플로우 노드"와 "LLM 노드 주입 지침서"라는 **두 정체성으로 동시 구현되어 서로를 무력화**하기 때문이다.

2026-06-05 조장 카톡으로 스킬 instructions의 본질이 재정의됐다(Q3):

> 스킬은 "돌아가는 코드"가 아니라 **① LLM 사용 노드에 주입하는 도메인 지침서** + **② 워크플로우 작성 에이전트(Composer)에 주입하는 필수 노드 선택 지침** 두 가지다.

### 현재 상태 (코드 확정, development 2026-06-05)

- **`SkillDocument`** (`common_schemas/skill_document.py`): `skill_id, name, description, instructions: str, scripts, templates`. 단일 `instructions`가 SKILL.md 본문. ADR-0017 이중 저장의 "지침서" 측.
- **저장**: `GcsSkillDocumentStore.save()`가 단일 키 `skills/{skill_id}/SKILL.md`만 씀 (`gcs_skill_document_store.py:28,44-51`). `skill_document_uri`(단일 str)에 URI 보관.
- **주입(소비)**: `execution_engine`의 `_inject_skill`이 `category=="ai"` LLM 노드 실행 시 `instructions`를 `system` 프롬프트에 병합. Composer 주입 경로는 **없음**.
- **검색**: `SearchSkillsUseCase.execute_accessible` → `SkillRepository.search(query_embedding, ...)` → `company_skills`/`personal_skills`의 **`embedding` 컬럼**(skill row 자체 임베딩)으로 top-k. **`node_definition_id`는 검색에 쓰이지 않는다.**
- **`node_definition_id`의 실제 역할**: 검색된 스킬을 *노드 후보(candidates)로 변환*하는 다리 — retriever(`composer_graph.py:692-698`), use_suggested(`:772-783`), suggest(`:737`)가 `skill.node_definition_id`로 `node_registry.get_schema()`를 호출해 `candidates`에 노드로 주입. 이 변환이 **결함 B(스킬-노드 둔갑)의 원천**.
- **스킬 정체성 3갈래**(`marketplace_skill_model.py:29-38`, 셋 다 nullable 공존): `node_definition_id`(노드) / `skill_document_uri`(지침서 GCS) / `workflow_id`(템플릿, PR #343 seed). 무엇으로 쓰는지 강제하는 제약 없음.

### PR #374 (2026-06-05 머지) — D3·D4 토대 선구현 (조장)

본 ADR 작성과 병행해 조장이 `common_schemas` + `storage` 토대를 PR #374로 구현·머지했다. 본 ADR의 D3·D4는 그 구현을 확정 문서화한다.
- `SkillDocument.composer_instructions: str = ""` 추가 + `instructions: str = ""` 완화(둘 다 optional). common_schemas 0.20.0 MINOR + TS codegen.
- `GcsSkillDocumentStore` 멀티파일 save/load/delete 구현. save() 반환 URI는 **호출부 계약 보존 위해 항상 SKILL.md URI**.
- `_inject_skill`(노드측) 무변경. 기존 스킬은 COMPOSER.md 부재 → `composer_instructions=""` degrade(역호환).

## Decision

### D1. 스킬 사용 모델 = "지침서 묶음" 단일화 (모델 A)

스킬은 워크플로우 **노드가 아니다**. 스킬은 **두 종류의 지침서(SKILL.md + COMPOSER.md)** 이며, 워크플로우 생성/실행 시점에 *기존 노드에 주입*되는 방식으로만 소비된다. 스킬을 candidates 노드로 주입하던 경로(결함 B)는 폐기한다.

### D2. (조장 Q1) 스킬 검색 경로 = **옵션 ① 스킬 자체 임베딩 + 전용 SearchSkills** ⭐

> 택1: **① 스킬 자체 임베딩 + 전용 검색(SearchSkills)** vs ② NodeDefinition 검색 경로 유지하되 candidates 주입만 제거

**① 채택.** 근거: 검색은 **이미** skill row의 `embedding` 컬럼 기반(`SearchSkillsUseCase` → `repo.search`)이고 `node_definition_id`에 의존하지 않는다. 따라서 `node_definition_id`를 폐기해도 검색 소스는 끊기지 않는다. 옵션 ②(NodeDefinition 경로 유지)는 결함 B의 둔갑 원천을 남겨 두 정체성 충돌이 재발하므로 기각.

**활성 스킬 경로 = two-shot HITL** (이게 `_build()` 그래프에 배선된 실경로):
```
search_nodes(retriever) → _suggest_skill_select_node → [유저 선택] → resume → draft → _bind_skill_node
```
> ⚠️ `_suggest_skill_node`(`:737`)·`_use_suggested_skill_node`(`:772-783`)는 `_build()`에 **미배선된 사장 코드**다 — 폐기 범위에서 활성 경로와 무관(혼동 주의, 조장 지적). 별도 정리 대상.

**폐기 범위** (단순 candidates 주입 제거로는 불충분 — 조장 지적 반영):
1. `PublishSkillUseCase._build_node_definition` + `node_def_repo.upsert` 호출 제거 (`publish_skill_use_case.py:84-90,95-114`) — 게시 시 NodeDefinition을 더는 만들지 않는다. **embedding 생성(`:74-82`)은 유지** (skill row에 채워야 검색됨). → **박아름 (결함 B·C 중 게시 측)**.
2. retriever의 `node_definition_id` 의존(검색된 스킬→candidates 노드 변환) 제거 + 선택 스킬 LLM 노드 보장(결함 A) → **PR #376(황대원 선반영, OPEN)에서 제거 완료** (development 미반영, 머지 대기). *(라인 번호는 #376 머지 시 변동되는 stale 참조라 생략)*
3. `SkillOption.node_definition_id`(common_schemas) 제거 또는 `skill_id`로 대체 → **조장 (common_schemas 영역)**. ⚠️ **D2 #1(publish NodeDefinition 생성 중단) 착수 전 선행 검증 필요**: publish가 멈추면 스킬의 `node_definition_id`가 None이 되므로, 활성 two-shot `_suggest_skill_select_node`가 옵션 제시에 그 값을 요구하지 않는지 확인해야 한다 (`SkillOption.node_definition_id`는 0.18.0에서 이미 optional이라 괜찮을 가능성 높지만 착수 전 검증 권장).
4. `company_skills.node_definition_id` 컬럼 + `idx_*_node_def` 인덱스 → **deprecated** (nullable 유지, 신규 코드 미참조. 물리 DROP은 후속 마이그레이션).
5. **embedding backfill**: PR #343 seed 5종은 SQL INSERT라 `embedding=NULL` → 검색 누락. seed에 embedding 채우는 backfill 필요(별도 작업, 본 ADR Follow-up).

### D3. (조장 Q2) SkillDocument 신규 필드 = `composer_instructions` **1개** (정정: "2필드" 아님) — ✅ PR #374 구현 완료

"md 2개"이지만 **모델 신규 필드는 1개**다. 기존 `instructions`가 SKILL.md(노드 지침서)에 1:1 대응하므로, 추가는 `composer_instructions`(COMPOSER.md 본문) 하나뿐이다. ("나머지 하나"는 없음 — 박아름 카톡의 "2필드 분리" 표현이 오해를 부른 것을 정정.)

**PR #374 구현 형태** (`common_schemas/skill_document.py`):
```python
class SkillDocument(BaseModel):
    skill_id: UUID
    name: str
    description: str
    instructions: str = ""               # SKILL.md body — 노드 주입 지침 (required→optional 완화)
    composer_instructions: str = ""      # COMPOSER.md body — Composer 주입 지침 (신규)
    scripts: list[dict] = []
    templates: list[dict] = []
```

- `instructions`는 **rename하지 않는다** (기존 데이터·코드 역호환). 의미는 "노드 지침서"로 고정.
- **둘 다 optional**: `composer_instructions`와 `instructions` 모두 default `""` — "노드 지침만 있는 스킬", "composer 지침만 있는 스킬" 모두 허용(#372 detail 3). required→optional은 더 허용적이라 역호환(MINOR, 0.20.0).
- `None` 대신 **빈 문자열 `""`** 채택(PR #374) — 부재를 `""`로 통일해 store degrade와 일관.

### D4. (조장 Q3) 멀티파일 store 계약 — ✅ PR #374 구현 완료

`SkillDocumentStore.save/load/delete`를 2파일로 확장한다.

| 파일 | 내용 | 직렬화 | 기록 조건 |
|------|------|--------|----------|
| `skills/{skill_id}/SKILL.md` | `instructions` | YAML frontmatter(name/description) + body (**기존 형식 유지**) | **항상 기록** (frontmatter가 name/description 메타 보유) |
| `skills/{skill_id}/COMPOSER.md` | `composer_instructions` | **순수 markdown body** (frontmatter 없음 — 메타는 SKILL.md만 보유) | `composer_instructions != ""`일 때만 기록 |

- **save**: SKILL.md **항상** + COMPOSER.md(composer_instructions 비어있지 않을 때만). 반환 URI = **항상 SKILL.md URI** (호출부 `skill_document_uri` 계약 보존). 본 ADR 초안의 "디렉토리 prefix 전환" 제안은 **철회** — `load()`가 URI가 아니라 `skill_id`로 키를 구성하므로 prefix 전환은 실익 없이 `skill_document_uri` 소비처 churn만 유발(조장 PR #374 as-built 채택). 빈 `composer_instructions` 재저장 시 stale COMPOSER.md 정리(commit `90d1755`).
- **load**: SKILL.md 부재 시 `load`가 **즉시 `None` 반환**(COMPOSER.md 확인 안 함, as-built). COMPOSER.md 부재 시 `composer_instructions=""` degrade.
- ⚠️ **그래서 SKILL.md를 생략하면 안 된다** — COMPOSER.md만 있는 스킬을 만들려고 SKILL.md를 빼면 `load`가 `None`이 되어 `composer_instructions`가 영구 유실된다. SKILL.md는 메타(frontmatter) 보유 차원에서 **항상 기록**해 이 트랩을 회피한다(`instructions=""`여도 SKILL.md 자체는 씀).
- **delete**: SKILL.md + COMPOSER.md 둘 다 정리(멱등) — `DeletePersonalSkillUseCase` orphan 경로.

### D5. 주입 경로 (소비)

| 지침서 | 소비 모듈 | 소비 시점 | 메커니즘 |
|--------|----------|----------|----------|
| SKILL.md (`instructions`) | execution_engine | 워크플로우 **실행** | `_inject_skill`이 LLM 노드 `system`에 병합 (**기존 유지**) |
| COMPOSER.md (`composer_instructions`) | ai_agent Composer | 워크플로우 **생성** | drafter가 노드 선택/구성에 반영 (**신규** — #372 결함 A 해소) |

**COMPOSER.md 로더 배선** — ✅ **PR #411 머지(2026-06-08)로 완료.** 아래 설계 예측 중 일부는 실제 구현에서 바뀌었다(기록 보존):
1. **로더 주입** — (예측: 스코프 횡단 `GetSkillDocument` use case 경유, `domain/ports` 직접 금지) → **실제: `SkillDocumentStore` Port를 ai_agent Composer가 직접 import**해 런타임 소비(`composer_graph._drafter_node`가 선택 `skill_id`로 `load()`). execution_engine과 동일한 런타임 DI 패턴 — Port ABC만 참조 + 구현체(`GcsSkillDocumentStore`)는 composition root 주입이라 Clean Architecture 정합. CLAUDE.md 교차 import 표에 `ai_agent → skills_marketplace.domain.ports.SkillDocumentStore` 행 추가(**PR #413, 박아름**).
2. **drafter hook** — `DrafterService.draft(skill_composer_instructions=...)` 전달 (신정혜, #411 `b41d20a`). #376이 준비한 hook 재사용.
3. **컨테이너 배선** — `agent-composer` composition root에서 `skill_doc_store` 주입 완료 (박아름, #411 `6db6207`). `SKILLS_MARKETPLACE_BUCKET` secret은 공용 SA(`cloudsql-iam-modal`)가 이미 accessor 보유 → 인프라 추가 작업 0(조장 확인).

## 영역 분담

| 작업 | 영역 | 상태 |
|------|------|------|
| `SkillDocument.composer_instructions` 추가 (7단계 체크리스트) | common_schemas (조장) | ✅ **PR #374 머지** |
| `GcsSkillDocumentStore` 멀티파일 save/load/delete | storage (조장) | ✅ **PR #374 머지** |
| `_inject_skill` (SKILL.md 노드 주입, 유지) | execution_engine (조장) | ✅ 무변경(유지) |
| retriever `node_definition_id` 의존 제거(결함 B) + 선택 스킬 LLM 노드 보장(결함 A) | ai_agent Composer (**황대원 선반영 #376 · 신정혜 소유**) | 🔵 **PR #376 OPEN** |
| COMPOSER.md 로더 주입 + drafter hook 배선(`skill_composer_instructions`) + composition root | ai_agent Composer (신정혜 `b41d20a` + 박아름 `6db6207`) | ✅ **PR #411 머지** |
| `SkillOption.node_definition_id` 제거/`skill_id` 대체 (D2 #3) | common_schemas (조장) | ⏳ 대기 |
| (선행 검증) publish NodeDef 생성 중단(D2 #1) 전 `_suggest_skill_select_node`가 옵션 제시에 `node_definition_id` 미요구 확인 (0.18.0 optional이라 likely OK) | skills_marketplace (박아름) | ⏳ D2 #1 착수 전 |
| `PublishSkillUseCase` NodeDefinition 생성 제거 + embedding 유지(결함 B 게시측) | skills_marketplace (박아름) | ⏳ 대기 (본 ADR Accepted 후) |
| 빌더가 SKILL.md + COMPOSER.md 2-md 합성 (추출 계약 재설계) | ai_agent skills_builder (박아름) | ⏳ 대기 |
| `category="action"` placeholder 재검토(결함 C — D1로 자연 무의미화) | skills_marketplace (박아름) | ⏳ 대기 |
| PR #343 seed 2-md 전환 + embedding backfill | database/skills_marketplace (박아름) | ⏳ Follow-up |

## Consequences

### Positive
- **#372 결함 일괄 해소**: COMPOSER.md가 필수 노드를 명시 → 결함 A(drafter LLM 노드 누락) 해소. `node_definition_id` 폐기 → 결함 B(노드 둔갑) 소멸. 스킬 정체성이 "지침서 디렉토리"로 수렴 → 결함 C(category=action placeholder) 무의미화.
- **관심사 분리**: 실행 시(노드) vs 생성 시(composer) 지침이 파일·필드로 분리 → 양쪽 프롬프트 노이즈 제거.
- **외부 SkillsMP 호환 유지**: SKILL.md 형식 불변. COMPOSER.md는 디렉토리 추가 파일이라 export 호환.
- **검색 인프라 재사용**: skill embedding 검색이 이미 존재 → 검색 계층 변경 0.

### Negative / Trade-offs
- **빌더 합성 부담 증가**: Gemma가 md 2개 합성(특히 COMPOSER.md는 노드 카탈로그 지식 필요). Q2(Gemma 유지)라 품질 리스크는 별도 검증(Q5).
- **common_schemas SSOT 변경**: 7단계 체크리스트 + TS codegen. (단 nullable 추가라 MINOR)
- **node_definition_id 폐기 파급**: 인덱스·컬럼 deprecated, PR #343 seed embedding backfill 필요.
- **Composer 주입 경로 신규**: drafter가 COMPOSER.md를 노드 구성에 반영하는 로직은 미구현 — 신정혜 영역 신규 작업.

### Follow-ups
- ✅ common_schemas `composer_instructions` 추가 (조장) — **PR #374 머지**
- ✅ `GcsSkillDocumentStore` 멀티파일 save/load/delete (조장) — **PR #374 머지**
- 🔵 Composer 결함 A·B (retriever `node_definition_id` 제거 + LLM 노드 보장) — **PR #376 OPEN (신정혜)**
- ✅ COMPOSER.md 로더 주입 + drafter hook 배선 + composition root (신정혜 `b41d20a` + 박아름 `6db6207`, D5) — **PR #411 머지**
- ⏳ `PublishSkillUseCase` NodeDefinition 생성 제거 + `category="action"` 재검토 (박아름, D2 결함 B·C)
- ⏳ 빌더 2-md(SKILL.md + COMPOSER.md) 추출 계약 재설계 (박아름, D3)
- ⏳ PR #343 seed 5종 2-md 전환 + embedding backfill (박아름)
- ⏳ ADR-0017 §2 "이중 저장" → 본 ADR로 부분 대체 표기 (NodeDefinition 측 폐기 반영)
- ⏳ Q5 검증: 노드당 instructions ~2,000토큰 시 `llm-base` n_ctx/max_tokens=8192 honor 여부 — 실측 후 instructions 별도 패스 분리 필요 시 재논의

**셀프 3축 리뷰 반영 (PR #377 코멘트):**
- 🔴 **REQ-013 spec 갱신 — `SkillDocument` 필드에 `composer_instructions` 추가** (spec L59가 PR #374 0.20.0 미반영, SSOT drift) — 조장(REQ-013 spec)
- 🔴 **REQ-013 spec 갱신 — D2 폐기로 L58/L93/L123 절 정정** (`PublishSkillUseCase`의 "staging→NodeDefinition 생성·upsert + node_definition_id 연결" / "NodeDefinition 메타=skills_marketplace 테이블" 흐름이 D2로 폐기됨) — 박아름(D2 게시측과 동시)
- 🟡 **기존 published 스킬의 NodeDefinition 잔재 정리** — D2는 publish의 *신규* 생성만 멈추므로, 이미 `node_definitions` 카탈로그에 생성된 스킬 NodeDefinition은 남아 retriever 일반 노드 검색에 잡힐 수 있음(결함 B 잔재). 정리/마이그레이션 필요 — 박아름
- ✅ **CLAUDE.md 교차 import 표 보강** — 실제 배선이 `SkillDocumentStore` Port 직접 참조라 `ai_agent → skills_marketplace.domain.ports.SkillDocumentStore` 행 + Port docstring 정정 — **PR #413(박아름)**

## Alternatives Considered

### A. 옵션 ② — NodeDefinition 검색 경로 유지, candidates 주입만 제거
- 장점: publish/DB 변경 최소.
- 단점: `node_definition_id`(노드 정체성)가 남아 결함 B의 둔갑 원천 유지 → 두 정체성 충돌 재발 가능. 검색이 어차피 skill embedding이라 NodeDefinition을 남길 실익 없음.
- **기각** (조장 지적: "candidates 주입 제거만으로는 안 됨").

### B. 단일 `instructions`에 `## For Composer` 섹션 구분
- 장점: 모델 필드·store 변경 0.
- 단점: 두 소비자(execution_engine 실행 / composer 생성)가 한 문서를 파싱·필터해야 함. 섹션 누락·오염 위험. 파일 분리가 관심사 경계와 정합.
- **기각**.

### C. 본 결정 — 2-md 디렉토리 + node_definition_id 폐기 + composer_instructions 1필드
- ✅ 채택.

## References

- [ADR-0017](./ADR-0017-skills-builder-skill-document-dual-storage.md) — Skills Builder 이중 저장 (본 ADR이 NodeDefinition 측 부분 대체)
- [ADR-0020](./ADR-0020-skills-builder-publish-lifecycle-gate.md) — 게시 lifecycle 게이트 (PUBLISHED 시 NodeDefinition 생성 → 본 ADR로 제거)
- 이슈 #372 — 스킬 바인딩 결함 (결함 A·B·C)
- 조장 카톡 2026-06-05 — Q1~Q5 답변 + 2-md 디렉토리 제안
- `docs/specs/REQ-004-ai-agent.md`, `docs/specs/REQ-013-skills-marketplace.md` — 본 ADR 적용 후 spec 갱신
