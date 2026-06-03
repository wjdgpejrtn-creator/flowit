# Supervisor Loop 승격 — 구현 설계서

> REQ-004 ai_agent / Main Orchestrator
> 작성: 2026-06-03 황대원 (조장) · REQ-004 오너 신정혜 협의 대상 (사후 통지)
> 대상 코드: `modules/ai_agent/adapters/supervisor.py` (`LangGraphSupervisor`)
> 관련 결정: ADR 미발급 (본 문서가 선행 설계), 메모리 `supervisor-loop-promotion-inflight`

---

## 0. 한 줄 요약

지금의 Main Orchestrator는 이름만 supervisor일 뿐 **1-홉 디스패처**다 (intent 1회 분류 → sub-agent 1개 relay → 종료). 이를 **순수 라우터 함수 + imperative 제어 루프**로 승격해, ① 재라우팅/복구 루프, ② 복합 의도의 고정 레시피 조합, ③ HandoffPayload 기반 복구 경로를 지원한다. LangGraph는 도입하지 않는다 (composer 내부 그래프만 LangGraph 유지).

---

## 1. 현행 진단 (as-is)

### 1.1 실제 코드 구조

라이브 배선: `services/agents/orchestrator/main.py` → `LangGraphSupervisor` (이름과 달리 LangGraph 아님, imperative async generator).

```
stream()
 └ _run()                         # 단일 패스, 복귀 없음
     ├ (round==2) → composer relay → update_memory → END   # two-shot 2차 특례
     ├ load_memory_node           # HTTP → personalization
     ├ intent_node                # IntentAnalyzerService (단일 라벨)
     └ route (1회 if/elif 분기):
         None            → general_chat_node (LLM 1 call)
         FAST_INTENTS    → fast_response_node (LLM 0 call)
         propose         → finalize_node
         build_skill     → skills relay → update_memory
         COMPOSER_INTENTS→ composer relay → update_memory
       END
```

### 1.2 문제점

| # | 문제 | 근거 (코드) |
|---|------|-------------|
| P1 | **복귀 루프 없음** — sub-agent 실패/부분완료 시 재시도·대체 경로 불가. relay 예외는 ErrorFrame yield 후 그냥 종료 | `supervisor.py:264-276` `_relay_stream` except → ErrorFrame, 루프 없음 |
| P2 | **라우팅 로직이 `_run`에 인라인** — 순수 함수가 아니라 async generator 본문에 섞임. 단위 테스트 시 전체 스트림을 돌려야 함 | `supervisor.py:161-218` if/elif 체인 |
| P3 | **복합 의도 표현 불가** — `intent_node`가 단일 `intent` 문자열만 반환. `skill_then_compose`(스킬 만들고 그걸로 워크플로우) 같은 요청을 한 경로로 못 묶음 | `intent_analyzer_service.py:99` 단일 `IntentResult` |
| P4 | **HandoffPayload 미연결** — common_schemas에 복구 계약(`recovery_mode`/`result_review`)이 있으나 supervisor는 안 씀. execution_engine만 소비 | `handoff.py`, `services/execution_engine/.../handle_handoff` |
| P5 | **죽은 중복 구현** — `application/agents/orchestrator/route_request_use_case.py`의 `RouteRequestUseCase`는 spec §3.1 형태지만 **어디에도 배선 안 됨**. 평행 구현 2개 | orchestrator main은 `LangGraphSupervisor`만 import |
| P6 | **two-shot 2차가 특례 분기** — `round==2`를 `_run` 맨 앞에서 가로채는 ad-hoc 처리. 루프가 있으면 자연스러운 resume 한 단계로 흡수 가능 | `supervisor.py:130-140` |

### 1.3 핵심 통찰

`LangGraphSupervisor`는 이미 imperative async generator라서 **루프 셸로 감싸는 비용이 작다.** 메모리의 "imperative 루프 + 순수 라우터" 결정은 사실상 절반 반영된 상태 — 라우터를 함수로 빼고, `_run`을 루프로 바꾸면 된다.

---

## 2. 목표 구조 (to-be)

### 2.1 제어 루프

