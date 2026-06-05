# ADR-0025: 재개 가능한 실행 — 협조적 pause + 체크포인트 resume

- **Status**: Proposed
- **Date**: 2026-06-05
- **Deciders**: @dhwang0803 (execution_engine, api_server, frontend)
- **Tags**: area/execution, layer/domain, req/007, req/010
- **관련 이슈**: #364 (워크플로우 일시정지 미배선 + resume이 체크포인트 없이 전체 재실행)

## Context

REQ-007 실행엔진은 워크플로우를 위상정렬 후 step(레벨/루프 바디) 단위로 순차 실행한다(ADR-0023). 일시정지/재개는 도메인 모델(`PauseResumeUseCase`, `ExecutionStatus.PAUSED`, `VALID_TRANSITIONS`)에만 존재하고 **런타임에 배선되어 있지 않았다**. UI e2e 테스트(2026-06-04, control-flow 배포 후) 중 확인된 결함:

1. **pause 진입 경로 부재**: `common_schemas.broker_tasks`에 `TASK_PAUSE_EXECUTION` 없음, api_server `exec_control.py`에 `/pause` 엔드포인트 없음, 엔진에 `pause_execution_task` 없음. `PauseResumeUseCase`가 `action="pause"`를 지원하나 **호출자가 없어** execution이 `PAUSED`에 도달 불가 → 재개 버튼은 dead.

2. **실행 중 executions row 부재**: `ExecuteWorkflowUseCase.execute()`가 **종료 시점에만** `execution_repo.save(result)`를 호출했다. api_server `/execute`는 `execution_id`(UUID)만 만들어 Celery dispatch할 뿐 row를 INSERT하지 않는다. 따라서 실행 중에는 `executions` row가 존재하지 않아:
   - pause를 보내도 `PauseResumeUseCase.get()`이 `NotFoundError` → graceful skip(아무 일도 안 일어남).
   - 실행 루프에 협조적 중단 체크를 넣어도 재조회할 status가 없음.

3. **resume이 전체 재실행**: resume은 같은 `execution_id`로 `trigger_type="resume"` execute를 재디스패치하나, `execute()`가 `trigger_type`을 **무시**하고 워크플로우를 처음부터 전체 실행했다. 이미 성공한 노드(Slack 전송, 시트 쓰기 등)를 **재실행 → 외부 부작용 중복**.

cancel은 Celery `revoke(terminate=True)`로 worker task를 강제 종료하므로 부분적으로 동작했으나, 실행 루프에 협조적 중단 지점이 없어 노드 실행 도중에는 즉시 멈추지 않았다.

## Decision

워크플로우 실행을 **재개 가능(resumable)** 하게 만든다. 핵심은 (a) 실행 중에도 `executions` row를 영속해 제어 가능 상태로 두고, (b) step 경계에서 협조적으로 pause를 감지하며, (c) resume 시 완료 노드를 재실행하지 않고 이어가는 것이다.

### ① pause 배선 (api_server + 엔진 + common_schemas)
- `common_schemas.broker_tasks.TASK_PAUSE_EXECUTION = "execution_engine.pause_execution"` 추가(SSOT).
- `POST /api/v1/executions/{id}/pause` (api_server `exec_control.py`) — cancel/resume과 동일한 소유자 검증 후 `send_task`. 202 + `ControlResponse(action="pause")`.
- `pause_execution_task` (엔진 `celery_tasks.py`) — `pause_resume_use_case.execute(id, "pause")`. cancel/resume과 동일한 `DomainError` graceful-skip 패턴(이미 종료/미존재 execution은 사용자 입력 오류 범주).
- pause task는 **status만 PAUSED로 전환**한다. 실행 중인 worker를 직접 죽이지 않는다 — 협조적 중단(②)에 맡긴다.

### ② 협조적 pause (step 경계 체크) + 실행 중 row 영속
- `execute()`가 **실행 시작 시점에 RUNNING row를 save**한다(직전엔 종료 시점에만 save). 이것이 폴링/pause 조회/협조적 재확인의 전제다.
- step(레벨/루프) **진입 직전마다** `execution_repo.get(execution_id).status`를 재조회한다. `PAUSED`면 누적 `node_results`를 보존한 채 루프를 중단하고, **완료/실패 마킹 없이** status=PAUSED로 최종 save한다(`mark_completed`/`mark_failed` 호출 안 함).
- **step마다 부분 결과를 체크포인트로 save**한다(폴링 진행률 노출 + crash 시에도 resume이 끝난 step부터 이어가게 함).
- 조회 실패(broker/DB 일시 오류) 시 보수적으로 **계속 실행**(중단하지 않음) — pause는 best-effort.

