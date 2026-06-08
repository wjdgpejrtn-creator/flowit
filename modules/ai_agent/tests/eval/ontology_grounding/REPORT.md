# 온톨로지 그라운딩 평가 하니스 (ADR-0026 §6.5)

composer의 노드 그라운딩/모티프 품질을 **결정적으로 before/after 측정**하는 하니스.
A1(CAN_FOLLOW + expand_candidates 부활)·C(모티프 확장)·B(retrieval 튜닝) 같은
고도화가 실제로 품질을 올리는지 수치로 검증하는 전제 도구다.

## 구성

| 파일 | 역할 | 실 스택 필요 |
|------|------|:---:|
| `scenarios.py` | 골든 요청셋 32건(루프 8 / 선형 16 / 분기 4 / 잡담 4) + 정답지 | — |
| `metrics.py` | 5대 지표 순수 추출기(환각·순환·모티프·집계) | — |
| `records.py` | 스냅샷 row(RunRecord) + 로드/세이브 | — |
| `test_metrics.py` | 지표 추출기 결정적 단위 테스트(15건) | — |
| `check_snapshot.py` | `/ontology-eval` 본체 — 집계 + 베이스라인 회귀 게이트 | — |
| `run_eval.py` | 라이브 캡처 — 실 composer로 골든셋 1회 실행 → 스냅샷 | ✅ |

**핵심 분리**: 지표 계산은 순수/결정적(테스트로 검증), **라이브 캡처만** Modal+Neo4j+DB를
필요로 한다.

## 5대 지표 (§6.5)

| 지표 | 의미 | 방향 |
|------|------|:---:|
| validator-pass rate | 1차 초안이 retry 없이 검증 통과한 비율 | ↑ |
| 평균 retry 횟수 | draft/validate/qa 재시도 평균 | ↓ |
| hallucinated-node rate | 카탈로그(EXECUTABLE_NODE_TYPES 53종)에 없는 node_type 비율 | ↓ |
| motif-correctness | "루프 요청 → 실행가능 quality_gate_loop 생성" 성공률 | ↑ |
| qa pass rate(≥8) | qa_evaluator 통과 분포 | ↑ |

> 보조: distractor 정답률(잡담을 워크플로우 없이 무시한 비율).

### quality_gate_loop 판정 기준

validator §2(SCC 완화) + CyclicScheduler 계약과 1:1 정합: **유향 순환(back-edge) +
condition 노드 ≥1개**. condition = category=="condition" 8종
(`if_condition/switch_case/loop_count/loop_list/retry/merge_branch/stop_workflow/delay`).
둘 중 하나라도 없으면 모티프 미성립(엔진이 거부할 탈출불가 루프이거나 단순 분기).

## 사용 절차 (before/after)

```bash
# 0) 단위 테스트로 지표 로직 자체 회귀 확인(언제나 가능)
PYTHONUTF8=1 PYTHONPATH="modules:packages/common_schemas/python" \
  python -m pytest modules/ai_agent/tests/eval/ontology_grounding -q

# 1) 베이스라인 캡처(A1 적용 전) — cloud-sql-proxy + Modal/Neo4j env 필요
DATABASE_URL=... LLM_BASE_URL=... EMBEDDING_BASE_URL=... NEO4J_URI=... ... \
  python -m ai_agent.tests.eval.ontology_grounding.run_eval --label baseline-pgvector
python -m ai_agent.tests.eval.ontology_grounding.run_eval --promote-baseline

# 2) A1(CAN_FOLLOW) 적용 후 재캡처 → 회귀/개선 판정
python -m ai_agent.tests.eval.ontology_grounding.run_eval --label phase2a-canfollow
python -m ai_agent.tests.eval.ontology_grounding.check_snapshot   # 베이스라인 대비 게이트
```

`check_snapshot`는 베이스라인이 있으면 회귀 게이트(허용폭: 비율 5%p / 환각 3%p /
retry 0.5회), 없으면 현재 집계만 보고하고 통과한다.

## 라이브 캡처 주의

- 조립은 `services/agents/agent-composer/main.py`(boot+route)를 미러한다 — 그쪽 조립이
  바뀌면 `run_eval._build_orchestrator`도 따라가야 한다.
- 로컬 DB는 `DATABASE_URL`(cloud-sql-proxy, port 6544 ssl=False — `staging_node_catalog_reseed`
  레시피)로 붙는다. 평가용이라 GCS 영속 store는 None으로 둔다.
- AuraDB Free는 72h auto-pause — 캡처 전 콘솔 resume 확인.
- 캡처는 골든셋 32건 × (13~16 LLM 콜) = Modal 비용/시간 발생(시나리오당 ~2.5분). 라벨로 캡처본을 구분 보관.
- run_eval는 평가용이라 워크플로우를 DB에 저장하지 않는다(save no-op) + `EVAL_USER_ID`(기본 system) 사용.
- `--limit N`으로 앞 N개만 캡처(스모크/부분 측정).

## 측정 결과 — A1 CAN_FOLLOW (ADR-0026 §4.2a), 2026-06-08

CAN_FOLLOW expand 소비를 in-process로 before/after 측정(전체 32건 ×, Neo4j 엣지 0↔55 토글로 A/B).
**하니스가 ADD-all 회귀를 잡아 cap 정밀화로 수렴시킨 사례** — 본 하니스의 존재 이유.

| 지표 | baseline(엣지 0) | ADD-all | **capped(seed≤5·add≤3)** |
|------|:---:|:---:|:---:|
| drafter 실패 | 6 | 🔴 23 | ✅ 9 |
| qa pass(≥8) | 64.3% | 🔴 28.6% | ✅ 67.9% |
| qa 평균 | 7.93 | 🔴 5.64 | ✅ 8.07 |
| motif-correctness | 75% | 75% | ✅ 100% (8/8) |
| 평균 노드수(wf) | 3.00 | 2.50 | 3.25 |
| hallucination | 0% | 0% | 0% |

- **ADD-all = 명확한 회귀**: 후보 풀 비대(~24→38)로 Gemma 드래프터의 structured JSON이 잘림
  (drafter 실패 전부 `Invalid JSON: EOF`). → 폐기.
- **capped = 회귀 제거 + motif 직격 개선**: seed를 검색 상위 hit으로 제한 + 추가 ≤3개로 풀 비대 억제.
  drafter 실패 정상화(9), qa baseline 동등~상회, **motif 75→100%**(control-flow 그라운딩↑), 워크플로우 풍부화.
- **캐비엇**: 단일 샘플 A/B라 qa 소폭 개선은 LLM 노이즈 범위일 수 있음. 견고한 결론은 "ADD-all 회귀 + capped 무회귀+motif개선".
- **distractor 0%는 측정 불가 아티팩트**: run_eval는 composer를 직접 호출하나 잡담 fast-path는 상위
  Orchestrator에 있어 composer 단독엔 미적용. before/after 동일이라 A/B 결론엔 무영향.
