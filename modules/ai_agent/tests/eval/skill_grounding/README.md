# skill_grounding — 도메인 그라운딩 추출 품질 하니스 (ADR-0029, P2)

composer의 `ontology_grounding/`(스켈레톤 그라운딩 측정)에 대응하는 **skill builder 버전**.
도메인 그라운딩(`:Domain/:Playbook/:Stage/:Rule`)이 추출 품질을 실제로 올리는지 결정적으로 측정한다.

> **상태: 뼈대(P0).** 스키마·ETL·Port/Adapter(P0)는 머지됐고, 본 하니스의 실측 캡처/게이트는
> **P2**에서 `ontology_grounding`의 `records.py`/`metrics.py`/`check_snapshot.py` 구조를 미러해 채운다.
> P1(추출 use case에 그라운딩 소비 배선)이 선행돼야 측정할 산출물이 생긴다.

## 측정할 지표 (composer 5대 지표 대응)
| 지표 | 의미 |
|---|---|
| `process_adherence` | 추출 스킬이 도메인 Playbook의 Stage 순서·역할을 따르는 비율 |
| `required_coverage` | 도메인/플레이북 `required` 노드·must를 충족한 비율 |
| `forbidden_violation_rate` | `forbidden` 노드/규칙 위반 비율(낮을수록 좋음) |
| `grounding_presence` | 산출 SKILL.md에 도메인 지침(focus/caution/format)이 반영된 비율 |
| `hallucinated_node_rate` | `EXECUTABLE_NODE_TYPES` 외 node_type 산출 비율(=0 유지) |

## 골든셋 (P2)
도메인 × 입력(SOP/인터뷰) → 기대 산출(프로세스 구조·필수노드·지침). `scenarios.py`로 시드,
`snapshots/`에 baseline 캡처, `check_snapshot.py`로 회귀 게이트(composer 패턴 동일).

## 분리 원칙
composer `ontology_grounding`과 **별도 디렉토리·별도 골든·별도 게이트**. 서로의 스냅샷/지표를 공유하지 않는다(ADR-0029 분리 불변식).