### ③ 체크포인트 resume (완료 노드 재디스패치 skip)
- `trigger_type == "resume"`이면 `execute()`가 직전 실행의 `executions.node_results`(JSON 컬럼, 이미 full `NodeResult` 영속)를 로드한다.
- 상태가 `succeeded`/`skipped`인 노드를 복원: `node_outputs`(L1 `${ref}` 소스)·`reachable`(L2)를 시드하고, 해당 노드들을 `completed_ids`로 표시 + UI 복원용 `node_complete` 이벤트 재발행.
- step 진입 시 **그 step의 모든 노드가 `completed_ids`에 있으면 재실행 skip**(`continue`) — 하류 컨텍스트는 위 시드로 이미 복원됨. 첫 미완료 step부터 정상 실행.
- 체크포인트 조회 실패(row 없음 등)면 체크포인트 없이 **처음부터 전체 실행**(graceful degrade).

### 체크포인트 granularity = **step 단위** (의도적 결정)
협조적 pause는 **step 경계에서만** 발동하므로 step은 원자적으로 끝난다 — 부분 완료 step이 존재하지 않는다. 따라서 저장된 `node_results`는 항상 "완전히 끝난 step"의 결과만 담고, "그 step의 모든 노드 완료" 판정이 곧 step 완료 판정이다. 노드 단위 부분 체크포인트(특히 **루프 iteration 중간** 복원)는 본 ADR 범위가 아니다.

- **루프(ADR-0023 L3) 중간 pause**: 루프 바디 노드는 iteration마다 `(instance_id, iteration)`로 append되며 `force_run`된다. 루프 step이 **완전히 끝나기 전**(자연/강제 탈출 전) pause되면 그 루프 step은 `node_results`에 부분만 남고 "전체 완료"가 아니므로 resume 시 **루프 step 전체를 처음부터 재실행**한다. iteration 중간 재개는 후속(루프 바디 부작용 멱등성 보장이 선결).

## Consequences

### Positive
- pause/resume이 실제로 동작한다(#364 해소). resume이 완료 노드를 재실행하지 않아 **외부 부작용 중복이 사라진다**.
- 실행 중 `executions` row가 존재해 폴링이 실시간 진행률/상태를 보고하고, cancel/pause 조회가 안정적으로 동작한다.
- step별 체크포인트로 worker crash 후에도 resume이 끝난 step부터 이어간다(내결함성 향상).

### Negative / Trade-offs
- step마다 `save` + step마다 `get`(pause 체크) → DB 왕복 증가. 워크플로우 step 수가 적어(보통 한 자리수) 비용은 작다.
- pause 지연 = 현재 step 완료까지(노드 실행 도중에는 멈추지 않음). 3노드 ~1s 워크플로우는 pause 윈도가 사실상 0 — 짧은 워크플로우는 pause 체감 효과가 작다(설계상 한계, UI 툴팁으로 설명).
- 루프 iteration 중간 재개 미지원(위 granularity 한계). 루프 바디가 비멱등 부작용을 가지면 resume 시 그 루프를 재실행하므로 중복 가능 — composer가 루프 바디에 멱등 노드를 배치하도록 유도 필요(후속).
- 동시성: pause task의 save와 worker의 step save가 경합할 수 있으나, worker는 PAUSED 감지 후 **마지막에** 저장하므로 `node_results`는 보존된다. cancel(`revoke`)은 기존대로 즉시 강제 종료 경로 유지.

## Alternatives considered
- **worker를 즉시 강제 종료(revoke)해서 pause**: cancel처럼 task를 죽이면 부분 결과/in-memory 상태가 유실되고 노드 실행이 비정상 중단된다. pause는 "재개 가능"이 핵심이라 협조적 중단이 적합.
- **api_server가 dispatch 시점에 PENDING row를 INSERT**: 실행 중 row 부재를 api 쪽에서 해결하는 대안. 그러나 실행 상태의 소유자는 엔진이며(트랜잭션·task_queue_id 일관성), 엔진이 시작 시 RUNNING으로 save하는 편이 ADR-0023 흐름과 정합. (api INSERT는 별도 트랜잭션·상태 drift 위험.)
- **노드 단위 / 루프 iteration 단위 체크포인트**: 정확하나 부분 상태 복원·멱등성 보장이 크게 복잡. step 경계 pause로 granularity를 step에 고정해 복잡도를 억제(YAGNI).

## Implementation notes
- 엔진: `services/execution_engine/src/application/use_cases/execute_workflow.py`(시작 save + step별 save + `_is_pause_requested` + `_load_checkpoint` + step skip), `adapters/celery_tasks.py`(`pause_execution_task`).
- api_server: `app/routers/exec_control.py`(`POST /pause`).
- common_schemas: `broker_tasks.py`(`TASK_PAUSE_EXECUTION`).
- frontend(REQ-010): `lib/api/workflowApi.ts`(`pauseExecution`) + `app/workflows/[id]/page.tsx`·`RunMode.tsx`(⏸ 버튼 + 버튼 disabled 사유 툴팁).
- `PauseResumeUseCase`/`ExecutionOrchestrator.VALID_TRANSITIONS`는 무변경(이미 pause/resume 전이 지원).
