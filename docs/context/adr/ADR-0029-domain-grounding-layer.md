# ADR-0029: 도메인 그라운딩 레이어 — skill builder 전용 온톨로지(composer와 분리)

- **Status**: Accepted (조장 @dhwang0803 — 온톨로지 스키마/ETL 오너). 2026-06-12 세션 결정.
- **Date**: 2026-06-12
- **Deciders**: @dhwang0803 (조장, 온톨로지 스키마·ETL) — ADR-0028 O8/O9를 구체 스키마로 RESOLVE
- **Tags**: area/skills_builder, area/ai_agent, layer/domain, layer/adapters, topic/ontology
- **관련**: ADR-0026(온톨로지 GraphRAG·§6.6 결정적 스켈레톤), ADR-0028(스킬빌더 에이전트화 — O8 도메인 스키마/O9 적재), `docs/context/skills_builder_architecture.md` §8

## Context

composer 측 온톨로지는 성숙했다 — 범용 스켈레톤 8종(SSOT 라이브러리) + 53종 노드 카탈로그 그라운딩 + 32 시나리오 골든셋 + 5대 지표 결정적 하니스(`check_snapshot`)로 반복 검증하며 쌓였다(ADR-0026). 반면 **skill builder 측은 "배관만" 있다** — `Neo4jSkillProjector`의 게시-시 `(:Skill)-[:BINDS]->(:Node)` 투영(Phase 2b)뿐이고, **추출 단계에서 그라운딩에 쓸 도메인 지식/프로세스/지침이 그래프에 없다.**

핵심 통찰(2026-06-12 검토): 업종/직무마다 **① 업무 프로세스 구조 ② 단계별 주요 포인트 ③ LLM이 신뢰할 산출물을 만들게 하는 지침**이 모두 달라야 하는데, 현재는:
- 스켈레톤 = **순수 구조(topology)**, 도메인 지식 0.
- `seeds/industry_defaults/*.json` = 도메인 **연산(노드)** 단위까지만(스키마·설명은 좋으나 *프로세스/지침* 없음).
- 그 둘을 잇는 **도메인 프로세스 + 도메인 그라운딩 지침** 레이어가 부재 → 측정할 ground truth도 없음.

ADR-0028 O8/O9가 `(:Domain)-[:USES_SKELETON]/[:FORBIDS]` 등을 **제안(미확정)**하고 명명 확정을 조장에게 위임했다. 본 ADR이 그 스키마를 확정한다.

## Decision

### 분리 원칙 (불변식) — composer ↔ skill builder 비오염
1. **어휘 비충돌** — composer(Skeleton/SlotSpec/Pattern/FILLED_BY/CAN_FOLLOW/USES_ROLE)와 라벨·관계가 한 글자도 안 겹침.
2. **두 서브그래프 사이 traversable 엣지 0** — composer 쿼리가 도메인 라벨을 MATCH하지 않고, 그 반대도 없음.
3. **노드 카탈로그는 "값"으로만 공유** — 도메인 레이어는 `:Node`로 엣지를 걸지 않고 **node_type 문자열**로 보유하며 ETL이 `EXECUTABLE_NODE_TYPES`로 검증(환각 차단). 카탈로그 SSOT는 공유하되 그래프는 안 닿음.
4. **코드 경로 분리** — 전용 Port/Adapter/ETL/시드/골든. composer 파일은 한 줄도 안 건드림.

