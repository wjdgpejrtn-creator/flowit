from __future__ import annotations

from ..value_objects.skeleton import Skeleton, SlotRole, SlotSpec

# 결정적 스켈레톤 라이브러리 시드 (ADR-0026 §6.6) — `_PATTERNS`(build_ontology.py) 후계.
#
# 이 상수가 SSOT다: ① Neo4j ETL(`scripts/build_ontology.py` project_skeletons)이 이걸
# `:Skeleton`/`:SlotSpec`/`:FILLED_BY`로 투영하고 ② 조립기(SkeletonAssembler)가 동일 상수를
# 소비해 워크플로우를 결정적으로 짠다. 복붙 drift 방지 — 노드 카탈로그 `_PATTERNS`와 같은 구조.
#
# 슬롯 후보(candidates)는 **카탈로그에 실재하는 node_type만** 나열한다(없는 슬롯/노드 시드 금지
# — 환각 유발, §6.1 시드 원칙 ① 계승). 그라운딩은 test_skeleton_library가 카탈로그 대조로 강제.
# default_node_type은 required 슬롯이 발화에서 비었을 때의 폴백(trigger 등). 슬롯 순서가 곧
# 선형 배선 순서이며, GATE는 직전 transform과 back-edge 루프를 이룬다(조립기 책임).

# ── 슬롯 후보 풀 (카탈로그 category 기반, 54종 중) ──────────────────────────────
# 발화에서 추출된 node_type만 실제로 슬롯에 들어가므로, candidates는 "이 슬롯이 허용하는
# 집합"(그래프 FILLED_BY)이다. 조립기는 추출 엔티티가 candidates에 속할 때만 채운다.
_TRIGGERS: tuple[str, ...] = (
    "schedule_trigger",
    "manual_trigger",
    "webhook_trigger",
    "event_trigger",
    "file_watch_trigger",
    "api_poll_trigger",
)
_SOURCES: tuple[str, ...] = (
    "google_sheets_read",
    "google_drive_read",
    "bigquery_query",
    "postgresql_query",
    "mysql_query",
    "http_request",
    "rest_api",
    "graphql",
    "file_read",
)
_AI: tuple[str, ...] = ("anthropic_chat", "gemma_chat")
# scorer = 생성물을 기준에 따라 채점하는 ai 노드. quality_loop에서 generator와 gate(if_condition)
# 사이에 들어가 score(number)를 내고, gate가 그 점수를 gte 비교한다(#438 §6.6 — 점수 내는 노드 부재
# 갭 해소). condition이 아니라 ai 노드이므로 _GATES와 분리.
_SCORERS: tuple[str, ...] = ("llm_judge",)
_SINKS: tuple[str, ...] = (
    "slack_post_message",
    "slack_notify",
    "email_send",
    "gmail_send",
    "google_docs_write",
    "pdf_generate",
    "file_write",
    "webhook",
    "linear_create_issue",
    "google_calendar_create_event",
)
# gate = 탈출 조건 condition 노드. quality_gate_loop의 evaluator(if_condition) 그대로.
_GATES: tuple[str, ...] = ("if_condition", "switch_case")
# router = XOR 분기 condition. splitter/merger = 병렬 분할/합류 condition.
_ROUTERS: tuple[str, ...] = ("if_condition", "switch_case")
_SPLITTERS: tuple[str, ...] = ("loop_list",)
_MERGERS: tuple[str, ...] = ("merge_branch",)
# delay = 백오프 대기(재시도 경로). terminal = 종료(반려 경로).
_DELAYS: tuple[str, ...] = ("delay", "retry")
_TERMINALS: tuple[str, ...] = ("stop_workflow",)
# 재시도 대상(worker)은 통상 외부 호출 — source 풀 + ai를 후보로(실패할 수 있는 연산).
_RETRY_WORKERS: tuple[str, ...] = _SOURCES + _AI


