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

# ── 슬롯 후보 풀 (카탈로그 category 기반, 53종 중) ──────────────────────────────
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
            SlotSpec(SlotRole.SINK, required=True, cardinality="many", candidates=_SINKS),
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
            SlotSpec(SlotRole.SINK, required=True, cardinality="many", candidates=_SINKS),
        ),
    ),
    # ── quality_loop ────────────────────────────────────────────────────────
    # van der Aalst Structured Loop + agentic Evaluator-Optimizer. quality_gate_loop의
    # 결정적 부활 — soft 힌트가 아니라 코드가 back-edge를 깐다(§6.6.4). generator(ai)와
    # evaluator(condition)가 필수이며 둘이 루프를 이룬다.
    Skeleton(
        name="quality_loop",
        intent_keywords=("통과할 때까지", "검증", "품질", "재생성", "만족할 때까지", "기준 충족", "반복 개선"),
        slots=(
            SlotSpec(SlotRole.TRIGGER, required=True, cardinality="one",
                     default_node_type="manual_trigger", candidates=_TRIGGERS),
            SlotSpec(SlotRole.SOURCE, required=False, cardinality="many", candidates=_SOURCES),
            SlotSpec(SlotRole.TRANSFORM, required=True, cardinality="one",
                     default_node_type="anthropic_chat", candidates=_AI),
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
)


def find_skeleton(name: str) -> Skeleton | None:
    for s in SKELETONS:
        if s.name == name:
            return s
    return None