### 스키마 (전용 라벨/관계)
```cypher
(:Domain  {code, name, kind, description})            // kind ∈ {industry, function}
(:Playbook {id, name, intent, summary})               // 도메인 최적화 프로세스(구조)
(:Stage   {id, order, role, purpose, key_points,      // 순서·역할 단계 + 주요 포인트
           allowed_node_types})                       //   node_type 문자열 배열(엣지X, 검증O)
(:Rule    {id, kind, statement, node_type, rationale, severity})
           // kind ∈ {required, forbidden, focus, caution, format}

(:Domain)-[:HAS_PLAYBOOK]->(:Playbook)
(:Playbook)-[:HAS_STAGE]->(:Stage)
(:Domain)-[:HAS_RULE]->(:Rule)
(:Playbook)-[:HAS_RULE]->(:Rule)
(:Domain)-[:HAS_SUBDOMAIN]->(:Domain)                 // (선택) 업종↔직무 계층
// composer로 가는 엣지: 0. :Node/:Skeleton/:Pattern 미참조.
```
- **`DERIVES_FROM :Skeleton` 채택 안 함** — composer 스켈레톤에 결합하지 않고 Playbook이 자기 구조를 독립 보유. 생성 워크플로우의 구조적 유효성은 `GraphValidator`가 compose 시점에 별도 검증하므로 잃는 게 없다.
- 물리 격리는 **같은 Neo4j + 전용 라벨/어댑터(논리 분리)** 채택(카탈로그 중복 0, 운영비 0). 더 강한 격리가 필요하면 별도 DB는 후속 결정.

### 매핑(① 구조 / ② 포인트 / ③ 지침)
| 도메인 차별점 | 그래프 |
|---|---|
| 프로세스 구조 | `:Playbook` → `:Stage`(order·role) |
| 단계별 주요 포인트 | `:Stage.key_points` |
| LLM 그라운딩 지침 | `:Rule`(required/forbidden = 노드 제약 또는 프로세스 must / focus·caution·format = 자유 지침) |

### 소비 경로 (추출 그라운딩)
skill builder 추출(SOP/인터뷰)이 `DomainGroundingPort.get_domain_grounding(code)`로 묶음 회수 →
프롬프트에 **프로세스 레일 + 단계 포인트 + 지침 + 필수/금지**를 주입 → LLM은 그 안에서 파라미터/문구만 채움(composer 스켈레톤 param-fill과 동형). 산출: **SKILL.md**(도메인 지식·제약 중심) / **COMPOSER.md**(구조·BINDS 중심) — `skills_builder_architecture.md`의 두 문서가 온톨로지로 backing됨.

## 산출물 (P0 — 본 ADR과 함께 머지)
- VO: `modules/ai_agent/domain/value_objects/domain_grounding.py` (Domain/Playbook/Stage/Rule/Bundle + `parse_domain` 검증)
- Port: `modules/ai_agent/domain/ports/domain_grounding_port.py` (`DomainGroundingPort`)
- Adapter: `modules/ai_agent/adapters/ontology/neo4j_domain_grounding_adapter.py` (도메인 라벨만 질의)
- ETL: `scripts/build_domain_ontology.py` (전 재투영, 멱등, composer ETL과 별개 스크립트)
- 시드: `modules/ai_agent/seeds/domains/*.json` (레퍼런스 `ecommerce.json`)
- 골든: `modules/ai_agent/tests/eval/skill_grounding/` (P2 — ontology_grounding 미러)

## Phasing
| Phase | 배선 | 데이터(조장) |
|---|---|---|
| **P0** (본 ADR) | 스키마·VO·Port·Adapter·ETL·골든 뼈대 + `ecommerce.json` 레퍼런스 | 포맷 검증 완료 |
| P1 | 추출 use case에 소비 쿼리 + 프롬프트 그라운딩 배선 | — |
| P2 | 골든 시나리오·지표(process_adherence/required_coverage/forbidden_violation/grounding_presence/hallucinated_node) + `check_snapshot` 게이트 | 도메인 골든 truth |
| P3 | — | 업종/직무 도메인 지식 합성·적재(쌓아올리기) |

## Consequences
- (+) composer 무오염 — composer 코드/쿼리/ETL 미변경, 두 서브그래프 disjoint(어댑터 테스트가 라벨 비참조를 가드).
- (+) ADR-0028 O8(스키마)/O9(적재)를 구체 RESOLVE. 측정 ground truth의 토대 마련(P2 하니스로 "좋은 스킬" 정량화 가능 → composer가 입증한 반복개선 루프를 skill builder에도 이식).
- (−) 핫패스에 도메인 회수 1쿼리 추가(추출 시) — 짧은 단일 MATCH라 경미.
- (−) 도메인 지식은 사람이 시드를 채워야 함(P3) — 본 레이어는 그 그릇. ETL이 환각 node_type을 거부해 품질 하한 보장.