SKELETONS: tuple[Skeleton, ...] = (
    # ── scheduled_pipeline ──────────────────────────────────────────────────
    # van der Aalst Sequence + agentic Prompt-Chaining. "매주 시트 읽어 요약 slack" 류 —
    # 정기 트리거로 시작해 source→transform→sink 선형. e2e 누락 버그(§6.6.4)의 직격 대상.
    Skeleton(
        name="scheduled_pipeline",
        intent_keywords=("매주", "매일", "매월", "매시간", "정기", "주기", "스케줄", "요일"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="schedule_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=False, cardinality="many", candidates=_AI),
            SlotSpec(SlotRole.GATE, required=False, cardinality="one", candidates=_GATES),
            # sink optional — "주간 보고서 작성"처럼 출력 채널 미언급 요청도 trigger→…→transform
            # 종단으로 결정적 조립(간결한 실제 발화 커버리지, 2026-06-09 측정). is_empty 가드가
            # 트리거뿐인 무의미 조립은 막는다. branch/approval은 타깃 필요라 sink 필수 유지.
            SlotSpec(SlotRole.SINK, required=False, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── event_response ──────────────────────────────────────────────────────
    # van der Aalst Deferred Choice(이벤트 수신) + agentic Routing 진입. 웹훅/이벤트로
    # 발동해 가공 후 내보낸다. trigger 기본을 webhook_trigger로.
    Skeleton(
        name="event_response",
        intent_keywords=("웹훅", "webhook", "이벤트", "들어오면", "수신", "발생하면", "올라오면"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="webhook_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=False, cardinality="many", candidates=_AI),
            SlotSpec(SlotRole.GATE, required=False, cardinality="one", candidates=_GATES),
            # sink optional (scheduled_pipeline과 동일 사유 — 간결 발화 커버리지).
            SlotSpec(SlotRole.SINK, required=False, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── quality_loop ────────────────────────────────────────────────────────
    # van der Aalst Structured Loop + agentic Evaluator-Optimizer. quality_gate_loop의
    # 결정적 부활 — soft 힌트가 아니라 코드가 back-edge를 깐다(§6.6.4). generator(ai)→
    # scorer(llm_judge, 점수화)→evaluator(if_condition, gte 비교)가 필수이며 generator↔evaluator가
    # 루프를 이룬다. scorer는 #438 §6.6에서 추가 — gate가 비교할 score를 내는 노드가 카탈로그에
    # 없던 갭을 메운다(점수 없이는 if_condition이 의미 비교 불가). SCC={generator,scorer,evaluator}에
    # condition(evaluator) 포함 → CyclicScheduler 수용(#392).
    Skeleton(
        name="quality_loop",
        intent_keywords=("통과할 때까지", "검증", "품질", "재생성", "만족할 때까지", "기준 충족", "반복 개선"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=True, cardinality="one",
                     default_node_type="anthropic_chat", candidates=_AI),
            SlotSpec(SlotRole.SCORER, required=True, cardinality="one",
                     default_node_type="llm_judge", candidates=_SCORERS),
            SlotSpec(SlotRole.GATE, required=True, cardinality="one",
                     default_node_type="if_condition", candidates=_GATES),
            SlotSpec(SlotRole.SINK, required=False, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── branch_on_classification ────────────────────────────────────────────
    # van der Aalst Exclusive Choice(XOR) + agentic Routing. "긴급하면 슬랙, 아니면 이메일" —
    # classifier(ai)가 분류 신호를 내고 router(if_condition)가 2갈래로 라우팅, 각 갈래가 다른
    # sink로 종결(합류 불요). 핸들=true/false (BranchEvaluator: if_condition.branch selector).
    # MVP=2-way(if_condition). 3갈래↑(switch_case 다중)는 조립기가 LLM으로 bail.
    Skeleton(
        name="branch_on_classification",
        intent_keywords=("분류", "분기", "조건에 따라", "경우에 따라", "라우팅"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=True, cardinality="one",
                     default_node_type="anthropic_chat", candidates=_AI),
            SlotSpec(SlotRole.ROUTER, required=True, cardinality="one",
                     default_node_type="if_condition", candidates=_ROUTERS),
            SlotSpec(SlotRole.SINK, required=True, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── conditional_action (단일 가드) ────────────────────────────────────────
    # van der Aalst Exclusive Choice의 1-action 특수화 — "임계치 넘으면 경보" 류. 분류
    # (branch_on_classification, 2-way)도 승인(approval_gate, HITL)도 아닌 **단일 가드 조건문**:
    # router(if_condition)가 가드 조건을 평가해 [true]→action sink, [false]→stop_workflow 종료.
    # transform optional — 가드는 분류기 불필요(if_condition이 입력 직접 평가, 자유조립이
    # "webhook→if_condition→email"로 푼 모양과 정합). false→terminal 자동 부착으로 router
    # outgoing=2 → motif(branch_on_classification: router outgoing≥2 + 무순환) 통과. approval과
    # 동형 구조이나 발동 어휘(임계/비교 가드 vs 검토/승인)와 transform 필수성(approval=proposer
    # 필수)이 다르다. 측정(skeleton-regressor-fix): branch_threshold_alert가 폴백으로 if_condition
    # 소실(qa10→4)되던 회귀의 직격 대상.
    Skeleton(
        name="conditional_action",
        # 선택은 shape(has_guard) 라우팅 전담(control 슬롯이라 _select linear_family 제외) — 아래
        # 키워드는 :Skeleton 투영/문서용 대표 가드 토큰(추출기 _GUARD_KEYWORDS와 동기 관리).
        intent_keywords=("넘으면", "초과하면", "이상이면", "미만이면", "도달하면", "임계치"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=False, cardinality="one", candidates=_AI),
            SlotSpec(SlotRole.ROUTER, required=True, cardinality="one",
                     default_node_type="if_condition", candidates=_ROUTERS),
            SlotSpec(SlotRole.TERMINAL, required=True, cardinality="one",
                     default_node_type="stop_workflow", candidates=_TERMINALS),
            SlotSpec(SlotRole.SINK, required=True, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── fan_out_map ─────────────────────────────────────────────────────────
    # van der Aalst Parallel Split + Synchronization + agentic Orchestrator-Workers. "각 항목마다
    # 처리" — splitter(loop_list)가 목록을 펼치고 worker(ai)가 항목별 처리, merger(merge_branch)가
    # 합류 후 sink. loop_list/merge_branch 출력은 list/int라 selector 없음 → 엣지 전부 live(DAG).
    Skeleton(
        name="fan_out_map",
        intent_keywords=("각각", "각 항목", "항목마다", "항목별", "그룹별", "일괄", "전부", "하나하나"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.SPLITTER, required=True, cardinality="one",
                     default_node_type="loop_list", candidates=_SPLITTERS),
            SlotSpec(SlotRole.TRANSFORM, required=True, cardinality="one",
                     default_node_type="anthropic_chat", candidates=_AI),
            SlotSpec(SlotRole.MERGER, required=True, cardinality="one",
                     default_node_type="merge_branch", candidates=_MERGERS),
            SlotSpec(SlotRole.SINK, required=True, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── retry_backoff ───────────────────────────────────────────────────────
    # van der Aalst Structured Loop + delay (resilience). "API 호출 실패하면 재시도" — worker
    # (실패 가능 연산)→gate(if_condition 성공?)→[false]→delay 백오프→worker 재시도 / [true]→sink.
    # SCC={worker,gate,delay}에 condition(gate) 포함 → CyclicScheduler 수용(#392). quality_loop와
    # 동형이나 back-edge에 delay가 끼고 worker가 ai가 아닌 외부호출(source)일 수 있다.
    Skeleton(
        name="retry_backoff",
        intent_keywords=("재시도", "실패하면", "실패 시", "다시 시도", "오류 나면"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=False, cardinality="many", candidates=_AI),
            SlotSpec(SlotRole.GATE, required=True, cardinality="one",
                     default_node_type="if_condition", candidates=_GATES),
            SlotSpec(SlotRole.DELAY, required=True, cardinality="one",
                     default_node_type="delay", candidates=_DELAYS),
            SlotSpec(SlotRole.SINK, required=False, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── approval_gate ───────────────────────────────────────────────────────
    # van der Aalst Deferred Choice + agentic Human-in-the-loop. "초안 검토 후 승인되면 발송,
    # 아니면 중단" — proposer(ai)→router(if_condition 승인?)→[true]→sink 진행 /[false]→terminal
    # (stop_workflow) 반려. 분기의 특수화(한 갈래가 종료)이므로 DAG(루프 아님). validator 통과.
    Skeleton(
        name="approval_gate",
        intent_keywords=("승인", "검토 후", "컨펌", "결재", "허가"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=True, cardinality="one",
                     default_node_type="anthropic_chat", candidates=_AI),
            SlotSpec(SlotRole.ROUTER, required=True, cardinality="one",
                     default_node_type="if_condition", candidates=_ROUTERS),
            SlotSpec(SlotRole.TERMINAL, required=True, cardinality="one",
                     default_node_type="stop_workflow", candidates=_TERMINALS),
            SlotSpec(SlotRole.SINK, required=True, cardinality="many", candidates=_SINKS),
        ),
    ),
)


def find_skeleton(name: str) -> Skeleton | None:
    for s in SKELETONS:
        if s.name == name:
            return s
    return None
