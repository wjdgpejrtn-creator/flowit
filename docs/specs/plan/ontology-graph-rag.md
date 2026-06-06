# Plan — 온톨로지 그래프 DB + GraphRAG (composer/skill-builder 품질 고도화)

> **결정 문서**: [ADR-0026](../../context/adr/ADR-0026-ontology-graph-db-graphrag.md) · **선행 control-flow**: [ADR-0023](../../context/adr/ADR-0023-workflow-control-flow-engine.md)
> **작성**: 2026-06-06 (황대원). 본 문서는 **그래프 DB 초기 인프라 설계·구축(황대원) + 구현·고도화 핸드오프(신정혜·박아름)** 가이드다.

---

## 0. 역할 분담 (RACI)

| 작업 영역 | 소유 | 비고 |
|----------|------|------|
| **그래프 DB 초기 인프라** (AuraDB provisioning, secret/terraform, `OntologyRetrieverPort` ABC, `Neo4jOntologyAdapter` 연결 스캐폴드, `build_ontology.py` ETL 골격, 온톨로지 스키마 제약/인덱스) | **황대원 (조장)** | 본 문서 §1·§3 — *구축 범위 끝* |
| **validator 순환 완화** (Phase 0, 하드 선행) | **황대원 선반영 (PR #392)** / 박아름 sign-off | 본 문서 §2 — 구현 완료, nodes_graph 교차소유 검토 대기 |
| **GraphRAG retrieval + 모티프 + drafter grounding** (Phase 2) | **신정혜** | 본 문서 §4 |
| **CAN_FOLLOW 휴리스틱 + 스킬 그래프 ETL 강화** (Phase 2) | **박아름** | 본 문서 §4 |
| **하이브리드 벡터 + 고도화 레버** (Phase 3) | 신정혜·박아름 | 본 문서 §5·§6 |

> 황대원은 인프라(§1·§3) + **Phase 0 validator 완화(§2)를 선반영**(PR #392, 위임이 결국 되돌아오는 패턴이라 직접 처리)했다. §4·§5·§6은 설계·계약·테스트 기준만 제공하고 실행은 담당자에게 넘긴다.

---

## 1. Phase 1 — 그래프 DB 초기 인프라 (황대원 구축 범위)

### 1.1 AuraDB provisioning
- Neo4j **AuraDB Free**(staging) 인스턴스 1개. region은 GCP staging과 근접(europe-west/us 중 api Cloud Run과 동일 권역).
- 연결 정보(`NEO4J_URI` `neo4j+s://...`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`)는 **dedicated secret** `ontology-neo4j-auradb`로 GCP Secret Manager에 저장. **공유 금지**(`secret_latency_bomb` 교훈).
- terraform이 env 바인딩 소유 — composer Modal app + (필요 시) api_server에 secret_env 주입. **deploy.yml은 이미지만**이므로 `terraform apply` 필수(`deploy_image_only_terraform_owns_env`).

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

### 1.3 `OntologyRetrieverPort` (ABC — ai_agent/domain/ports)
신정혜가 소비할 **계약만** 정의(구현 비움). 도메인 레이어이므로 neo4j import 금지.
```python
# modules/ai_agent/domain/ports/ontology_retriever.py
from abc import ABC, abstractmethod
from common_schemas import NodeCandidate  # 또는 기존 후보 VO 재사용

class OntologyRetrieverPort(ABC):
    @abstractmethod
    async def expand_candidates(
        self, seed_node_types: list[str], hops: int = 1
    ) -> "OntologySubgraph": ...
    """벡터 seed(node_type)들을 그래프로 1~2홉 확장해 제약된 후보 서브그래프 반환."""

    @abstractmethod
    async def match_patterns(self, intent: str) -> list["PatternTemplate"]: ...
    """의도 문자열에 맞는 검증된 워크플로우 모티프(:Pattern) 템플릿 반환."""
```
> `OntologySubgraph`/`PatternTemplate`은 ai_agent 도메인 VO(또는 common_schemas 승격은 신정혜 협의). 황대원은 **빈 dataclass 골격**만 제공.

### 1.4 `Neo4jOntologyAdapter` (어댑터 — ai_agent/adapters/ontology)
- **요청마다 driver 생성** 패턴 강제 — composer가 Modal ASGI라 `@modal.enter`에서 driver 1회 생성 시 asyncpg와 동일하게 boot≠request 루프 미스매치로 hang(`composer_modal_per_request_engine`). worker 패턴(요청마다 생성·close)을 따른다.
- Phase 1 쿼리만 구현: seed→expand(`REQUIRES`/`BINDS`/`IN_CATEGORY`). `CAN_FOLLOW`/`match_patterns`는 **`NotImplementedError`** 로 두고 §4에서 박아름·신정혜가 채움.

### 1.5 `scripts/build_ontology.py` (ETL 골격 — 멱등)
- 소스: `NodeDefinitionRepository.list_all()`(노드) + skills(`SkillRepository`). Neo4j는 직접 모름 — ETL이 투영.
- Phase 1 무손실 MERGE만:
```
MERGE (:Node {node_type})  SET category/risk_level/service_type
MERGE (:Connection {provider}) ; (:Node)-[:REQUIRES]->(:Connection)
MERGE (:Category {name}) ; (:Node)-[:IN_CATEGORY]->(:Category)
MERGE (:Skill {id}) ; (:Skill)-[:BINDS]->(:Node)
```
- **벡터 복제 안 함** — pgvector(BGE-M3)를 seed 검색에 그대로 사용(`skill_embedding_pipeline_gap` staleness 회피).
- 실행 시점: 정적 카탈로그는 deploy 훅 1회. **스킬 publish 경로 incremental upsert**는 §4(박아름).

> **인프라 검증 종료선**: AuraDB 연결됨 + 제약 생성됨 + `build_ontology.py`로 56노드+연결+스킬 무손실 투영됨 + `expand_candidates` Phase 1 쿼리 동작. 여기까지가 황대원 구축 범위.

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
**GraphRAG 흐름**:
```
1. vector seed:   pgvector top-k (BGE-M3) → seed node_type 집합
2. graph expand:  OntologyRetrieverPort.expand_candidates(seed, hops=1~2)
                  → REQUIRES/CAN_FOLLOW/BINDS 1~2홉 제약 서브그래프
3. drafter:       서브그래프 내부 엣지만 생성 (constrained generation)
4. 모티프:        intent가 "검증/재생성/품질"이면
                  OntologyRetrieverPort.match_patterns(intent) → quality_gate_loop 템플릿
                  → USES_ROLE 슬롯에 구체 node_type 바인딩
                  → back-edge(condition→generator) + exit-edge + condition.parameters.max_iterations 생성
```
- **L3b** (ADR-0023 §L3 line 47): drafter가 back-edge + condition 노드를 생성하는 책임. 모티프 템플릿이 `CyclicScheduler` 계약(condition ≥1개)을 보장 → §2 validator 통과 → 엔진 실행.
- **constrained generation이 환각 억제의 본질**: drafter가 서브그래프 밖 node_type/엣지를 만들지 못하게 프롬프트+후처리로 강제.
- 모티프 템플릿 예(quality_gate_loop): `generator(LLM 노드) → evaluator(condition: score<θ) --retry--> generator / --done--> 하류`. `max_iterations`는 evaluator 파라미터.

### 4.2 박아름 — CAN_FOLLOW 추론 + 스킬 그래프 ETL
- **CAN_FOLLOW 휴리스틱**: 노드 I/O가 JSON Schema dict(`node_definition.py:24-25`)라 무손실 불가. 추론 알고리즘 가이드:
  - `A.output_schema`의 properties(이름+JSON type) ↔ `B.input_schema.required`(이름+type) 매칭 → 일치 수/타입 호환으로 `confidence` 산출.
  - confidence < 임계는 edge 생성 안 함(오탐 억제). 임계·매칭 규칙은 골든 셋으로 튜닝.
- **스킬 그래프 ETL 강화**: 기존 스킬 **publish 경로에 Neo4j incremental upsert 훅** 배선(`BINDS`, `:Skill` 속성). 정적 카탈로그와 달리 스킬은 자주 바뀜.
- **USES_ROLE 시드**: 모티프 슬롯(generator=LLM 노드, evaluator=condition 노드)에 맞는 node_type을 카탈로그에서 큐레이션해 `:Pattern`에 연결.

---

## 5. Phase 3 — 하이브리드 벡터 (선택)
- 벡터를 Neo4j 네이티브 벡터 인덱스로 이관 시 **seed+expand를 단일 Cypher**로 통합 가능(왕복 1회). pgvector 이중 저장 staleness와 트레이드오프 — Phase 2 안정화 후 측정 기반 결정.

---

## 6. 고도화(advancement) 레버 — 상세 가이드

품질을 단계적으로 끌어올리는 레버. 담당자가 측정하며 적용.

### 6.1 모티프 라이브러리 확장 (신정혜·박아름)
`quality_gate_loop` 외 검증된 모티프를 `:Pattern`으로 추가 → composer가 복합 패턴을 1급 생성:
- **fan_out / map**: 리스트 입력을 노드별 병렬 처리 (control-flow L1 데이터흐름 위)
- **retry_backoff**: 실패 시 지연 후 재시도 (유한 순환 + 조건)
- **approval_gate**: 사람 컨펌 후 진행 (컨펌 게이트와 연계, ADR 컨펌 시리즈)
- **branch_on_classification**: 분류 결과로 분기 (L2 조건 분기)
> 각 모티프는 §2 validator 통과 + `CyclicScheduler`/`BranchEvaluator` 계약 정합이 필수. 추가 시 파리티 테스트 동반.

### 6.2 retrieval 튜닝 (신정혜)
- vector seed `k`, hop depth(1 vs 2)를 골든 셋으로 스윕. 1홉은 정밀/저지연, 2홉은 재현↑/노이즈↑.
- expand 시 `risk_level`·`required_connections` 미충족 노드 **사전 필터**(사용자 보유 connection 기반, PR #348 connection-aware와 연계)로 후보 오염 차단.

### 6.3 CAN_FOLLOW 신뢰도 + 큐레이션 (박아름)
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

---

## 7. 지뢰 / 운영 체크리스트
1. **Modal per-request driver** — `@enter` 1회 생성 금지(loop-binding hang). 요청마다 생성·close.
2. **dedicated secret + terraform** — `ontology-neo4j-auradb` 공유 금지, `terraform apply`로 env 바인딩(deploy.yml은 이미지만).
3. **ETL 동기화** — 정적 카탈로그 deploy 1회 + 스킬 publish incremental. 재시드 레시피(`staging_node_catalog_reseed`)와 정합.
4. **3-owner 협의** — Phase 0은 황대원이 nodes_graph(박아름 소유)에 선반영(PR #392, 사후 통지 완료) → 박아름 sign-off 대기. Phase 2(신정혜+박아름) 동시 진행 전 ownership 통지(`cross_owner_module_etiquette`).
5. **프로젝트 일정** — 2026-06-30 staging 종료와 별개의 **장기 제품 방향**. staging 검증은 Phase 1 한정, Phase 2+는 일정 합의 후.

---

## 8. 진행 순서 요약
```
[황대원] §1 인프라 구축 (AuraDB + Port ABC + 어댑터 스캐폴드 + ETL 골격)   ─┐ 병렬 가능
[황대원] §2 Phase 0 validator 완화 ✅ PR #392 (박아름 sign-off 대기)        ─┘
        ↓ (둘 다 완료)
[신정혜+박아름] §4 Phase 2 GraphRAG + 모티프 + drafter grounding
        ↓
[공통] §6.5 평가 하니스로 측정 → §6 고도화 레버 반복
```