```
stream()
 └ _run()
     ├ load_memory  (루프 입구 북엔드 — 1회)
     ├ analyze_intent → RoutePlan (레시피 키 + 스텝 큐)
     └ LOOP (while step := plan.next()):
         ├ route(state, plan) → target            # 순수 함수
         ├ dispatch(target, state) → frames, delta # relay or local node
         ├ state = merge(state, delta)             # state merge 규칙(§5)
         ├ on error → recovery_target(state, handoff)  # 재시도/대체/포기
         └ plan.advance(result)                    # 다음 스텝 or 종료
     └ update_memory  (루프 출구 북엔드 — 1회)
       END
```

핵심: **forward dispatch = state read, loop-back = state write.** 에이전트끼리 직접 통신하지 않고 supervisor가 소유한 canonical state를 통해서만 연결된다 (state-mediated).

### 2.2 컴포넌트 분해

| 컴포넌트 | 위치 | 성격 | 비고 |
|---------|------|------|------|
| `RoutePlan` (VO) | `ai_agent/domain/value_objects/route_plan.py` | 신규 | 레시피 키 + 잔여 스텝 큐 + 커서 |
| `route()` 라우터 함수 | `ai_agent/domain/services/supervisor_router.py` | 신규, **순수** | `(state, plan) → RouteTarget`. LLM 호출 없음 |
| `RECIPES` 테이블 | 동 파일 | 신규, 상수 | intent/복합키 → 스텝 시퀀스 |
| `recovery_target()` | 동 파일 | 신규, 순수 | `(state, handoff) → RouteTarget | None` |
| 제어 루프 셸 | `ai_agent/adapters/supervisor.py` | 개편 | `_run`을 루프로 |
| 복합 의도 분류 | `intent_analyzer_service.py` | 개편 | 복수 라벨/레시피 키 |
| `RouteRequestUseCase` | `application/agents/orchestrator/` | **삭제** | 죽은 중복 (P5) |

도메인 규칙(라우팅·복구·레시피)은 `domain/services`·`domain/value_objects`에 두어 **순수 단위 테스트** 가능하게 하고, 어댑터(`supervisor.py`)는 HTTP relay·SSE yield·state merge 오케스트레이션만 담당한다 (Clean Architecture 경계 준수).

---

## 3. 라우터 함수 (deterministic, LLM 아님)

```python
# domain/services/supervisor_router.py  (의사코드)

class RouteTarget(str, Enum):
    LOAD_MEMORY = "load_memory"
    GENERAL_CHAT = "general_chat"
    FAST_RESPONSE = "fast_response"
    FINALIZE = "finalize"
    COMPOSER = "composer"
    SKILLS = "skills"
    UPDATE_MEMORY = "update_memory"
    DONE = "done"

# 레시피 = intent(또는 복합 키) → forward 스텝 시퀀스
RECIPES: dict[str, list[RouteTarget]] = {
    "chitchat":         [RouteTarget.FAST_RESPONSE],
    "info_question":    [RouteTarget.FAST_RESPONSE],
    "control":          [RouteTarget.FAST_RESPONSE],
    "workflow_execute": [RouteTarget.FAST_RESPONSE],
    "propose":          [RouteTarget.FINALIZE],
    "draft":            [RouteTarget.COMPOSER],
    "refine":           [RouteTarget.COMPOSER],
    "clarify":          [RouteTarget.COMPOSER],
    "build_skill":      [RouteTarget.SKILLS],
    # ── 복합 레시피 (신규) ──
    "skill_then_compose": [RouteTarget.SKILLS, RouteTarget.COMPOSER],
    None:               [RouteTarget.GENERAL_CHAT],  # 미분류
}

def route(plan: RoutePlan) -> RouteTarget:
    """순수 함수: 현재 plan 커서가 가리키는 다음 스텝. 끝이면 DONE."""
    return plan.peek() or RouteTarget.DONE
```

**결정 규칙**: LLM은 라우팅에 관여하지 않는다. 의도 분류(LLM 가능)는 `intent_node`에서 끝나고, 거기서 나온 레시피 키로 `RECIPES`를 조회할 뿐이다. → 라우팅 재현성·테스트 용이성 확보.

---

## 4. 복합 의도 분류 (가장 약한 고리)

현 `IntentAnalyzerService`는 단일 라벨. 복합 레시피를 쓰려면 **레시피 키**를 뽑아야 한다.

