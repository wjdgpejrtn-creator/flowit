# ADR-0026: 온톨로지 기반 그래프 DB (Neo4j AuraDB) + GraphRAG — composer/skill-builder 품질 향상 및 워크플로우 모티프 그라운딩

- **Status**: Proposed
- **Date**: 2026-06-06
- **Deciders**: @dhwang0803 (조장 — 발의, execution_engine/REQ-007) + 신정혜 (REQ-004 ai_agent Composer) + @billionaireahreum (박아름 — REQ-002/003 nodes_graph, REQ-013 skills_marketplace)
- **Tags**: area/ai_agent, area/skills_marketplace, area/nodes_graph, layer/adapter, infra/graph-db, req/004, req/013

## Context

composer와 skill builder의 생성 품질이 떨어진다. 두 가지 갈래의 문제가 확인됐다.

1. **노드 레벨 환각** — composer가 56종 노드 카탈로그(외부 14 + 도메인 28 + toolset 14)에서 후보를 고를 때, 벡터 유사도(pgvector + BGE-M3) top-k만으로 골라 **불가능한 조합·존재하지 않는 연결**을 만든다. PR #387/#378의 `executable_node_types` 미러 그라운딩으로 절반은 손댔으나, **노드 간 호환성·연결 요구(required_connections)·타입 흐름**은 평탄한 임베딩 검색으로 표현되지 않는다.

2. **패턴(모티프) 레벨 부재** — 사용자가 "메시지를 보내기 전에 품질을 검증하고 미달이면 재생성"처럼 **검증→재생성 루프**가 있는 워크플로우를 요청해도 composer가 만들지 못한다. 이는 ADR-0023이 도입한 control-flow의 **L3 유한 순환(품질 게이트 루프)** 패턴이다. drafter가 "generator → evaluator → 조건 back-edge / exit-edge"라는 구조적 모티프를 안정적으로 그리지 못하고 매번 환각한다.

평탄한 RAG의 한계는 **구조적 제약과 멀티홉 추론**을 못 하는 것이다. 온톨로지(노드·연결·타입·스킬·검증된 워크플로우 모티프를 노드/엣지로 표현한 지식 그래프)를 도입하고 GraphRAG(벡터 seed → 그래프 확장 → 제약된 서브그래프 반환)로 생성을 그라운딩하면, 다중홉 질의에서 명시적 관계로 답을 묶어 환각을 억제한다는 것이 다수 연구에서 확인된다(온톨로지 그라운딩 KG가 도메인 QA 사실오류 30~40%↓; agentic decomposition으로 14.1%→4.9%).

### 선행 의존성 (중요)

품질 게이트 루프 모티프는 **ADR-0023의 다음 후속이 선행되지 않으면 무의미하다**:

