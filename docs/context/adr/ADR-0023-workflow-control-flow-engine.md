# ADR-0023: 사용자 워크플로우 control-flow 엔진 (데이터 흐름 · 조건 분기 · 유한 순환)

- **Status**: Proposed
- **Date**: 2026-06-04
- **Deciders**: @dhwang0803 (execution_engine), @<nodes_graph owner>, @<ai_agent owner>
- **Tags**: area/execution, layer/domain, req/007

## Context

현재 사용자 워크플로우 실행엔진은 **위상정렬 후 각 노드를 정적 파라미터로 순서대로 실행**할 뿐이다. 확인된 한계:

1. **노드 간 데이터 흐름이 없다.** `ExecuteWorkflowUseCase`가 모든 노드에 동일한 `context.parameters`를 넘기고(`execute_workflow.py`), `_build_input`은 `{**node.parameters, **inputs}`만 병합한다(`catalog_node_executor.py`). 상류 노드의 `output`은 `NodeResult`로 수집만 되고 하류 입력으로 **전달되지 않는다**. 엣지는 실행 순서만 결정한다.
2. **조건 분기가 없다.** 한 레벨의 모든 노드가 무조건 실행된다. `if_condition`/`switch_case` 노드가 있어도 "안 탄 가지"를 skip하지 않는다.
3. **순환이 없다.** `GraphValidator`와 `TopologicalScheduler.validate_dag` 모두 cycle을 `E_CYCLE_DETECTED`로 거부한다. "품질 게이트 미통과 시 재실행" 같은 반복을 그래프로 표현할 수 없다.

목표는 사용자 워크플로우를 **실제 데이터 파이프라인 + 제어흐름**으로 만드는 것이다(예: `시트 읽기 → 요약 → 품질검증 → 미통과면 재요약 루프 → 통과면 슬랙 전송`). 실제 제품 역량 강화가 목적이며, agentic 반복(루프)을 1급으로 지원한다.

## Decision

control-flow를 **3개 층으로 점진 도입**한다. 각 층은 다음 층의 토대다.

### L1 — 데이터 흐름 (reference resolution) ← 본 ADR의 즉시 결정
- 노드 파라미터 값에 **상류 출력 참조**를 쓸 수 있다: `${<from_instance_id>.<output_field>}`.
  - 값 전체가 단일 참조면 **타입 보존**(예: 숫자·객체 그대로), 문자열 안에 임베디드면 문자열화 보간.
  - instance_id는 UUID(점 없음)라 마지막 `.` 기준 분리로 모호성 없음.
- `ExecuteWorkflowUseCase`가 레벨 완료마다 `NodeResult.output`을 `node_outputs[instance_id]`에 누적하고, 노드 dispatch 직전 그 노드의 파라미터를 `node_outputs`로 해석한다. 미해결 참조(상류 실패/누락)는 빈 문자열/`None`으로 degrade하고 경고.
- **위상정렬·executor·common_schemas 스키마 무변경.** 신규 도메인 서비스 `ReferenceResolver` + `execute_workflow` 배선만. 엣지는 여전히 의존/순서, 참조는 데이터 매핑(직교).

### L2 — 조건 분기 (live-edge reachability) ← 본 ADR 확정 (구체 규약)
- **분기 핸들 규약**: 조건 노드(category `"condition"`)의 출력 중 **데이터 pass-through용 `value`를 제외한 string 필드값**이 *live한 출력 핸들 이름*이다. 실측: `if_condition` → `branch:"true"|"false"`, `switch_case` → `matched_case:"<case>"`. 엣지의 `from_handle`이 그 값과 일치하면 live, 아니면 dead.
- **degrade(하위호환)**: 조건 노드라도 출력에 selector가 없거나, outgoing 엣지 중 selector와 일치하는 게 하나도 없으면(예: from_handle이 전부 `"output"`인 레거시) **전부 live**로 처리해 그래프를 고립시키지 않는다.
- **reachability 실행(위상정렬 유지)**: 레벨-스케줄러를 교체하지 않는다. DAG라 노드 처리 시점에 모든 선행이 끝나 있으므로, 실행 전 "incoming 엣지 중 live한 게 ≥1개(또는 루트)"면 reachable→실행, 아니면 `skipped`(미실행). skip은 하류로 전파(전부 dead면 연쇄 skip). `NodeResult.status`의 기존 `"skipped"` 사용.
- 신규 도메인 서비스 `BranchEvaluator`(live 판정 순수 로직) + `ExecuteWorkflowUseCase` reachability 배선. validator 무변경(엔진이 liveness 처리). 여전히 **비순환**.

### L3 — 유한 순환 (quality-gate loop)
- back-edge 허용 + **max-iteration 가드** + 반복별 결과 키 `(instance_id, iteration)`.
- `GraphValidator`/`validate_dag`의 cycle 무조건 거부 → **"유한·탈출가능 cycle 허용"**(모든 cycle에 break 가능한 condition + max_iterations 보유)으로 전환.
- scheduler를 순환 실행(work-queue + 방문 카운터)으로. 미통과 시 루프 바디 재실행, 가드 도달 시 강제 탈출.

## Consequences

### Positive
- L1만으로 모든 다중노드 워크플로우가 실제로 이어진다(데이터가 흐른다).
- L2/L3로 검증·재시도·분기 등 agentic 패턴을 사용자 워크플로우 1급으로 지원.
- 각 층이 독립 배포 가능(L1은 위상정렬 위에서 동작 → 회귀 위험 낮음).

### Negative / Trade-offs
- L2/L3는 레벨-스케줄러를 동적 실행기로 교체 → execution_engine 코어 재작성.
- 참조 문법은 composer/editor가 생성·편집해야 의미 있음(엔진 단독으론 토대만).
- 무한 루프 방지를 위해 max-iteration 가드가 필수 — 미설정 cycle은 검증 거부 유지.

### Follow-ups
- L1 composer: drafter가 "가져와야 할 입력"에 리터럴 대신 `${상류.출력}` 참조 생성(C 항목).
- L1 editor: 엣지 연결 시 출력→입력 필드 매핑 UI.
- L2/L3: validator handle/cycle 규약 + scheduler 동적 실행기(별도 ADR 보강 가능).

## Alternatives Considered

- **엣지 핸들 기반 필드 매핑**(from_handle=출력필드, to_handle=입력필드): 시각적이나 부분 문자열 보간·다중 참조에 약하고 현 핸들 모델(레이아웃/방향)과 충돌. 기각.
- **필드명 자동 병합**(상류 출력을 하류 입력에 이름으로 자동 주입): 암묵적·충돌 모호. 기각.
- **DAG 유지 + 분기로만 품질 게이트**(루프 없이 유한 펼치기): 실제 반복 불가 → 제품 목표 미달. 기각(L3 채택).

## References

- 본 시리즈: 데이터 흐름 없음 진단(`execute_workflow.py:92`, `catalog_node_executor._build_input`)
- 관련: ADR-0018(노드 독립 실행 경로), `TopologicalScheduler`, `GraphValidator._detect_cycles`