### 4.1 최소 변경안 (이번 범위)

`analyze()`가 `IntentResult` 하나 대신 **레시피 키 문자열**을 추가로 결정한다. 단일 의도는 키 = intent 값 그대로, 복합만 별도 키.

```python
# fast classifier에 복합 규칙 추가 (정규식 우선순위로)
#   "스킬 만들어서 ... 워크플로우"  → "skill_then_compose"
#   그 외 → 기존 단일 intent를 키로 사용
```

복합 분류는 fast-path 정규식으로 시작하고(보수적), 애매하면 단일 의도로 폴백한다. **완전 동적 체이닝은 범위 제외** — 화이트리스트 레시피만.

### 4.2 RoutePlan VO

```python
@dataclass
class RoutePlan:
    recipe_key: str | None
    steps: list[RouteTarget]      # RECIPES[recipe_key] 복사본
    cursor: int = 0
    def peek(self) -> RouteTarget | None: ...
    def advance(self) -> None: ...   # cursor += 1
    def insert(self, target) -> None: ...  # 복구 시 대체 스텝 삽입
```

---

## 5. State merge 규칙

`AgentState`는 **frozen**(불변)이므로 루프 내 누적은 두 방법 중 하나:
- (A) supervisor 내부 mutable `_State` TypedDict 유지(현행) + 스텝 결과를 거기 누적, sub-agent 호출 시점에만 `AgentState` 조립.  ← **채택**
- (B) `state.model_copy(update=...)` 매 홉. frozen 재생성 비용 + 필드 누락 위험.

(A) 채택 이유: 현행 `_State`가 이미 mutable 작업 영역. 여기에 누적 필드 추가.

| 필드 | 누적 규칙 | 충돌 우선순위 |
|------|----------|--------------|
| `personal_memory` | load_memory 1회 set, 이후 read-only | — |
| `workflow_draft` | composer 스텝 결과로 갱신 (last-write) | 최신 스텝 우선 |
| `selected_skill_id` | skills 스텝 산출 → 다음 composer 스텝 입력 | skills 출력 우선 |
| `intent / recipe_key` | intent_node 1회 set | — |
| `round` | resume 시 +1 | — |
| `error` | 복구 시도 후 성공이면 clear | 최신 성공 우선 |

**핵심 데이터 흐름 (복합 레시피)**: `skill_then_compose` = SKILLS 스텝이 `selected_skill_id`를 state에 write → COMPOSER 스텝이 그걸 read해 해당 스킬로 워크플로우 작성. 두 에이전트는 직접 통신하지 않고 state로만 연결.

---

## 6. 복구 경로 (HandoffPayload)

```python
def recovery_target(state, handoff: HandoffPayload) -> RouteTarget | None:
    """순수 함수: 실패 핸드오프 → 복구 라우팅. None이면 포기(ErrorFrame)."""
    if handoff.handoff_type == "recovery_mode":
        # 재시도 카운트 확인 → 한도 내면 같은 target 재시도, 초과면 None
        ...
    if handoff.handoff_type == "result_review":
        # 부분 결과 검토 → composer로 보정 라우팅
        ...
```

| 실패 상황 | handoff_type | 복구 동작 |
|----------|-------------|----------|
| relay HTTP 타임아웃/5xx | recovery_mode | 한도(예: 1회) 내 동일 target 재시도, 초과 시 ErrorFrame |
| sub-agent ErrorFrame 반환 | result_review | state 보존 + general_chat 폴백 안내 or 포기 |
| relay frame 상한 초과 (E_RELAY_LIMIT) | recovery_mode | 즉시 포기 (무한 루프 방지) |

재시도 카운트는 `_State`에 `retry_count` 추가. 루프 전체 홉 상한(예: 8)도 둬서 무한 루프 방어 (recursion_limit 전례 교훈 — `langgraph-recursion-limit` 메모리).

---

## 7. two-shot HITL 흡수

현 `round==2` 특례 분기(P6)는 루프 구조에서 **resume 스텝**으로 자연 흡수:
- 1차: 루프가 composer 스텝에서 SUSPEND 신호 받으면 plan 커서를 보존한 채 스트림 종료.
- 2차(round==2): 보존된 plan을 복원해 composer 스텝부터 재개. 별도 if 가로채기 불필요.