- **엔진 실행기**(`CyclicScheduler`)는 ✅ 완료·staging 배포됨 (PR #359, `origin/release` ancestor 확인).
- composer `validator_node`가 쓰는 **`nodes_graph` `GraphValidator._detect_cycles`가 모든 순환을 무조건 `E_CYCLE_DETECTED`로 거부**했다 — **엔진은 루프를 돌릴 수 있는데 composer가 자기 검증에서 루프 드래프트를 삭제하던** 비대칭. **PR #392(황대원 선반영, OPEN)로 완화**: non-trivial SCC가 condition 노드를 ≥1개 포함하면 허용(엔진 `CyclicScheduler` 수용 기준 1:1 미러), 박아름 sign-off 대기.

따라서 그래프 DB로 모티프를 아무리 잘 retrieve해도, **validator 완화(ADR-0023 §L3 후속 — PR #392로 선반영)가 먼저 들어오지 않으면 composer는 루프 워크플로우를 절대 출력할 수 없다.** 본 ADR은 이 의존성을 1급으로 못박는다.

## Decision

**온톨로지 기반 그래프 DB로 Neo4j AuraDB(매니지드)를 채택**하고, composer/skill-builder의 검색을 평탄 벡터 RAG에서 **GraphRAG(벡터 seed → 그래프 확장 → 제약된 후보 서브그래프)** 로 전환한다. 온톨로지는 노드·연결·스킬뿐 아니라 **검증된 워크플로우 모티프(`:Pattern`)** 를 1급 엔티티로 포함하며, `quality_gate_loop` 모티프(gen → eval condition → back-edge/exit-edge 구조)는 ADR-0023의 `CyclicScheduler` 수용 계약(루프에 condition 노드 ≥1개 존재 — 유한성은 엔진 max-iter 가드가 보장)과 1:1로 정합한다.

도입은 **3개 Phase로 점진**하며, L3 validator 완화가 Phase 2의 하드 선행이다.

### Port 소유권 / 경계 (Clean Architecture)

기존 `NodeRegistry` 퍼사드 및 `EmbedderPort` 예외 패턴(ADR-0013 — Modal/외부 호출은 ai_agent 영역)을 따른다.

```
ai_agent/domain/ports/OntologyRetrieverPort   (ABC, consumer-owned — Composer가 소비)
ai_agent/adapters/ontology/Neo4jOntologyAdapter   (구현 — neo4j async driver)
scripts/build_ontology.py                          (ETL: Postgres 카탈로그+스킬 → Neo4j 투영, 멱등)
```

- Port를 **ai_agent가 소유**하는 근거: 소비자가 Composer이고, 외부 인프라(Neo4j) 호출 어댑터를 도메인 소유 모듈이 아닌 호출 모듈에 두는 것이 ADR-0013 EmbedderPort와 동일한 확립된 예외 패턴. `domain/`은 프레임워크 무지 유지(neo4j import는 `adapters/`에만).
- 온톨로지 **데이터 출처**는 `nodes_graph`(노드 정의) + `skills_marketplace`(스킬). 이들은 ETL의 소스일 뿐 Neo4j를 직접 모르며, 의존 방향 무변경.

### 온톨로지 스키마

```cypher
// Phase 1 — 무손실 (데이터에서 직접)
(:Node {node_type, category, risk_level, service_type})
(:Connection {provider})
(:Skill {id, tier, audience})          // personal/team/company (ADR-0012)
(:Category {name})

(:Node)-[:REQUIRES]->(:Connection)      // required_connections (무손실)
(:Node)-[:IN_CATEGORY]->(:Category)     // 무손실
(:Skill)-[:BINDS]->(:Node)              // 스킬↔노드 (이슈 #372). ADR-0024 D2 정합 = 모델 A:
                                        // 스킬은 ai(LLM) 노드 + required_connections 노드에 BINDS
                                        // (node_definition_id 경로 폐기). publish 훅이 라이브 upsert.

// Phase 2 — 모티프 + 휴리스틱 타입 흐름
(:Pattern {name, intent})                              // 예: quality_gate_loop
(:Pattern)-[:HAS_TEMPLATE]->(서브그래프 템플릿)          // gen→eval→조건 back-edge/exit-edge
(:Pattern)-[:USES_ROLE {slot}]->(:Node)                // generator/evaluator 슬롯에 맞는 node_type
(:Node)-[:CAN_FOLLOW]->(:Node)                         // output_schema↔input_schema 휴리스틱 매칭
```

- **벡터는 Phase 1에서 복제하지 않는다.** pgvector(BGE-M3)를 seed 검색에 그대로 쓰고 Neo4j는 순수 구조 확장만 담당한다(이중 저장 = staleness 부채, `skill_embedding_pipeline_gap` 교훈). 하이브리드 단일쿼리가 필요하면 Phase 3에서 Neo4j 네이티브 벡터 인덱스로 이관.
- `CAN_FOLLOW`는 노드 I/O가 JSON Schema dict(`node_definition.py:24-25` `input_schema`/`output_schema`)라 **휴리스틱 추론**이며 무손실이 아니다 → Phase 2로 미룸.

### GraphRAG 흐름 (composer `retriever_node` 교체)

```
vector seed (pgvector top-k)
  → graph expand 1~2홉 (REQUIRES / CAN_FOLLOW / BINDS / Pattern.HAS_TEMPLATE)
  → 제약된 후보 서브그래프 반환
  → drafter는 서브그래프 밖 엣지 생성 금지 (constrained generation = 환각 억제 본질)
  → 의도가 "검증/재생성/품질"이면 quality_gate_loop 모티프 retrieve → CyclicScheduler 실행가능 형태로 grounding
  → validator(GraphValidator) retry 횟수 자연 감소
```

### Phase 로드맵 (의존 순서)

| Phase | 내용 | 소유 | 선행 |
|------|------|------|------|
| **0 (하드 선행)** | `GraphValidator._detect_cycles` 완화 — non-trivial SCC가 condition 노드 ≥1개면 허용(유한성은 엔진 max-iter 가드), ADR-0023 §L3 후속 | 황대원 선반영 **PR #392** (박아름 sign-off) | #359 ✅ |
| **1** | Neo4j AuraDB + 온톨로지 무손실 edge(노드/연결) + `OntologyRetrieverPort`/어댑터 + `build_ontology.py` + expand 1-hop | ✅ 황대원 **PR #393** (AuraDB 라이브검증·53노드·secret 3종·IAM) | — |
| **2a** | `:Pattern` 모티프(`quality_gate_loop`) + `CAN_FOLLOW`(노드 I/O 파생) + drafter grounding + retriever 배선 | **신정혜** (composer grounding — 박아름 비의존, 자력 완결) | Phase 0, 1 |
| **2b** | 스킬 `(:Skill)-[:BINDS]->(:Node)` ETL + publish 훅 — ✅ **박아름 구현**: `SkillOntologyProjector` Port(skills_marketplace) + `Neo4jSkillProjector`(ai_agent/ontology) + `PublishSkillUseCase` non-fatal 훅 + `build_ontology.project_skill(s)` 배치 backfill 헬퍼. D2 정합 모델 A(ai 노드 + connection 노드 BINDS) | **박아름** (skill-builder grounding, 별개 소비자) | Phase 1 |
| **3** | Neo4j 네이티브 벡터 인덱스로 하이브리드 단일쿼리 (선택) | 황대원 | Phase 2 |

## Consequences

### Positive
- 노드 후보를 **실행 가능한 호환 서브그래프로 제약** → composer 환각·validator retry 감소.
- 품질 게이트 루프 등 agentic 모티프를 **검증된 템플릿으로 grounding** → ADR-0023 control-flow 역량이 사용자에게 실제로 도달.
- skills_marketplace 성장 시 `skill→node→connection→type` 멀티홉 추론으로 확장 가능(장기 제품 방향).
- LangGraph/LangChain 생태계와 Neo4j GraphRAG 통합이 턴키(`neo4j-graphrag-python`, LlamaIndex) → 통합 비용 최소.

### Negative / Trade-offs
- **신규 인프라 1종**(AuraDB) + GCP secret 3종 + Modal `load_secrets_to_env` 매핑. 운영 표면 증가.
- 온톨로지 ETL(`build_ontology.py`)이 Postgres 카탈로그·스킬과 **동기화 부채**를 만든다 — 정적 카탈로그는 deploy 시 1회, 스킬은 publish마다 incremental upsert 필요.
- `CAN_FOLLOW`가 JSON Schema 휴리스틱이라 **무손실이 아님** — 오탐/누락 가능, Phase 2에서 정밀화 비용.
- 3개 owner 모듈(ai_agent/nodes_graph/skills_marketplace) 동시 터치 → 협의 오버헤드.

### Follow-ups
- **Phase 0(validator 완화)는 본 ADR과 독립적으로도 필요** — **PR #392(황대원 선반영)로 완료, 박아름 sign-off 대기**. 미완 시 Phase 2 전체 블록. 파리티 가드(validator↔CyclicScheduler 수용 계약)는 #392에 조립-계층 테스트로 동봉.
- **Modal per-request driver**: composer가 Modal ASGI라 neo4j async driver를 `@enter`에서 1회 생성하면 asyncpg와 동일하게 boot≠request 루프 미스매치로 hang 위험(`composer_modal_per_request_engine` 사고 재연). 요청마다 드라이버 생성 패턴 강제.
- **Secret 경로 = Modal `load_secrets_to_env` (terraform 아님)**: AuraDB 자격은 GCP secret 3종(`neo4j-uri`/`neo4j-username`/`neo4j-password`, ✅ 생성 + `cloudsql-iam-modal` SA IAM 부여). composer/skills-builder는 Modal 앱이라 `boot()`에서 런타임 pull — terraform `secret_env`는 Cloud Run 전용이라 본 경로엔 안 씀. secret `:latest` 복수 공유 시 `secret_latency_bomb` 주의(버전 핀).
- **ETL 훅**: ✅ 완료 — `PublishSkillUseCase`가 `SkillOntologyProjector`(미주입/실패 시 non-fatal)로 게시 시 `(:Skill)-[:BINDS]->(:Node)` incremental upsert. api_server DI는 `NEO4J_URI` 설정 시에만 `Neo4jSkillProjector` 주입(하위호환).
- 프로젝트 종료(2026-06-30) 일정과 별개의 **장기 제품 방향** 결정임 — staging 검증 범위는 Phase 1로 한정.

## Alternatives Considered

- **FalkorDB** (Redis 모듈 기반 그래프 DB): 이미 쓰는 Redis 재활용 + GraphRAG 전용 저지연 + multi-graph가 3계층 테넌시에 매핑되는 인프라 친화성이 매력. 단 LangChain/LangGraph 통합이 Neo4j보다 얕아 통합 비용을 우리가 더 짐. **차선** — 인프라 친화성 우선 시 재검토.
- **Apache AGE** (PostgreSQL openCypher 확장): pgvector와 단일 스토어 유지가 장점이나, **Cloud SQL이 AGE 확장 미지원** → 자체 관리 Postgres/AlloyDB 컨테이너 이전 필요. 사실상 막힘. 기각.
- **Kùzu** (임베디드 그래프 DB): 임베디드·Modal 친화로 후보였으나 **2025-10 GitHub 아카이브(read-only) + Apple acqui-hire로 유지보수 종료**. 신규 도입 부적합. 기각(후속 포크 LadybugDB는 성숙도 미달).
- **AlloyDB AI** (GCP 네이티브 벡터/RAG): 그래프(Cypher/온톨로지 멀티홉)가 아니라 본 목표(구조적 제약·모티프) 미충족. 기각.
- **그래프 DB 없이 Postgres 인접 테이블 + 그라운딩 강화만**: 56노드 규모엔 단기 ROI가 높으나, `:Pattern` 모티프 멀티홉·스킬 그래프 성장을 표현 못 함 → 장기 제품 방향(채택 스코프)과 불일치. 본 ADR 범위에서 기각(단기 데모용으로는 별개 선택지).

## References

- 선행/연계: [ADR-0023](./ADR-0023-workflow-control-flow-engine.md) (control-flow L3 유한 순환 — 본 ADR의 모티프가 그 계약에 정합, validator 완화가 하드 선행), [ADR-0013](./ADR-0013-embedder-port-ssot.md) (Modal 호출 ai_agent 소유 예외 패턴 — Port 소유권 근거)
- 코드 증거: `modules/nodes_graph/domain/services/graph_validator.py:65-94` (순환 무조건 거부), `services/execution_engine/src/domain/services/cyclic_scheduler.py` (PR #359, 엔진 실행기 ✅), `modules/nodes_graph/domain/entities/node_definition.py:24-25` (I/O JSON Schema), `modules/nodes_graph/application/executable_node_types.py` (#387 그라운딩 미러)
- 관련 이슈: #372 (스킬↔노드 바인딩), #378/#387 (composer 구조노드 그라운딩)
