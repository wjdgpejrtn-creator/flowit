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
- 캡처는 골든셋 32건 × (13~16 LLM 콜) = Modal 비용/시간 발생. 라벨로 캡처본을 구분 보관.