단 이번 범위에선 **기존 round==2 분기를 유지하되 루프 안으로 이동**하는 최소 변경만. 완전 plan 영속화(GCS)는 후속.

---

## 8. 3-평면 (참고 — 본 설계의 라우팅 대상)

| 평면 | 행위자 | supervisor 관계 |
|------|--------|----------------|
| **Composer** (정혜) | 서브에이전트 (Modal app) | 라우팅 대상. 내부는 LangGraph 19-node 유지 |
| **Skills Builder** (박아름) | 서브에이전트 (Modal app) | 라우팅 대상. SOP 경로는 suspend/resume HITL |
| **Personalization** (햄햄) | 서브에이전트 | **라우팅 대상 아님 — 루프 북엔드** (입구 load_mem / 출구 update_mem) |

Skills **Marketplace**는 에이전트가 아니라 공유 도메인 모듈(3-tier 생명주기·RBAC). supervisor 라우팅과 무관.

personal scope 스킬은 self-service 자동 승인(actor==owner)이라 빌더 한 턴에 PUBLISHED까지 완주 → `skill_then_compose` 복합 레시피가 직후 composer의 SearchSkills(PUBLISHED)에서 즉시 발견됨 (게이트 문제 없음).

---

## 9. 구현 단계 (phase-by-phase)

각 Phase는 unit test + (해당 시) staging smoke 통과 후 다음 진행.

| Phase | 내용 | 산출물 | 테스트 |
|-------|------|--------|--------|
| **P0** | `RouteTarget`/`RoutePlan`/`RECIPES`/`route()`/`recovery_target()` 순수 도메인 추가 | `domain/services/supervisor_router.py`, `domain/value_objects/route_plan.py` | 순수 단위 (mock 불필요) |
| **P1** | `supervisor.py` `_run`을 루프 셸로 개편 (단일 의도는 1-스텝 plan으로 동작 = 동작 동일) | `adapters/supervisor.py` | 기존 supervisor 테스트 그린 유지 (회귀 0) |
| **P2** | 복구 경로 연결 (retry_count + recovery_target + 홉 상한) | 동 | relay 실패 mock 테스트 |
| **P3** | 복합 의도 분류 + `skill_then_compose` 레시피 | `intent_analyzer_service.py` | 분류 단위 + 복합 relay e2e mock |
| **P4** | two-shot round==2를 루프 resume 스텝으로 이동 | 동 | 기존 `test_two_shot_relay_e2e` 그린 유지 |
| **P5** | 죽은 `RouteRequestUseCase` + 테스트 삭제 | 파일 삭제 | import 그래프 확인 (배선 0 재확인) |
| **P6** | orchestrator Modal app 재배포 + staging smoke (chitchat 3s / draft / skill_then_compose) | — | Modal logs duration 확인 |

**P1이 핵심 안전선**: 단일 의도를 1-스텝 plan으로 처리하면 외부 동작이 현행과 동일해야 한다. 회귀 테스트 그린 = 루프 셸이 기존 1-홉을 정확히 재현한다는 증거.

---

## 10. 비범위 (out of scope)

- 완전 동적 LLM 체이닝 (화이트리스트 레시피만)
- RoutePlan GCS 영속화 (round==2는 기존 방식 유지)
- LangGraph 도입 (SSE 패스스루 PR #214 스카 + recursion_limit 전례)
- composer/skills 내부 그래프 변경 (정혜/박아름 영역)
- personalization 메모리 구조 변경 (햄햄 영역, 본 설계는 북엔드 호출만)

---

## 11. ownership / 협의

- 본 설계·구현은 **REQ-004 ai_agent 영역(정혜님 소유)**. 조장(황대원) 주도 + 사후 통지로 진행 (2026-06-03 합의).
- 복합 의도 분류(`intent_analyzer_service.py`)는 정혜님 fast-path 작업과 겹침 — P3 진입 전 동기화 필요.
- skills 레시피 스텝은 박아름 Skills Builder 계약 의존 — `selected_skill_id` 산출 형식 확인 필요.
- PR body에 ownership 사후 통지 섹션 필수 (`cross-owner-module-etiquette` 관례).
