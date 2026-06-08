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

## 측정 결과(권위) — A1 CAN_FOLLOW 양팔 de-noise (ADR-0026 §6 우선1), 2026-06-08

**단일 샘플 A/B는 이 하니스의 LLM 노이즈에서 신뢰 불가**가 1차 결론. 따라서 양팔(A1-OFF
엣지 0 / A1-ON 엣지 55) **각 3회 반복** 후 평균±std로 효과를 산출했다. 토글은 Neo4j
CAN_FOLLOW 엣지만 0↔55(Pattern/Node/BINDS 불변), 측정 후 55 복원.

| 지표 | dir | OFF 평균±std (3run) | ON 평균±std (3run) | **A1 효과** | 유의성 |
|------|:---:|:---:|:---:|:---:|:---:|
| hallucination | ↓ | 0.000±0.000 | 0.000±0.000 | ±0 | · |
| validator-pass | ↑ | 0.417±0.073 | 0.476±0.017 | +0.060 | · 노이즈내 |
| **avg_retry** | ↓ | 0.798±0.236 | 0.536±0.077 | **−0.262** | ~ **robust** |
| motif-correctness | ↑ | 0.667±0.212 | 0.792±0.118 | +0.125 | · 노이즈내 |
| qa_score(평균) | ↑ | 7.048±0.485 | 6.929±0.823 | −0.119 | · 노이즈내 |
| qa_pass(≥8) | ↑ | 0.512±0.045 | 0.500±0.105 | −0.012 | · 노이즈내 |

유의성: ✓ |효과|>std합 / ~ |효과|>max(std) / · 노이즈내.

- **A1 = 무회귀.** qa_pass −0.01(평평)·qa_score −0.12(노이즈내)로 회귀 없음.
- **유일한 robust 이득 = retry 감소**(0.80→0.54, 효과>max std). 후보 그라운딩 개선 → 재초안 루프 ↓.
- **motif·validator는 방향만 양(+)**, std 안에 묻혀 robust 아님. **직전 단일샘플의 "motif 75→100%"는 노이즈**였다.
- **hallucination은 양팔 0** — A1 이전(EXECUTABLE_NODE_TYPES #378)부터 0이라 A1 공로 아님.

### ⚠️ baseline.json 교정 (중요)
직전 커밋된 `baseline.json`(qa_pass 0.643 / motif 0.75)은 **운 좋은 단일 샘플**이었다.
de-noise한 진짜 A1-OFF는 qa_pass **0.512** / motif **0.667**. 이 오염된 baseline과 ON-only를
비교하면 가짜 qa 회귀가 보인다(직전 세션 오판 원인). → 회귀 게이트의 baseline을 **de-noise한
A1-ON arm 평균**(현 배포 상태)으로 교정해 향후 §6.1 모티프 작업이 현 상태 대비 측정되게 한다.

### (참고) 직전 단일 샘플 A/B — superseded
ADD-all이 후보 풀 비대(~24→38)로 Gemma structured JSON을 잘라 drafter 실패 폭증(6→23,
qa pass 64→29%) → cap 정밀화(seed≤5·add≤3)로 폐기·수렴시킨 기록. **cap이 ADD-all 회귀를
제거한다는 결론은 유효**(위 양팔 측정의 무회귀와 정합). 다만 그때의 "capped qa 67.9% / motif
100%" 절대 수치는 단일 샘플 노이즈로, 위 양팔 평균이 대체한다.

- **distractor 0%는 측정 아티팩트**: run_eval가 composer를 직접 호출하나 잡담 fast-path는 상위
  Orchestrator 소관이라 composer 단독엔 미적용. 양팔 동일이라 A1 결론엔 무영향.
