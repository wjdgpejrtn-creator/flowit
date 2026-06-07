# Plan — 온톨로지 그래프 DB + GraphRAG (composer/skill-builder 품질 고도화)

> **결정 문서**: [ADR-0026](../../context/adr/ADR-0026-ontology-graph-db-graphrag.md) · **선행 control-flow**: [ADR-0023](../../context/adr/ADR-0023-workflow-control-flow-engine.md)
> **작성**: 2026-06-06 (황대원). 본 문서는 **그래프 DB 초기 인프라 설계·구축(황대원) + 구현·고도화 핸드오프(신정혜·박아름)** 가이드다.

---

## 0. 역할 분담 (RACI)

| 작업 영역 | 소유 | 비고 |
|----------|------|------|
| **그래프 DB 초기 인프라** (AuraDB provisioning, GCP secret 3종+IAM, `OntologyRetrieverPort` ABC, `Neo4jOntologyAdapter`, `build_ontology.py` ETL, 스키마 제약) | **황대원 (조장)** | 본 문서 §1·§3 — ✅ 완료(PR #393) |
| **validator 순환 완화** (Phase 0, 하드 선행) | **황대원 선반영 (PR #392)** / 박아름 sign-off | 본 문서 §2 — 구현 완료, nodes_graph 교차소유 검토 대기 |
| **GraphRAG retrieval + 모티프 + drafter grounding** (Phase 2) | **신정혜** | 본 문서 §4 |
| **CAN_FOLLOW 엣지(노드 호환) + 모티프 `:Pattern` 시드 + 소비** (Phase 2) | **신정혜** | §4.2a — 노드 I/O 스키마 파생(스킬 무관). **composer grounding이라 박아름 비의존·자력 완결** |
| **스킬 그래프 ETL — `BINDS` + publish 훅** (Phase 2) | **박아름** | §4.2b — skill-builder grounding (별개 소비자) |
| **하이브리드 벡터 + 고도화 레버** (Phase 3) | 신정혜·박아름 | 본 문서 §5·§6 |

> 황대원은 인프라(§1·§3) + **Phase 0 validator 완화(§2)를 선반영**(PR #392, 위임이 결국 되돌아오는 패턴이라 직접 처리)했다. §4·§5·§6은 설계·계약·테스트 기준만 제공하고 실행은 담당자에게 넘긴다.

---

## 1. Phase 1 — 그래프 DB 초기 인프라 (황대원 구축 범위) — ✅ 완료 (PR #393, 라이브 검증)

> **상태(2026-06-06)**: 코드 스캐폴드 + ETL = PR #393. **실제 AuraDB Free 인스턴스로 라이브 검증 완료** — `build_ontology.py`가 제약 5건 + 노드 53건 투영, `expand_candidates` 어댑터 스모크 통과. GCP secret 3종 + Modal SA IAM 부여 완료(아래 §1.1). 남은 건 Phase 2 소비자 배선뿐.

### 1.1 AuraDB provisioning — ✅ 완료
- Neo4j **AuraDB Free** 인스턴스 1개 생성·운영 중. (AuraDB = 매니지드 Neo4j. self-host로 바꿔도 코드 무변경, secret 값만.)
- 연결 정보는 GCP Secret Manager에 **secret 3종**으로 저장(✅ 생성됨): `neo4j-uri`(`neo4j+s://...`) / `neo4j-username` / `neo4j-password`. Modal 런타임 SA `<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`에 `secretmanager.secretAccessor` 부여 완료.
- **⚠️ env 바인딩은 terraform이 아니라 Modal `load_secrets_to_env`**: composer/skills-builder는 Modal 앱이라 `boot()`에서 `services.common.gcp_secrets.load_secrets_to_env({"neo4j-uri":"NEO4J_URI", ...})`로 런타임 pull한다. terraform `secret_env`는 **Cloud Run(api/worker) 전용**이며 Modal 경로엔 안 쓴다(`deploy_image_only_terraform_owns_env`는 Cloud Run 한정). → 매핑 추가 + 재배포는 Phase 2 소비 시(§4.1).
- **AuraDB Free 운영 주의**: 72h 미사용 시 auto-pause(콘솔 resume, 데이터 보존). secret을 `:latest`로 복수 서비스가 공유하면 `secret_latency_bomb` → 버전 핀 권장.

### 1.2 온톨로지 스키마 제약/인덱스 (멱등 DDL)
```cypher
CREATE CONSTRAINT node_type_unique IF NOT EXISTS
  FOR (n:Node) REQUIRE n.node_type IS UNIQUE;
CREATE CONSTRAINT skill_id_unique IF NOT EXISTS
  FOR (s:Skill) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT connection_provider_unique IF NOT EXISTS
  FOR (c:Connection) REQUIRE c.provider IS UNIQUE;
CREATE CONSTRAINT pattern_name_unique IF NOT EXISTS
  FOR (p:Pattern) REQUIRE p.name IS UNIQUE;
```

### 1.3 `OntologyRetrieverPort` (ABC) + VO — ✅ 빌드됨 (실제 시그니처)
`modules/ai_agent/domain/ports/ontology_retriever.py` (도메인, neo4j import 없음):
```python
class OntologyRetrieverPort(ABC):
    async def expand_candidates(self, seed_node_types: list[str], hops: int = 1) -> OntologySubgraph: ...
    async def match_patterns(self, intent: str) -> list[PatternTemplate]: ...
```
VO는 `modules/ai_agent/domain/value_objects/ontology.py` (frozen dataclass, **신정혜 소비 시 이 필드를 씀**):
```python
OntologyNode(node_type, category, risk_level, requires: tuple[str,...])
OntologySubgraph(seeds, nodes: tuple[OntologyNode,...], adjacency: dict[str, tuple[str,...]])
    .allowed_node_types() -> frozenset[str]   # constrained generation 화이트리스트
PatternTemplate(name, intent, role_slots: dict[str, tuple[str,...]])
```
> common_schemas 승격이 필요하면 신정혜 협의(현재는 ai_agent 도메인 VO).

### 1.4 `Neo4jOntologyAdapter` — ✅ 빌드됨 (`ai_agent/adapters/ontology/`)
- **요청마다 driver 생성·close** 패턴 강제(`composer_modal_per_request_engine` — Modal boot≠request 루프 hang 회피). neo4j는 lazy import(extras 미설치여도 모듈 로드 가능), `NEO4J_*` env에서 연결정보, `driver_factory` 주입 훅으로 테스트.
- **Phase 1 expand_candidates 실제 범위 = seed + category sibling 1-hop** (REQUIRES/IN_CATEGORY 메타 포함). **`CAN_FOLLOW`는 아직 없음**(Phase 2 신정혜 — composer grounding). `hops` 인자는 forward-compat 예약.
- `match_patterns`는 **`NotImplementedError`** — Phase 2 신정혜가 `:Pattern` Cypher로 채움(§4.1).

### 1.5 `scripts/build_ontology.py` (멱등 ETL) — ✅ 빌드+검증됨
- 노드 소스: **`nodes_graph.application.catalog_registry.get_all_node_definitions()`** (import-only, DB 불필요) → **53노드**(executable 카탈로그). *CLAUDE.md "56종"은 toolset 14를 포함한 별개 집계 — ETL 투영 수와 다름.* Neo4j는 직접 모름 — ETL이 투영.
- 멱등 MERGE: `apply_constraints`(제약 5건) + `project_catalog`(Node/Category/Connection + REQUIRES/IN_CATEGORY).
- **스킬 `(:Skill)-[:BINDS]->(:Node)`는 미투영 (Phase 2 TODO, 박아름)** — DB 의존이라 publish 훅으로 incremental(§4.2).
- **벡터 복제 안 함** — pgvector(BGE-M3) seed 검색 유지(`skill_embedding_pipeline_gap` staleness 회피).
- 로컬 실행: `NEO4J_* env + .venv\Scripts\python.exe scripts\build_ontology.py`.

> **인프라 검증 종료선 ✅ 달성**: AuraDB 연결 + 제약 5건 생성 + 53노드 투영 + `expand_candidates` 동작 라이브 확인. **여기까지가 황대원 구축 범위(완료)** — 이후는 §4 Phase 2 소비.

---

## 2. Phase 0 — validator 순환 완화 스펙 (✅ PR #392 황대원 선반영, 박아름 sign-off 대기, 하드 선행)

> **이게 안 들어오면 §4 모티프가 무의미하다.** 엔진은 루프를 돌릴 수 있는데(PR #359 ✅) composer `validator_node`가 쓰는 `GraphValidator`가 모든 순환을 삭제한다. 그래프 DB와 **독립적으로 필요**.

### 2.1 현 상태 (✅ PR #392로 해소)
기존: `_detect_cycles`가 Kahn 알고리즘으로 **순환이면 무조건** `E_CYCLE_DETECTED`. **PR #392(황대원 선반영, OPEN)에서 아래 §2.3 스펙대로 SCC 기반 완화 + §2.4 테스트 + 조립-계층 파리티 가드를 구현 완료**. 박아름 nodes_graph sign-off 대기.

### 2.2 엔진 수용 기준 (반드시 미러할 계약)
`CyclicScheduler`(execution_engine)의 실측 수용 규칙:
- `is_brancher[instance_id] = (NodeDefinition.category == "condition")` — `execute_workflow.py:88-89`.
- non-trivial SCC(`_is_nontrivial`: 노드 ≥2개 **또는** self-loop) **마다 condition 노드 ≥1개**면 허용. 없으면 `ValidationError(E_CYCLE_DETECTED)` "탈출 불가능한 순환" — `cyclic_scheduler.py:62-66`.
- max_iterations·back-edge 분류·유한성은 **엔진 책임**(전역 `DEFAULT_MAX_ITERATIONS` 항상 존재). validator는 **존재 보장만** 검사.

### 2.3 변경 스펙 (`_detect_cycles` 교체)
무조건 거부 → **"탈출 불가능한 순환만 거부"** 로 완화. 엔진과 1:1 정합.

1. **SCC 계산** — Tarjan(또는 Kosaraju)으로 (`nodes`, `connections`) SCC 분해. *권장: `CyclicScheduler._tarjan_sccs`와 동일 알고리즘 — 추후 공용 유틸로 추출 가능(중복 주의, 별도 합의).*
2. **non-trivial 판정** — `_is_nontrivial`과 동일 의미(size>1 OR self-loop). trivial만 있으면(=DAG) `return []` (기존 비순환 동작 불변).
3. **condition 노드 존재 검사** — 각 non-trivial SCC에서 멤버 노드의 `NodeDefinition.category == "condition"` 여부 확인.
   - category 해소: `self._repo`(`NodeDefinitionRepository`, 이미 보유). **SCC 멤버 노드만** `get_by_id(node.node_id)` 또는 1회 `list_all()`로 `{node_id: category}` 맵 구성(라운드트립 절약, 엔진의 batch 방식과 동형).
   - **⚠️ async 전환**: `_detect_cycles`가 repo를 쓰므로 **async가 돼야 함**. `validate()`(line 37)에서 `await self._detect_cycles(...)`로 변경. (이미 `_check_required_connections`/`_check_required_parameters`가 async repo 패턴이라 동형.)
4. **판정**: condition 노드 없는 non-trivial SCC가 있으면 → `E_CYCLE_DETECTED`(메시지 "탈출 불가능한 순환"). 모든 non-trivial SCC가 condition 보유 → `return []`.

### 2.4 테스트 기준 (박아름)
| 케이스 | 기대 |
|--------|------|
| 비순환 DAG | passed (회귀) |
| 2-노드 순환, condition 노드 없음 | `E_CYCLE_DETECTED` |
| 2-노드 순환, 멤버 1개 `category=="condition"` | passed |
| condition 노드 self-loop | passed |
| 비-condition 노드 self-loop | `E_CYCLE_DETECTED` |
| SCC 2개 중 하나만 condition 누락 | `E_CYCLE_DETECTED` |
| **파리티 테스트(핵심)** | 동일 워크플로우 코퍼스에 대해 **`validator.validate() passed ⟺ CyclicScheduler.plan() non-raise`**. 둘이 어긋나면 composer가 통과시킨 draft가 엔진에서 죽거나(false accept) 실행 가능한데 거부(false reject) |

> 파리티 테스트가 진짜 계약이다. 공용 fixture로 양쪽을 같은 입력에 물려라.

### 2.5 주의
- `_detect_isolated_nodes`/`_check_type_compatibility`가 루프 노드를 오탐하지 않는지 회귀 확인(back-edge target이 고립으로 잡히면 안 됨).
- 이건 **nodes_graph 자기 모듈 포트만** 쓰므로 크로스모듈 의존 없음.

---

## 3. 온톨로지 스키마 (전체)

```cypher
// Phase 1 — 무손실 (build_ontology.py가 Postgres에서 투영)
(:Node {node_type, category, risk_level, service_type})
(:Connection {provider})
(:Skill {id, tier, audience})          // personal/team/company (ADR-0012)
(:Category {name})
(:Node)-[:REQUIRES]->(:Connection)
(:Node)-[:IN_CATEGORY]->(:Category)
(:Skill)-[:BINDS]->(:Node)             // 이슈 #372 바인딩

// Phase 2 — 모티프 + 휴리스틱 타입 흐름
(:Pattern {name, intent})              // quality_gate_loop, fan_out, retry_backoff, approval_gate ...
(:Pattern)-[:HAS_TEMPLATE]->(:Template)   // gen→eval→조건 back-edge/exit-edge 구조
(:Pattern)-[:USES_ROLE {slot}]->(:Node)   // generator/evaluator 슬롯에 맞는 node_type
(:Node)-[:CAN_FOLLOW {confidence}]->(:Node) // output_schema↔input_schema 휴리스틱

// Phase 3 — 하이브리드 (선택)
(:Node {embedding})  // Neo4j 네이티브 벡터 인덱스로 이관 시
```

---

## 4. Phase 2 — GraphRAG + 모티프 (신정혜·박아름 핸드오프)

### 4.1 신정혜 — composer `retriever_node` 교체 + 모티프 grounding

**착수 진입점 (구체 파일):**
- 소비 지점: `ai_agent/adapters/langgraph/composer_graph.py`(`LangGraphOrchestrator`)의 retriever 노드. 현재 `NodeRegistry.search`(pgvector)만 씀 → 그 뒤에 `OntologyRetrieverPort.expand_candidates`를 붙인다.
- DI 주입: `services/agents/agent-composer/main.py`의 `boot()`에서 `Neo4jOntologyAdapter()`를 생성해 orchestrator에 주입. **현재 미배선**(Phase 1은 dangling 방지로 안 함).

**런타임 secret 배선 (secret은 이미 생성됨 — §1.1):**
1. `agent-composer/main.py`의 `load_secrets_to_env({...})`에 추가:
   `"neo4j-uri":"NEO4J_URI", "neo4j-username":"NEO4J_USERNAME", "neo4j-password":"NEO4J_PASSWORD"`
2. `neo4j` 드라이버를 composer Modal `image.pip_install(...)`에 추가.
3. `PYTHONUTF8=1 modal deploy services/agents/agent-composer/main.py` 재배포(매핑 추가는 재배포해야 반영 — `code_change_deploy_verify`).

**GraphRAG 흐름:**
```
1. vector seed:   NodeRegistry.search (pgvector top-k, BGE-M3) → seed node_type
2. graph expand:  OntologyRetrieverPort.expand_candidates(seed)
                  → 현재(Phase 1 어댑터): seed + category sibling 1-hop (REQUIRES 메타 포함)
                  → CAN_FOLLOW 호환 확장(신정혜 §4.2a) 추가 시 강화 — 박아름 비의존
3. drafter:       OntologySubgraph.allowed_node_types() 밖 node_type/엣지 생성 금지 (constrained generation)
4. 모티프:        intent가 "검증/재생성/품질"이면 match_patterns(intent) → quality_gate_loop 템플릿
                  → role_slots(generator/evaluator)에 구체 node_type 바인딩
                  → back-edge(condition→generator) + exit-edge + condition.parameters.max_iterations 생성
```

**`match_patterns` 구현(신정혜)** — 현재 `NotImplementedError`:
- `:Pattern`/`:Template`/`USES_ROLE` 노드를 먼저 시드해야 함. **시드 = 카탈로그 node_type 기반(generator=LLM 노드, evaluator=condition 노드)이라 신정혜 자력 가능 — 박아름 비의존.** 시드 후 어댑터에 Cypher 추가: `MATCH (p:Pattern) WHERE intent 매칭 → role_slots 반환`.
- 반환 `PatternTemplate.role_slots`를 drafter가 구체 node_type으로 채워 루프 생성.

**핵심 원칙:**
- **L3b** (ADR-0023 §L3): drafter가 back-edge + condition 노드 생성. 모티프가 `CyclicScheduler` 계약(condition ≥1개) 보장 → §2 validator(PR #392) 통과 → 엔진 실행. **Phase 0 머지가 선행**.
- **constrained generation이 환각 억제의 본질** — `allowed_node_types()`를 프롬프트+후처리 가드로 강제.
- 모티프 예(quality_gate_loop): `generator(LLM) → evaluator(condition: score<θ) --retry--> generator / --done--> 하류`, `max_iterations`는 evaluator 파라미터.

### 4.2a 신정혜 — CAN_FOLLOW 엣지 + 모티프 시드 (composer grounding, 박아름 비의존)
> **소비자 = composer**, 데이터 소스 = **노드 I/O 스키마**(nodes_graph 공개 스키마, read-only). 스킬과 무관하므로 박아름 작업에 묶이지 않는다 — 신정혜가 ETL 확장부터 소비까지 자력 완결. (박아름 consult는 스키마 의미 정확도 향상용 *옵션*, 비차단.)
- **CAN_FOLLOW 휴리스틱**(`build_ontology.py` ETL 확장): 노드 I/O가 JSON Schema dict(`node_definition.py:24-25`)라 무손실 불가.
  - `A.output_schema` properties(이름+JSON type) ↔ `B.input_schema.required`(이름+type) 매칭 → 일치 수/타입 호환으로 `confidence` 산출.
  - confidence < 임계는 edge 생성 안 함(오탐 억제). 임계·매칭 규칙은 골든 셋으로 튜닝.
- **소비**: retriever에서 `expand_candidates` 결과의 CAN_FOLLOW로 후보를 **ADD 보강/랭킹**(subtract 필터 금지 — stale 역효과).
- **USES_ROLE / `:Pattern` 시드**: 모티프 슬롯(generator=LLM 노드, evaluator=condition 노드)을 카탈로그 node_type으로 큐레이션 → `:Pattern`에 연결. 카탈로그 기반이라 박아름 비의존.

> **✅ 구현·측정 완료 (PR #410, 황대원 선반영 — 정혜 검토/이관 대기, 2026-06-08)**
> `compute_can_follow_edges()`(output명 ∩ B.required-input명 + 트리거 타깃 제외 → 실 카탈로그 **55엣지**) + 어댑터 `_EXPAND_CYPHER`를 CAN_FOLLOW traverse로 교체 + `NodeRegistry.list_by_node_types()` 그라운딩 + retriever `_expand_can_follow()` ADD 보강.
>
> **§6.5 하니스로 in-process before/after 측정(엣지 0↔55 토글)** — 하니스가 **회귀를 잡은 사례**:
> | 지표 | baseline | ADD-all | **capped(채택)** |
> |---|---|---|---|
> | drafter 실패 | 6 | 🔴 23 | ✅ 9 |
> | qa pass(≥8) | 64.3% | 🔴 28.6% | ✅ 67.9% |
> | motif-correctness | 75% | 75% | ✅ **100%** |
> | hallucination | 0% | 0% | 0% |
>
> - **ADD-all = 회귀**: 후보 풀 비대(~24→38)로 Gemma structured JSON이 잘림(`Invalid JSON: EOF`). → **cap 필수**: seed=검색 상위 5 hit만(구조/개인 노드 제외) + 추가 ≤3개(`_EXPAND_SEED_LIMIT`/`_EXPAND_ADD_LIMIT`).
> - **핵심 교훈**: **환각은 이미 baseline 0%**(`executable_node_types` 그라운딩 #378이 진작 해결) → CAN_FOLLOW의 실효는 **환각감소가 아니라 motif(75→100%)·워크플로우 풍부화**다. ADR가 내세운 "환각 억제" 명분은 이 갈래에선 헤드룸이 없었음(§9.2 "constrained generation 최고가치"는 hallucinated-edge가 0이 아닐 때만 유효 — 본 카탈로그 규모에선 이미 0).
> - **구현은 ADD 보강이지 constrained generation(allowed_node_types whitelist/subtract)이 아님** — subtract는 ETL stale 시 유효 후보 삭제 위험이라 의도적 회피. whitelist 레버는 환각이 0이 아닌 환경(스킬 노드 대량 유입 등)에서 재검토.

### 4.2b 박아름 — 스킬 그래프 ETL (skill-builder grounding, 별개 소비자)
- **스킬 `(:Skill)-[:BINDS]->(:Node)` ETL**: 기존 스킬 **publish 경로에 Neo4j incremental upsert 훅** 배선(`BINDS`, `:Skill` 속성). 정적 카탈로그와 달리 스킬은 자주 바뀜. 소비자는 skill-builder(+ 향후 composer 스킬 제시) — composer의 노드 grounding(§4.2a)과 독립.
- ✅ **구현 완료**(#397 박아름) + **라이브 활성화**(#401 황대원): api 이미지 `ai_agent[ontology]` + api_server(Cloud Run) terraform `secret_env` `NEO4J_*` 바인딩 + api SA `secretAccessor`. 머지+`terraform apply`+기존 PUBLISHED 스킬 `project_skills()` backfill 후 신규 게시분이 자동 투영된다.

---

## 5. Phase 3 — 하이브리드 벡터 (선택)
- 벡터를 Neo4j 네이티브 벡터 인덱스로 이관 시 **seed+expand를 단일 Cypher**로 통합 가능(왕복 1회). pgvector 이중 저장 staleness와 트레이드오프 — Phase 2 안정화 후 측정 기반 결정.

---

## 6. 고도화(advancement) — 후속 본작업 (전 항목 진행 확정)

> **범위 확정 (2026-06-08)**: 본 이니셔티브의 의도된 고도화는 **"품질검증 루프 하나"가 아니라 "retry·분기·fan-out 등 다양한 control-flow 패턴을 자연어로 1급 생성"**이다. A1(#410)으로 핵심 2갈래(환각=이미 0%, quality_gate_loop=75→100%)는 충족됐으나, **그것만으론 의도한 고도화에 미달** — §6.1 모티프 확장이 능력 갭(미충족 의도)이고 §6.2/6.3/6.4도 함께 진행한다. 따라서 §6은 "선택적 레버"가 아니라 **커밋된 후속 로드맵**이다(우선순위는 §8).
>
> **방법론**: 각 항목은 §6.5 하니스로 before/after 측정하며 적용한다(A1에서 ADD-all 회귀를 잡았듯 — 측정 없는 고도화는 추측). 단일 샘플 노이즈를 줄이려 핵심 변경은 2~3회 반복 측정.

### 6.1 모티프 라이브러리 확장 (신정혜) — **agentic 패턴 기반 시드 스펙**

> **문제 인식(2026-06-07)**: 현재 `:Pattern`은 `quality_gate_loop` **1종뿐**이라 사실상 "패턴 라이브러리"라 부르기 어렵다. 온톨로지 그라운딩의 효익은 **검증된 모티프의 폭**에 비례하므로(§9 연구 근거), 아래 라이브러리를 1급으로 시드한다.
>
> **모티프 = 두 계보의 교집합** (§9.3): ① **van der Aalst control-flow 패턴**(프로세스 과학 정전, 20+종) ② **agentic workflow 패턴**(LLM 시대 — Anthropic/HF/Neo4j 합의: Prompt-Chaining·Routing·Parallelization·Orchestrator-Workers·Evaluator-Optimizer·Planning). 둘 다에서 검증된 패턴만 넣어야 환각을 **늘리지 않고** 억제한다(임의 패턴은 잘못된 구조를 강제).

**시드 스펙** — `_PATTERNS`(build_ontology.py) 확장. `intent`는 `match_patterns`의 `CONTAINS` 매칭 키워드, `role_slots`는 슬롯→카탈로그 category 매핑(현 condition 노드 인벤토리: `if_condition`/`switch_case`/`loop_list`/`loop_count`/`delay`/`retry`/`merge_branch`/`stop_workflow`, ai 노드: `anthropic_chat`/`gemma_chat`):

| 모티프 | van der Aalst | agentic | intent 키워드(예) | role_slots (slot→category/node) | 구조 | 엔진 계약 |
|--------|---------------|---------|-------------------|--------------------------------|------|-----------|
| `quality_gate_loop` ✅ | Structured Loop | Evaluator-Optimizer | 검증·품질·재생성 | generator→ai, evaluator→condition | gen→eval→(back-edge/exit-edge), `max_iterations` | CyclicScheduler(SCC당 condition≥1) + #392 validator |
| `branch_on_classification` | Exclusive Choice (XOR) | Routing | 분류·조건·~이면·분기 | classifier→ai, router→condition(`if_condition`/`switch_case`) | classify→XOR 분기→합류 | BranchEvaluator (L2 조건분기) |
| `fan_out_map` | Parallel Split + Sync | Orchestrator-Workers / Parallelization | 각각·목록·일괄·전부 | splitter→condition(`loop_list`), worker→ai/action, merger→condition(`merge_branch`) | split→병렬 worker→merge | L1 데이터흐름 + loop_list/merge_branch |
| `retry_backoff` | Structured Loop + delay | (resilience) | 재시도·실패하면·반복 | action→action, delay→condition(`delay`/`retry`), gate→condition(`if_condition`) | try→실패?→delay→retry / →exit | CyclicScheduler(condition≥1) |
| `approval_gate` | Deferred Choice / Milestone | Human-in-the-loop | 승인·검토 후·컨펌 | proposer→ai/action, gate→condition(`if_condition`), terminal→condition(`stop_workflow`) | propose→hold→approve/reject | 컨펌 게이트(ADR 컨펌 시리즈) |
| `sequential_chain` (암묵) | Sequence | Prompt-Chaining | (명시 모티프 불요 — DAG 기본) | step→any | A→B→C 선형 | 기본 DAG (validator 무순환) |

> **시드 원칙**: ① 슬롯 category는 **카탈로그에 실재하는 node_type**으로만(없는 슬롯은 시드 안 함 — 환각 유발). ② intent 키워드는 사용자 문장에서 실제 등장하는 한국어 표현으로(현 매칭이 `toLower CONTAINS p.intent`라 한 패턴에 복수 키워드가 필요하면 `:Pattern`을 키워드별 복수 시드하거나 매칭 Cypher를 `any()`로 확장). ③ `sequential_chain`은 LLM이 이미 잘 만드는 선형이라(§9.4 graph-planning 갭은 분기·루프에 집중) 시드 우선순위 최하.
> **필수 가드**: 각 모티프는 §2 validator 통과 + `CyclicScheduler`/`BranchEvaluator` 수용 계약과 1:1 정합 + **파리티 테스트 동반**(composer가 통과시킨 모티프 draft가 엔진에서 죽으면 false accept). 신규 모티프 PR마다 골든셋에 해당 시나리오 1건 추가(§6.5).

### 6.2 retrieval 튜닝 (신정혜)
- vector seed `k`, hop depth(1 vs 2)를 골든 셋으로 스윕. 1홉은 정밀/저지연, 2홉은 재현↑/노이즈↑.
- expand 시 `risk_level`·`required_connections` 미충족 노드 **사전 필터**(사용자 보유 connection 기반, PR #348 connection-aware와 연계)로 후보 오염 차단.

### 6.3 CAN_FOLLOW 신뢰도 + 큐레이션 (신정혜 — composer grounding)
- 휴리스틱 confidence에 **사람 큐레이션 레이어** — 자주 쓰이는 호환쌍은 수동 승격, 오탐쌍은 블랙리스트.
- 실행 로그(`node_results`)에서 **실제로 성공한 A→B 연쇄**를 마이닝해 confidence 보정(실측 기반 강화).

### 6.4 explainability / provenance (신정혜)
- 서브그래프 반환 시 각 후보의 **node_type provenance + 선택 근거(어느 seed/hop/모티프에서 왔는지)** 를 함께 반환 → composer 설명(컨펌 게이트 신뢰 매니페스트)과 SSE에 노출. 환각 디버깅·사용자 신뢰 모두 강화.

### 6.5 평가 하니스 (공통 — 고도화의 전제)
**before/after를 결정적으로 측정**하지 않으면 고도화가 추측이 된다. 골든 워크플로우 요청 셋(예: 30~50건, "품질검증 루프" 포함)에 대해:
| 지표 | 의미 |
|------|------|
| **validator-pass rate** | drafter 1차 산출물이 검증 통과하는 비율 (retry 전) |
| **validator retry 횟수** | qa_evaluator/validator 재시도 평균 (ADR-0004 흐름) |
| **hallucinated-edge rate** | 카탈로그에 없는 node_type/불가능 엣지 비율 |
| **motif-correctness** | "루프 요청 → 실행가능 quality_gate_loop 생성" 성공률 |
| **e2e quality score** | qa_evaluator score(≥8 통과) 분포 |
- GraphRAG 도입 전(현 pgvector top-k) 베이스라인 측정 → Phase별 회귀. `/rag-check` 골든 스냅샷 패턴 참고.

> **✅ 하니스 구축 완료 (PR #409 머지)** — `modules/ai_agent/tests/eval/ontology_grounding/`. 골든셋 32건(루프8/선형16/분기4/잡담4) + 순수 지표 추출기 + `run_eval`(라이브 캡처, main.py 조립 미러) + `check_snapshot`(베이스라인 회귀 게이트, `/ontology-eval`). 지표 계산은 순수/결정적(단위테스트), 라이브 캡처만 Modal+Neo4j+DB.
>
> **실측 캐비엇 (A1 측정에서 확인)**:
> - **hallucinated-edge는 baseline에서 이미 0%** — `executable_node_types` 그라운딩(#378)이 진작 해결. 이 지표는 스킬 노드 대량 유입 등 카탈로그 오염 시에만 움직임. §9.2의 "constrained generation 최고가치" 전제(환각>0)가 본 규모에선 미성립.
> - **motif-correctness 측정 정의**: "루프 요청 → 유향 순환(back-edge) + condition 노드 ≥1"(validator §2 SCC + CyclicScheduler 계약 1:1). 8개 루프 시나리오 기준.
> - **distractor 정답률은 측정 불가 아티팩트**: `run_eval`는 composer(LangGraphOrchestrator)를 **직접** 호출하는데 잡담 fast-path는 상위 **Main Orchestrator**에 있어 composer 단독엔 미적용 → 잡담도 워크플로우 생성. before/after 동일이라 A/B 결론엔 무영향이나, 절대값은 무의미.
> - **retry/validator-pass는 drafter 실패 시 허상**: drafter가 아예 실패(node 0)하면 재시도 루프에 안 들어가 "무재초안"으로 빠짐. 헤드라인 신호는 **drafter 실패율 + qa**.
> - **단일 샘플 LLM 노이즈**: 시나리오당 ~2.5분(32건×~80분/캡처)이라 반복이 비싸지만, 핵심 결론은 2~3회 반복 측정으로 de-noise 권장.

---

## 7. 지뢰 / 운영 체크리스트
1. **Modal per-request driver** — `@enter` 1회 생성 금지(loop-binding hang). 요청마다 생성·close.
2. **secret 경로 = Modal `load_secrets_to_env` (terraform 아님)** — composer/skills-builder는 Modal 앱이라 `boot()`에서 GCP secret(`neo4j-uri`/`username`/`password`)을 런타임 pull. terraform `secret_env`는 Cloud Run(api/worker) 전용. secret `:latest` 복수 공유 시 `secret_latency_bomb` → 버전 핀.
3. **ETL 동기화** — 정적 카탈로그 deploy 1회 + 스킬 publish incremental. 재시드 레시피(`staging_node_catalog_reseed`)와 정합.
4. **소비자 분리 — Phase 2는 박아름 의존 아님**: composer grounding(§4.2a 모티프·CAN_FOLLOW)은 노드 I/O 스키마 파생이라 **신정혜 자력 완결**. 박아름 몫(§4.2b 스킬 BINDS)은 skill-builder grounding이라 **독립 병렬**. (Phase 0 validator만 nodes_graph 교차소유라 박아름 sign-off 필요 — PR #392.)
5. **프로젝트 일정** — 2026-06-30 staging 종료와 별개의 **장기 제품 방향**. staging 검증은 Phase 1 한정, Phase 2+는 일정 합의 후.

---

## 8. 진행 순서 요약
```
[황대원] §1 인프라 ✅ PR #393 / §2 Phase 0 validator 완화 ✅ PR #392
        ↓
[신정혜] §4.1 retriever+모티프+drafter grounding ✅ (#395 머지)
[황대원] §4.2a CAN_FOLLOW + expand 부활(capped, 하니스 검증) ✅ PR #410 (정혜 이관 대기)
[박아름] §4.2b 스킬 BINDS ETL ✅ (#397/#401 머지·배포)
[공통]  §6.5 평가 하니스 ✅ PR #409 머지
        ↓ ── 후속 고도화(전 항목 진행 확정, 측정 주도) ──
[우선1] 반복 측정 de-noise (capped A1 2~3회 재캡처 — 기능 추가 0, '달성' 검증 최우선)
[우선2] §6.1 모티프 라이브러리 확장 (branch_on_classification / fan_out_map / retry_backoff /
        approval_gate) — 의도된 고도화의 본질(다양한 control-flow 생성). 모티프당 골든셋+파리티
[우선3] §6.3 CAN_FOLLOW 신뢰도(실행로그 node_results 마이닝) + §6.2 retrieval 튜닝 + §6.4 provenance
        ↑ 각 항목 §6.5 하니스 before/after 게이트 통과 필수
```
> RACI: §6 후속은 plan상 신정혜(composer grounding). 황대원 A1 선반영분(#410) 이관 후 신정혜 주도, 황대원 리뷰/하니스 조율. 일정은 2026-06-30 staging 종료 전 합의.

---

## 9. 온톨로지 구조·패턴 설계 원칙 (연구 근거)

> **목적**: 온톨로지 성능은 **그래프 구조·검색 패턴·모티프 라이브러리·평가 방법**에 크게 좌우된다(현장/논문 합의). 본 절은 §4.2a(신정혜)·§6 고도화·§6.5 하니스 설계의 **근거와 리뷰 기준**을 박제한다. (조사 2026-06-07, 출처 §9.6.)

### 9.1 그래프 구조 설계 4원칙
1. **"단순 그래프 + 강한 검색" > 복잡한 그래프** — 완벽히 풍부한 그래프보다 *싸고 빠르게 추출 가능한 핵심만 넣고 retrieval 파이프라인이 메우게* 하는 게 비용 대비 recall이 높다. → **우리 검증**: 53노드 최소 스키마 + 벡터 비복제 결정이 정합. 신정혜 §4.2a가 그래프를 과설계하면 경계.
2. **타입드 + 가중(confidence) 엣지** — 추론(휴리스틱) 엣지엔 confidence를 달아 임계 필터. → **우리**: `CAN_FOLLOW {confidence}`(§4.2a)가 정확히 이 패턴. 임계 골든셋 튜닝 + 오탐쌍 블랙리스트(§6.3)가 품질을 결정.
3. **경량 계층/커뮤니티** — GraphRAG 계열은 엔티티를 community(주제 클러스터)로 묶어 전역/지역 질의를 분리. → **우리**: `:Category`(IN_CATEGORY)가 경량 community 역할. 노드 53개라 본격 community detection(Leiden 등)은 과함.
4. **⚠️ 과확장(over-expansion)이 정밀도를 희석** — 큰 이웃을 다 끌어오면 주제 밖 노드가 섞여 retrieval precision 저하. → **우리 직결**: `expand_candidates` hops(1 vs 2) 튜닝(§6.2) + #395의 **subtract 필터 제거(ADD-only)** 결정이 이 함정 회피. 하니스로 측정할 핵심 파라미터.

### 9.2 검색(retrieval) 패턴
- **vector seed → graph expand → constrained context** = GraphRAG 표준. 우리 `pgvector seed → expand_candidates → allowed_node_types()`가 교과서 흐름.
- **schema/ontology-constrained generation = 환각 억제의 본질** — 논문 최강 합의. 스키마·공리를 프롬프트 주입하거나 디코딩 제약 시 사실오류 유의하게↓(임상 KG-RAG 등). → **우리**: `OntologySubgraph.allowed_node_types()` 화이트리스트가 이것. **⚠️ 2026-06-08 실측 정정**: A1(#410)으로 expand는 켜졌으나 **ADD 보강 형태**(whitelist/subtract 아님)이며, 하니스 측정에서 **hallucinated-edge가 baseline 이미 0%**(executable_node_types #378이 진작 해결)라 **이 레버는 본 카탈로그 규모(53노드)에선 헤드룸이 없다**. constrained generation(whitelist)은 환각>0 환경(스킬 노드 대량 유입 등)에서만 재검토 가치. → CAN_FOLLOW의 실효는 환각감소가 아니라 **motif·풍부화**로 드러남(§4.2a 측정).
- **local vs global retrieval 분리** — entity-centric(호환 노드) vs motif(의도 패턴). 우리가 `expand_candidates`(local) / `match_patterns`(global) 두 Port 메서드로 이미 분리.

### 9.3 모티프 라이브러리 = van der Aalst ∩ agentic
- **van der Aalst control-flow 패턴**(2003~): Sequence, Parallel Split/Synchronization, Exclusive Choice(XOR), Simple Merge, Multi-Choice, Structured Loop, Deferred Choice, Milestone …
- **agentic workflow 패턴**(LLM): Prompt-Chaining, Routing, Parallelization/Sectioning, Orchestrator-Workers, Evaluator-Optimizer, Planning.
- **우리 §6.1 모티프가 두 계보의 교집합** — 검증된 패턴만 1급 시드(매핑 표는 §6.1). 임의 패턴 금지 + 엔진 계약 파리티 필수.

### 9.4 평가 — "워크플로우 = 그래프"
- 워크플로우 생성 벤치마크(WorFBench/WorFEval)는 **subsequence + subgraph matching**으로 평가 — 텍스트 일치가 아닌 **구조 일치**. → **우리 하니스(§6.5)**: motif-correctness를 "생성물에 generator→evaluator→back-edge→exit-edge **서브그래프**가 있나"로, hallucinated-edge를 "생성 엣지가 카탈로그/CAN_FOLLOW의 **그래프 멤버십**인가"로 측정(텍스트 아님).
- **결정적 발견**: LLM은 **sequence planning ≫ graph planning** — GPT-4도 그래프(분기·병렬·루프) 생성에서 ~15% 갭. → 모티프 그라운딩의 정량적 정당화. 또한 **soft 프롬프트 주입의 한계**(graph 구조는 LLM 약점)를 시사 → 장기적으로 **결정적 모티프 합성**(템플릿 서브그래프 직접 생성)이 soft 주입보다 안정적일 수 있음. §4.2a 설계 선택(주입 vs 합성)의 근거.

### 9.5 종합 — 리뷰/하니스 5원칙
1. 그래프는 단순하게, 검색을 강하게 (과설계 경계).
2. **constrained generation(allowed_node_types)이 환각 억제 본질** — 단, 실측상 환각 이미 0%(53노드 규모)라 헤드룸 없음(§9.2 정정). A1은 ADD 보강이지 whitelist 아님. CAN_FOLLOW 실효 = motif·풍부화.
3. CAN_FOLLOW는 confidence-weighted + 임계 튜닝 (오탐 억제가 품질 결정).
4. 모티프는 van der Aalst/agentic 검증 패턴만 + 엔진 계약 파리티.
5. 평가는 **subgraph matching** (구조 일치), graph-planning이 LLM 약점이라 **N회 반복 통과율**로(soft 주입 비결정성).

### 9.6 출처
- GraphRAG 구조·검색: [Towards Data Science — GraphRAG in Practice](https://towardsdatascience.com/graphrag-in-practice-how-to-build-cost-efficient-high-recall-retrieval-systems/) · [Neo4j RAG tutorial](https://neo4j.com/blog/developer/rag-tutorial/) · [Survey of Graph RAG (arXiv 2501.13958)](https://arxiv.org/pdf/2501.13958) · [Survey on Knowledge-Oriented RAG (arXiv 2503.10677)](https://arxiv.org/pdf/2503.10677)
- 온톨로지 그라운딩/제약 생성: [Ontology-grounded KGs for clinical QA hallucination (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1532046426000171) · [Ontology-Grounded LLM Construction (EmergentMind)](https://www.emergentmind.com/topics/ontology-grounded-llm-construction) · [Ontology-Constrained Generation (arXiv 2411.15666)](https://arxiv.org/pdf/2411.15666) · [API Hallucination via Hierarchical Dependency (arXiv 2505.05057)](https://arxiv.org/pdf/2505.05057)
- 워크플로우 패턴/평가: [Design Patterns for Agentic Workflows (HF)](https://huggingface.co/blog/dcarpintero/design-patterns-for-building-agentic-workflows) · [Workflow Patterns — van der Aalst (Springer)](https://link.springer.com/rwe/10.1007/978-0-387-39940-9_826) · [Benchmarking Agentic Workflow Generation — WorFBench (arXiv 2410.07869)](https://arxiv.org/abs/2410.07869)
