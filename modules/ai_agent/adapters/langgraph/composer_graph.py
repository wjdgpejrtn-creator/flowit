"""LangGraph Orchestrator (Composer) — Workflow Composer 어댑터 레이어.

spec §3.2 Workflow Composer 내부 StateGraph 구현. LangGraph는 adapters/에만 존재.

Fixed DAG 구조:
  compress → security → intent
    → clarify 경로: consultant → slot_fill → END
    → 일반 경로: search_nodes → draft_workflow → validate_workflow
        → (retry_draft → draft_workflow)* → qa_evaluator
        → (retry_draft → draft_workflow)* → promote
        → save_workflow → confirm_result → save_memory → END
"""
from __future__ import annotations

import asyncio
import json
import logging
import operator
import os
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID, uuid4

import httpx
from auth.domain.services.permission_resolver import PermissionResolver
from common_schemas.agent import DraftSpec, IntentResult, MemoryEntry, SlotFillingState
from common_schemas.enums import IntentType, RiskLevel
from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    ChatMessageFrame,
    DraftSpecDeltaFrame,
    ErrorFrame,
    IntentResultFrame,
    PipelineStatusFrame,
    QAMetricFrame,
    RationaleDeltaFrame,
    ResultFrame,
    SessionFrame,
    SkillOption,
    SkillSelectionFrame,
    SlotFillQuestionFrame,
    SSEFrame,
    WorkflowDraftFrame,
)
from common_schemas.workflow import NodeConfig, WorkflowSchema
from common_schemas.workflow_explanation import WorkflowExplanation
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.services.graph_validator import GraphValidator
from pydantic import BaseModel
from skills_marketplace.application.use_cases.search_skills_use_case import SearchSkillsUseCase
from skills_marketplace.domain.ports import SkillDocumentStore

from ...domain.entities.memory_file import MemoryFile, MemoryFileRef
from ...domain.entities.session_ref import SessionRef
from ...domain.ports.composer_state_store import ComposerStateStore
from ...domain.ports.connection_resolver import ConnectionResolver
from ...domain.ports.llm_port import LLMPort
from ...domain.ports.node_registry import NodeRegistry
from ...domain.ports.ontology_retriever import OntologyRetrieverPort
from ...domain.ports.personal_memory_store import PersonalMemoryStore
from ...domain.ports.session_frame_store import SessionFrameStore
from ...domain.ports.workflow_draft_store import WorkflowDraftStore
from ...domain.ports.workflow_repository import WorkflowRepository
from ...domain.services.dataflow_grounding import outputs_of as _outputs_of
from ...domain.services.drafter_service import DrafterService, _slim_schema
from ...domain.services.intent_analyzer_service import IntentAnalyzerService
from ...domain.services.qa_evaluator_service import QAEvaluatorService
from ...domain.services.skeleton_assembler import SkeletonAssembler
from ...domain.services.slot_ensemble import EnsembleSlotResolver
from ...domain.services.slot_filling_service import SlotFillingService
from ...domain.services.slot_voters import LexicalVoter, OntologyVoter, SemanticVoter
from ...domain.services.workflow_diff_service import WorkflowDiffService
from ...domain.services.workflow_edit_planner import WorkflowEditPlanner
from ...domain.services.workflow_edit_service import EditPlan, WorkflowEditService
from ...domain.services.workflow_explanation_service import WorkflowExplanationService
from ...domain.services.workflow_layout_service import WorkflowLayoutService
from ...domain.value_objects.turn_limit import TurnLimit

_logger = logging.getLogger(__name__)

_QA_MAX_RETRY = 3
_MAX_AGENT_ITERATIONS = 15  # 무한 루프 방지
# refine op 편집 — planner 총 실행 횟수 상한(초기 1 + replan). validate 실패/불량 node_type 시
# 1회 재계획 후 실패 처리(사용자 확정 정책 2026-06-10).
_REFINE_PLAN_MAX_ATTEMPTS = 2
# CAN_FOLLOW 확장 cap (ADR-0026 §4.2a) — ADD-all은 후보 풀을 부풀려 작은 LLM(Gemma) 드래프터의
# structured JSON 생성을 잘리게 만든다(평가 하니스 실측: drafter 실패 6→23, qa pass 64%→29%).
# seed를 검색 상위 hit으로 제한 + 추가 후보 상한으로 풀 비대를 억제한다.
_EXPAND_SEED_LIMIT = 5   # 확장 seed = 검색 상위 N hit만(구조/개인 노드 제외)
_EXPAND_ADD_LIMIT = 3    # CAN_FOLLOW로 추가하는 신규 후보 상한

# 범용 LLM 노드 — 요약/생성/분류/판단 등 거의 모든 워크플로우의 핵심 스텝인데, 의미검색은
# 특정 도메인 쿼리("이 URL 요약")에서 이 generic 노드를 top-k 밖으로 밀어내 후보에서 누락시킨다
# → drafter가 쓰려다 `후보 목록에 없는 node_type drop`으로 끊긴 워크플로우 산출(평가 진단 ②,
# anthropic_chat이 카탈로그에 있는데도 드롭). 구조 노드(#378)와 동일하게 관련도 무관 항상-포함한다.
# 카탈로그 ai 노드와 동기화는 test_core_llm_nodes_drift가 가드.
# llm_judge: 콘텐츠를 기준에 따라 채점(score:number)하는 scorer — 품질 루프
# (generator→llm_judge→if_condition gte)의 게이트 노드라 항상-포함해야 composer가 누락 없이 배선한다(#438 §6.6).
_CORE_LLM_NODE_TYPES: tuple[str, ...] = ("anthropic_chat", "gemma_chat", "llm_judge")

# 스킬 검색 관련성 컷 — 코사인 거리(0=동일, 2=정반대) 상한. 이 거리 밖 후보는 제외해
# 무관한 스킬이 옵션/노드 후보에 딸려 나오는 것을 막는다.
# 기본값 0.50: staging 실측(BGE-M3, 한국어 짧은 텍스트) 기준 — 관련 스킬은 0.35~0.49,
# 무관 쿼리는 0.64+에 분포해 0.50이 둘을 가른다(0.30은 거의 동일어도 컷해 과도했음).
# 데이터 축적 후 SKILL_SEARCH_MAX_DISTANCE env로 무재배포 튜닝.
_SKILL_SEARCH_MAX_DISTANCE = float(os.getenv("SKILL_SEARCH_MAX_DISTANCE", "0.50"))

# RAG로 회수한 사용자 패턴 본문을 drafter 프롬프트에 넣을 때 항목당 본문 절단 길이 —
# 프롬프트 비대화 방지. top-k(=RecallPersonalSkillsUseCase 기본 3) × 이 길이가 주입 상한.
_RECALL_PATTERN_MAX_CHARS = 500

class _NextAction(BaseModel):
    """LLM 에이전트가 다음에 실행할 툴을 선택하는 스키마."""

    tool_name: Literal[
        "analyze_intent",
        "ask_clarification",
        "fill_slots",
        "search_nodes",
        "draft_workflow",
        "validate_workflow",
        "evaluate_quality",
        "retry_draft",
        "promote_workflow",
        "save_workflow",
        "execute_workflow",
        "evaluate_output",
        "confirm_result",
        "save_memory",
        "done",
    ]
    reasoning: str

# 실행 결과 폴링 설정
_EXEC_POLL_INTERVAL_SEC = 3
_EXEC_TIMEOUT_SEC = 300

# 실행 엔진 API 경로 상수 — api_server 라우트 변경 시 여기만 수정
_EXEC_START_PATH = "/api/v1/workflows/{workflow_id}/execute"
_EXEC_POLL_PATH = "/api/v1/executions/{execution_id}"


class _State(TypedDict):
    session_id: UUID
    user_id: UUID
    user_role: str  # "User" | "Admin" — PermissionResolver 권한 확인용
    department_id: UUID | None
    messages: list[dict[str, Any]]
    turn_count: int
    personal_memory: list[MemoryEntry]
    personal_patterns: list[str]  # RAG로 회수한 사용자 과거 패턴 본문 — drafter 프롬프트 주입용
    intent: str | None
    intent_analyzed_entities: dict[str, Any]
    draft_spec: DraftSpec | None
    node_candidates: list[NodeConfig]
    # 온톨로지 CAN_FOLLOW 서브그래프 허용 node_type — retriever→drafter 전달(같은 라운드 transient,
    # 앙상블 OntologyVoter 입력). resume 시 부재면 빈 리스트로 graceful degrade.
    ontology_allowed: list[str]
    workflow_draft: WorkflowSchema | None
    # intent_node가 load한 확인 대기 draft — refine 시 drafter가 재사용(이중 GCS load 방지, #369)
    loaded_prior_workflow: WorkflowSchema | None
    qa_attempts: int
    qa_score: float
    pass_flag: bool
    qa_feedback: str
    # validate/QA 실패 후 재시도 교정 피드백 — drafter에 별도 전달(intent 오염·UI 누출 방지, #378)
    retry_feedback: str
    # drafter degrade로 버린 node_type(후보 미존재) — 재시도 retriever가 결정적으로 재검색(리뷰 #2)
    dropped_node_types: list[str]
    collected_frames: Annotated[list[AnySSEFrame], operator.add]
    error: str | None
    # tool-calling agent 제어
    agent_done: bool
    agent_iterations: int
    # handoff 이후 필드
    saved_workflow_id: UUID | None          # handoff_node에서 WorkflowRepository.save() 결과
    # 실행 검증 필드
    execution_id: str | None               # execute_node에서 설정
    execution_result: dict[str, Any] | None  # execute_node에서 실행 결과
    output_quality_score: float             # evaluate_output_node에서 설정
    output_quality_feedback: str            # evaluate_output_node에서 설정
    # skill suggest 필드 (two-shot 경로)
    suggested_skills: list[dict[str, Any]]  # 제안된 스킬 후보 목록
    # fixed DAG 필드
    validation_issues: str | None           # validator 실패 사유 (non-fatal — error 필드와 분리)
    retry_count: int                        # draft/validate/qa 재시도 횟수
    # no-progress 감지 — 재시도 draft가 직전 실패본과 구조 동일하면 재시도가 무의미(결정적 스켈레톤
    # 재조립 / LLM이 없는 노드 invent→drop→동일 불완전 반복). 헛바퀴 차단 + out-of-scope 빠른 실패.
    last_draft_sig: tuple[Any, ...] | None  # 직전 draft 구조 시그니처(node_id 집합 + node_id 엣지)
    draft_repeated: bool                    # 현재 draft == 직전 draft (futile retry → 즉시 종결)
    # two-shot HITL 스킬 선택 필드 (REQ-013)
    round: int                              # 1=옵션 제시 라운드, 2=선택 입력 후 재개 라운드
    selected_skill_id: UUID | None          # 2차 라운드에서 사용자가 선택한 스킬 (LLM 노드 바인딩 대상)
    awaiting_skill_selection: bool          # suggest_skill_select가 옵션 emit + 중단했는지 (라우팅용)
    resume_ok: bool                         # 2차 resume에서 GCS 상태 복원 성공 여부 (라우팅용)
    # 컨펌 게이트 신뢰 매니페스트 (영역 C)
    workflow_explanation: WorkflowExplanation | None
    offered_skill_ids: list[str]            # 1차에 제시한 옵션 skill_id 집합 (2차 bind 멤버십 검증 — IDOR 차단)
    # GraphRAG — ADR-0026 Phase 2a (모티프 그라운딩). expand_candidates(서브그래프) 소비는
    # CAN_FOLLOW 호환 필터(박아름 §4.2) 머지 후 ADD 방식으로 배선 예정 — 그 전까지 호출 보류.
    pattern_templates: list[Any] | None     # list[PatternTemplate] — 모티프 그라운딩 (ADR-0026 Phase 2a)
    # refine 전용 서브그래프 (op 기반 편집) — fresh QA 게이트 미경유로 부정 발화 오작동 차단
    edit_plan: EditPlan | None              # planner가 만든 편집 연산 리스트
    refine_plan_attempts: int               # planner 총 실행 횟수 (validate 실패/불량 type 시 1회 replan)
    edit_fallback: bool                     # op 적용 실패 → drafter ref-edit 폴백을 탔는지 (관측용)
    refine_route: str | None                # refine_plan 다음 분기 신호: "apply" | "replan"


class LangGraphOrchestrator:
    """Workflow Composer — fixed DAG (spec §3.2).

    compress → security → intent → search_nodes → draft → validate → qa → promote → save → confirm → memory → END.
    services/agents/agent-composer/main.py composition root에서 인스턴스화.
    """

    def __init__(
        self,
        intent_analyzer: IntentAnalyzerService,
        drafter: DrafterService,
        qa_evaluator: QAEvaluatorService,
        slot_filler: SlotFillingService,
        node_registry: NodeRegistry,
        workflow_repo: WorkflowRepository,
        graph_validator: GraphValidator,
        permission_resolver: PermissionResolver | None = None,
        embedder: EmbedderPort | None = None,
        skill_search: SearchSkillsUseCase | None = None,
        session_frame_store: SessionFrameStore | None = None,
        llm: LLMPort | None = None,
        workflow_draft_store: WorkflowDraftStore | None = None,
        execution_engine_url: str | None = None,
        personal_memory_store: PersonalMemoryStore | None = None,
        composer_state_store: ComposerStateStore | None = None,
        workflow_explanation_svc: WorkflowExplanationService | None = None,
        connection_resolver: ConnectionResolver | None = None,
        ontology_retriever: OntologyRetrieverPort | None = None,
        skill_doc_store: SkillDocumentStore | None = None,
        skeleton_assembler: SkeletonAssembler | None = None,
        slot_resolver: EnsembleSlotResolver | None = None,
        workflow_edit_planner: WorkflowEditPlanner | None = None,
        workflow_edit_service: WorkflowEditService | None = None,
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._drafter = drafter
        # refine 전용 op 기반 편집 (PR-2). applier는 순수라 미주입 시 기본 생성. planner는 llm
        # 있으면 기본 생성·없으면 None → _refine_plan_node가 drafter ref-edit 폴백으로 graceful degrade.
        self._edit_service = workflow_edit_service or WorkflowEditService()
        self._edit_planner = workflow_edit_planner or (WorkflowEditPlanner(llm) if llm else None)
        # ADR-0026 §6.6 결정적 스켈레톤 — 순수(무의존)라 미주입 시 기본 생성. assemble None이면
        # 일반 LLM draft로 폴백하므로 항상 안전(소비처 _drafter_node).
        self._skeleton_assembler = skeleton_assembler or SkeletonAssembler()
        # ADR-0026 §6.6 Phase 2 앙상블 슬롯 채움 — 미주입 시 싼 voter 3종(lexical+semantic+ontology)
        # 으로 기본 생성. LLM voter(SlotMapperPort)는 composition root에서 주입(미주입=graceful
        # degrade). resolve 실패/픽 없음이면 assemble이 lexical/grounding으로 폴백하므로 항상 안전.
        self._slot_resolver = slot_resolver or EnsembleSlotResolver(
            [LexicalVoter(), SemanticVoter(), OntologyVoter()]
        )
        self._qa_evaluator = qa_evaluator
        self._slot_filler = slot_filler
        self._node_registry = node_registry
        self._workflow_repo = workflow_repo
        self._graph_validator = graph_validator
        self._permission_resolver = permission_resolver
        self._embedder = embedder
        self._skill_search = skill_search
        self._session_frame_store = session_frame_store
        self._llm = llm
        self._workflow_draft_store = workflow_draft_store
        self._execution_engine_url = execution_engine_url or os.getenv("EXECUTION_ENGINE_URL", "")
        self._personal_memory_store = personal_memory_store
        self._composer_state_store = composer_state_store
        self._workflow_explanation_svc = workflow_explanation_svc or WorkflowExplanationService()
        self._connection_resolver = connection_resolver
        self._ontology_retriever = ontology_retriever
        self._skill_doc_store = skill_doc_store
        self._layout = WorkflowLayoutService()
        self._graph = self._build()

    # ------------------------------------------------------------------ public

    async def stream(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        personal_memory: list[MemoryEntry] | None = None,
        user_role: str = "User",
        department_id: UUID | None = None,
        round: int = 1,
        selected_skill_id: UUID | str | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        # selected_skill_id는 relay(JSON)를 거치며 str로 도착할 수 있어 UUID로 강제
        coerced_skill_id: UUID | None = None
        if isinstance(selected_skill_id, UUID):
            coerced_skill_id = selected_skill_id
        elif isinstance(selected_skill_id, str) and selected_skill_id:
            try:
                coerced_skill_id = UUID(selected_skill_id)
            except ValueError:
                coerced_skill_id = None
        return self._run(
            user_id, session_id, message, personal_memory or [], user_role,
            department_id, round, coerced_skill_id,
        )

    async def _run(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        personal_memory: list[MemoryEntry],
        user_role: str,
        department_id: UUID | None,
        round: int = 1,
        selected_skill_id: UUID | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        session_frame = SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())
        yield session_frame
        user_chat_frame = ChatMessageFrame(role="user", content=message)
        yield user_chat_frame
        all_frames: list[AnySSEFrame] = [session_frame, user_chat_frame]

        initial: _State = {
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "department_id": department_id,
            "messages": [{"role": "user", "content": message}],
            "turn_count": 1,
            "personal_memory": personal_memory,
            "personal_patterns": [],
            "intent": None,
            "intent_analyzed_entities": {},
            "draft_spec": None,
            "node_candidates": [],
            "ontology_allowed": [],
            "workflow_draft": None,
            "loaded_prior_workflow": None,
            "qa_attempts": 0,
            "qa_score": 0.0,
            "pass_flag": False,
            "qa_feedback": "",
            "retry_feedback": "",
            "dropped_node_types": [],
            "collected_frames": [],
            "error": None,
            "agent_done": False,
            "agent_iterations": 0,
            "suggested_skills": [],
            "saved_workflow_id": None,
            "execution_id": None,
            "execution_result": None,
            "output_quality_score": 0.0,
            "output_quality_feedback": "",
            "validation_issues": None,
            "retry_count": 0,
            "last_draft_sig": None,
            "draft_repeated": False,
            "round": round,
            "selected_skill_id": selected_skill_id,
            "awaiting_skill_selection": False,
            "resume_ok": False,
            "offered_skill_ids": [],
            "workflow_explanation": None,
            "edit_plan": None,
            "refine_plan_attempts": 0,
            "edit_fallback": False,
            "refine_route": None,
        }

        try:
            async for event in self._graph.astream(initial, {"recursion_limit": 40}, stream_mode="updates"):
                for node_name, updates in event.items():
                    node_frame = AgentNodeFrame(agent_node_name=node_name)
                    yield node_frame
                    all_frames.append(node_frame)
                    if not isinstance(updates, dict):
                        continue
                    for frame in updates.get("collected_frames", []):
                        yield frame
                        all_frames.append(frame)
                    if updates.get("error"):
                        error_frame = ErrorFrame(code="E_COMPOSER", message=updates["error"])
                        yield error_frame
                        all_frames.append(error_frame)
                        await self._try_save_session(session_id, user_id, message, all_frames)
                        return
        except GraphRecursionError:
            error_frame = ErrorFrame(
                code="E_RECURSION",
                message="워크플로우 생성 최대 단계 초과",
            )
            yield error_frame
            all_frames.append(error_frame)

        await self._try_save_session(session_id, user_id, message, all_frames)

    async def _try_save_session(
        self,
        session_id: UUID,
        user_id: UUID,
        message: str,
        frames: list[AnySSEFrame],
    ) -> None:
        if self._session_frame_store is None:
            return
        workflow_id: UUID | None = None
        for frame in frames:
            if isinstance(frame, ResultFrame):
                wid_str = frame.payload.get("workflow_id")
                if wid_str:
                    try:
                        workflow_id = UUID(wid_str)
                    except Exception:
                        pass
                break
        ref = SessionRef(
            session_id=session_id,
            user_id=user_id,
            workflow_id=workflow_id,
            created_at=datetime.now(UTC),
            message_preview=message[:100],
        )
        try:
            await self._session_frame_store.save_session(ref, frames)
        except Exception as exc:
            _logger.warning("session frame 저장 실패 (non-fatal): %s", exc)

    # ------------------------------------------------------------------ agent loop

    def _build_agent_prompt(self, state: _State) -> str:
        # NOTE: 이 tool-calling 루프(_agent_node)는 현재 _build()의 라이브 DAG에 노드로
        # 미배선이다(고정 DAG 사용). 개인화의 실제 주입점은 drafter(_drafter_node →
        # DrafterService.draft(personal_patterns=...))다. 이 루프가 향후 다시 배선될 때
        # 동일 버그(개인 패턴 미반영)가 재발하지 않도록 여기서도 함께 주입한다.
        intent = state.get("intent") or "아직 분석 안 됨"
        has_draft = state.get("workflow_draft") is not None
        qa_score = state.get("qa_score", 0.0)
        qa_attempts = state.get("qa_attempts", 0)
        pass_flag = state.get("pass_flag", False)
        saved = state.get("saved_workflow_id") is not None
        executed = state.get("execution_id") is not None
        messages_preview = "\n".join(
            f"{m['role']}: {m.get('content', '')[:200]}"
            for m in (state.get("messages") or [])[-3:]
        )
        patterns = state.get("personal_patterns") or []
        patterns_section = (
            "사용자 과거 패턴 (관련 있을 때만 반영):\n"
            + "\n".join(f"- {p}" for p in patterns)
            + "\n\n"
            if patterns
            else ""
        )
        return (
            "워크플로우 자동화 AI 에이전트입니다.\n\n"
            f"대화:\n{messages_preview}\n\n"
            f"{patterns_section}"
            f"현재 상태:\n"
            f"- 의도: {intent}\n"
            f"- 워크플로우 초안: {'있음' if has_draft else '없음'}\n"
            f"- QA: 점수={qa_score}, 시도={qa_attempts}회, 통과={pass_flag}\n"
            f"- DB 저장: {saved}, 실행 완료: {executed}\n"
            "사용 가능한 툴:\n"
            "- analyze_intent: 사용자 의도 분석\n"
            "- ask_clarification: 추가 정보 요청 (슬롯 미완성)\n"
            "- fill_slots: 슬롯 채우기\n"
            "- search_nodes: 노드 카탈로그 검색\n"
            "- draft_workflow: 워크플로우 초안 생성\n"
            "- validate_workflow: 워크플로우 구조 검증\n"
            "- evaluate_quality: 워크플로우 품질 평가\n"
            "- retry_draft: QA 실패 시 재초안\n"
            "- promote_workflow: 워크플로우 확정 (is_draft=False)\n"
            "- save_workflow: DB에 저장\n"
            "- execute_workflow: 실행 엔진 호출 (사용자가 메시지에서 '실행'을 명시적으로 요청한 경우에만)\n"
            "- evaluate_output: 실행 결과 품질 평가\n"
            "- confirm_result: 사용자에게 결과 전달\n"
            "- save_memory: 대화 패턴 저장\n"
            "- done: 모든 작업 완료\n\n"
            "다음에 실행할 툴 하나를 선택하고 이유를 설명하세요.\n"
            '{"tool_name": "<툴이름>", "reasoning": "<이유>"}'
        )

    async def _agent_node(self, state: _State) -> dict:
        if self._llm is None:
            return {"error": "LLM 미주입 — tool-calling 불가", "agent_done": True}

        iterations = state.get("agent_iterations", 0) + 1
        if iterations > _MAX_AGENT_ITERATIONS:
            return {
                "agent_done": True,
                "error": f"에이전트 최대 반복 횟수({_MAX_AGENT_ITERATIONS}) 초과",
                "agent_iterations": iterations,
            }

        t0 = time.monotonic()
        try:
            action = await self._llm.generate_structured(self._build_agent_prompt(state), _NextAction)
        except Exception as exc:
            return {"error": f"툴 선택 실패: {exc}", "agent_done": True, "agent_iterations": iterations}

        _logger.info("agent 툴 선택: %s — %s", action.tool_name, action.reasoning)

        tool_map: dict[str, Any] = {
            "analyze_intent":   self._intent_node,
            "ask_clarification": self._consultant_node,
            "fill_slots":       self._slot_fill_node,
            "search_nodes":         self._retriever_node,
            "draft_workflow":       self._drafter_node,
            "validate_workflow": self._validator_node,
            "evaluate_quality": self._qa_evaluator_node,
            "retry_draft":      self._qa_retry_node,
            "promote_workflow": self._promote_node,
            "save_workflow":    self._handoff_node,
            "execute_workflow": self._execute_node,
            "evaluate_output":  self._evaluate_output_node,
            "confirm_result":   self._user_confirm_node,
            "save_memory":      self._memory_save_node,
        }

        if action.tool_name == "done":
            elapsed = int((time.monotonic() - t0) * 1000)
            return {
                "agent_done": True,
                "agent_iterations": iterations,
                "collected_frames": [
                    PipelineStatusFrame(service_name="agent", status="completed", elapsed_ms=elapsed)
                ],
            }

        tool_fn = tool_map.get(action.tool_name)
        if tool_fn is None:
            return {"error": f"알 수 없는 툴: {action.tool_name}", "agent_done": True, "agent_iterations": iterations}

        try:
            updates = await tool_fn(state)
        except Exception as exc:
            return {"error": f"툴 실행 실패({action.tool_name}): {exc}", "agent_done": True, "agent_iterations": iterations}

        tool_frames = updates.get("collected_frames", [])

        # 사용자에게 보이는 AI 응답을 ChatMessageFrame으로 기록
        assistant_chat: ChatMessageFrame | None = None
        if action.tool_name == "ask_clarification":
            for f in tool_frames:
                if isinstance(f, SlotFillQuestionFrame):
                    assistant_chat = ChatMessageFrame(role="assistant", content=f.question)
                    break
        elif action.tool_name == "confirm_result":
            for f in tool_frames:
                if isinstance(f, ResultFrame):
                    summary = json.dumps(f.payload, ensure_ascii=False)[:300]
                    assistant_chat = ChatMessageFrame(role="assistant", content=summary)
                    break

        pre_frames: list[AnySSEFrame] = [AgentNodeFrame(agent_node_name=action.tool_name)]
        if assistant_chat:
            pre_frames.append(assistant_chat)

        return {
            **updates,
            "agent_iterations": iterations,
            "collected_frames": pre_frames + tool_frames,
        }

    @staticmethod
    def _route_agent(state: _State) -> str:
        if state.get("agent_done") or state.get("error"):
            return "end"
        return "continue"

    @staticmethod
    def _route_after_security(state: _State) -> str:
        return "end" if state.get("error") else "intent"

    @staticmethod
    def _route_after_intent(state: _State) -> str:
        intent = state.get("intent")
        if intent == "clarify":
            return "consultant"
        if intent in {"draft", "refine", None}:
            return "search_nodes"
        # propose 포함 예상 외 intent → supervisor가 처리, composer는 no-op END
        return "end"

    @staticmethod
    def _route_after_validate(state: _State) -> str:
        # refine(op 편집)은 QA 커버리지 게이트를 타지 않는다 — 그 게이트가 편집 발화의 부정/제거
        # 노드명을 '필수'로 오인해 무한 재시도를 일으켰다(E_QA_EXHAUSTED 근본). 구조 검증만 거쳐
        # 바로 promote. 검증 실패 시 1회 재계획(refine_plan) 후 실패.
        if state.get("intent") == "refine":
            if state.get("pass_flag"):
                return "promote"
            if state.get("refine_plan_attempts", 0) < _REFINE_PLAN_MAX_ATTEMPTS:
                return "refine_plan"
            return "validation_failed"
        if state.get("pass_flag"):
            return "qa_evaluator"
        # no-progress: 재시도 draft가 직전과 동일하면 재시도 무의미 → 즉시 종결(헛바퀴 차단).
        if state.get("draft_repeated"):
            return "validation_failed"
        if state.get("retry_count", 0) < _QA_MAX_RETRY:
            return "retry_draft"
        return "validation_failed"

    @staticmethod
    def _route_after_refine_plan(state: _State) -> str:
        if state.get("error"):
            return "end"
        return state.get("refine_route") or "apply"

    @staticmethod
    def _route_after_qa(state: _State) -> str:
        if state.get("pass_flag"):
            return "promote"
        # no-progress: 재시도 draft가 직전과 동일하면 같은 QA 실패 반복 → 즉시 종결. 결정적 스켈레톤
        # 재조립이나 LLM의 없는-노드 invent→drop→동일 불완전 케이스(out-of-scope)를 빠르게 실패.
        if state.get("draft_repeated"):
            return "qa_failed"
        if state.get("qa_attempts", 0) < _QA_MAX_RETRY:
            return "retry_draft"
        return "qa_failed"

    # ---- two-shot HITL 라우터 (REQ-013) ----

    @staticmethod
    def _route_entry(state: _State) -> str:
        """진입 분기 — 2차(선택 입력) 라운드는 GCS 복원(resume)부터, 1차는 기존 전처리(compress)부터."""
        return "resume" if state.get("round", 1) == 2 else "compress"

    @staticmethod
    def _route_after_resume(state: _State) -> str:
        """복원 성공 시 draft로, 실패(세션 만료) 시 종료."""
        return "draft" if state.get("resume_ok") else "end"

    @staticmethod
    def _route_after_suggest(state: _State) -> str:
        """refine → op 기반 편집 서브그래프(refine_plan), 옵션 emit+중단(two-shot) → END,
        그 외 → 한 라운드 내 draft(fresh, one-shot 폴백). planner 미주입 시에도 refine_plan이
        drafter ref-edit 폴백으로 graceful degrade하므로 여기선 intent만 본다."""
        if state.get("awaiting_skill_selection"):
            return "wait"
        if state.get("intent") == "refine":
            return "refine"
        return "draft"

    # ------------------------------------------------------------------ preprocessing nodes

    # 1. compress_node — turn_count >= 25 시 메시지 압축
    async def _compress_node(self, state: _State) -> dict:
        TurnLimit().validate(state["turn_count"])
        compressed = state["messages"][-1:]
        return {"messages": compressed, "turn_count": 1}

    # 위험 패턴 — 시스템 명령 / SQL 조작 / 프롬프트 탈취 시도
    _DANGEROUS_PATTERNS: list[str] = [
        "drop table", "delete from", "truncate table",  # SQL 파괴
        "rm -rf", "sudo ", "exec(", "eval(",             # 시스템 명령
        "ignore previous instructions", "ignore all instructions",  # 프롬프트 탈취
        "you are now", "act as if",                      # 역할 변경 시도
    ]

    # 2. security_node — 입력 검증 + 위험 패턴 감지 + 권한 확인
    async def _security_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        message = state["messages"][-1].get("content", "") if state["messages"] else ""

        if not message.strip():
            return {"error": "빈 메시지는 처리할 수 없습니다."}
        if len(message) > 10_000:
            return {"error": f"메시지가 너무 깁니다 ({len(message)}자). 최대 10,000자."}

        # 위험 패턴 감지
        lower = message.lower()
        for pattern in self._DANGEROUS_PATTERNS:
            if pattern in lower:
                return {"error": f"허용되지 않는 요청입니다. (감지된 패턴: '{pattern}')"}

        # 권한 확인 — PermissionResolver 주입된 경우
        # NOTE: 이 단계는 coarse pre-screen — 실제 노드가 식별되기 전이라
        # 텍스트 키워드 휴리스틱만 사용한다. 정밀한 risk_ceiling 강제는
        # 실 노드가 확정되는 validator 단계에서 처리한다.
        if self._permission_resolver is not None and state.get("department_id"):
            perm = self._permission_resolver.resolve(
                user_id=state["user_id"],
                role=state["user_role"],  # type: ignore[arg-type]
                department_id=state["department_id"],
                session_id=state["session_id"],
            )
            if perm.risk_ceiling != RiskLevel.RESTRICTED and any(
                kw in lower for kw in ("restricted", "admin only", "관리자만", "시스템 접근")
            ):
                return {"error": "해당 요청은 관리자 권한이 필요합니다."}

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "collected_frames": [
                PipelineStatusFrame(service_name="security", status="completed", elapsed_ms=elapsed)
            ]
        }

    # 3. intent_node
    async def _intent_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        # 상태 인지 분류(#369): 이 세션에 사용자 확인 대기 draft가 있으면 그 사실을 분류기에
        # 주입해 "url 바꿔줘"/"채널 #general로 해줘" 같은 수정 발화가 새 워크플로우 생성(draft)으로
        # 오분류되는 것을 막는다. draft load는 여기 1회로 일원화(state에 stash → drafter 재사용,
        # refine 경로 중복 load 방지). create(draft 부재) 요청도 has_pending_draft 판정 위해 1회
        # GET(None) — create 경로는 0→1이나 100~300s 파이프라인 대비 무시 가능.
        prior_workflow: WorkflowSchema | None = None
        if self._workflow_draft_store is not None:
            try:
                prior_workflow = await self._workflow_draft_store.load_draft(state["session_id"])
            except Exception as exc:
                _logger.warning("intent: prior draft 조회 실패 (무시): %s", exc)
                prior_workflow = None
        try:
            result = await self._intent_analyzer.analyze(
                state["messages"], context={"has_pending_draft": prior_workflow is not None}
            )
        except Exception as exc:
            return {"intent": "clarify", "error": f"intent 분석 실패: {exc}"}
        # composer 진입 = supervisor가 draft/refine/clarify로 분류한 상황
        # result=None(미분류)이면 draft로 기본 처리
        if result is None:
            result = IntentResult(intent=IntentType.DRAFT, confidence=0.5, analyzed_entities={})
        elapsed = int((time.monotonic() - t0) * 1000)
        draft_spec = DraftSpec(
            natural_language_intent=state["messages"][-1].get("content", ""),
            unresolved_nodes=[],
            discovered_entities=result.analyzed_entities,
            slot_filling_state=SlotFillingState(
                asked=[], pending=list(result.analyzed_entities.keys()), filled={}
            ),
            consultant_turn_count=0,
        )
        return {
            "intent": result.intent,
            "intent_analyzed_entities": result.analyzed_entities,
            "draft_spec": draft_spec,
            "loaded_prior_workflow": prior_workflow,
            "collected_frames": [
                IntentResultFrame(intent=result.intent, entities=result.analyzed_entities),
                PipelineStatusFrame(service_name="intent", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 4. consultant_node — clarify 인텐트: slot filling 준비
    async def _consultant_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        spec = state.get("draft_spec")
        if spec is None:
            return {}
        entities = spec.discovered_entities or {}
        slot_state = spec.slot_filling_state
        newly_filled = {k: v for k, v in entities.items() if k in slot_state.pending}
        updated_slot = SlotFillingState(
            asked=slot_state.asked,
            pending=[s for s in slot_state.pending if s not in newly_filled],
            filled={**slot_state.filled, **newly_filled},
        )
        updated_spec = spec.model_copy(update={
            "slot_filling_state": updated_slot,
            "consultant_turn_count": spec.consultant_turn_count + 1,
        })
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "draft_spec": updated_spec,
            "collected_frames": [
                PipelineStatusFrame(service_name="consultant", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 5. slot_fill_node — 슬롯 채움 질문 생성
    async def _slot_fill_node(self, state: _State) -> dict:
        spec = state["draft_spec"]
        if spec is None:
            return {}
        question = self._slot_filler.next_question(spec.slot_filling_state, spec)
        if question:
            return {
                "collected_frames": [
                    SlotFillQuestionFrame(question=question, field_name="unknown")
                ]
            }
        return {}

    async def _recall_personal_patterns(self, user_id: UUID, query: str) -> list[str]:
        """RAG(BGE-M3 코사인 유사도)로 이번 요청과 관련된 사용자 과거 패턴 본문을 회수.

        ``RecallPersonalSkillsUseCase`` 독스트링의 설계 의도 — "Workflow Composer가 프롬프트
        작성 전 호출해 관련 사용자 패턴을 주입" — 를 라이브 그래프에 배선한다. store/embedder
        미주입 또는 회수 실패 시 빈 리스트를 반환해 개인화를 조용히 건너뛴다(non-fatal).
        load_memory 전체 덤프와 달리 쿼리 관련 top-k만 회수해 프롬프트 오염을 막는다.
        """
        if self._personal_memory_store is None or self._embedder is None:
            return []
        try:
            from ...application.agents.personalization.recall_personal_skills_use_case import (
                RecallPersonalSkillsUseCase,
            )

            recall = RecallPersonalSkillsUseCase(self._personal_memory_store, self._embedder)
            files = await recall.execute(user_id, query)
        except Exception as exc:
            _logger.warning("개인 패턴 회수 실패 (non-fatal, 개인화 미적용): %s", exc)
            return []
        patterns: list[str] = []
        for f in files:
            body = (f.body or "").strip()
            if not body:
                continue
            label = (f.description or f.name or "").strip()
            snippet = body[:_RECALL_PATTERN_MAX_CHARS]
            patterns.append(f"[{label}] {snippet}" if label else snippet)
        return patterns

    async def _fetch_structural_candidates(self) -> list[NodeConfig]:
        """구조 노드(트리거/제어흐름) 후보를 회수 — 실패·미구현 시 빈 리스트(비치명적).

        ``NodeRegistry.list_structural``이 없거나(구버전 mock) 조회가 실패해도 워크플로우
        생성을 막지 않는다. ``list()``로 강제 평가해 mock이 비-iterable을 돌려줘도 안전하게
        빈 리스트로 degrade한다.
        """
        lister = getattr(self._node_registry, "list_structural", None)
        if lister is None:
            return []
        try:
            result = await lister()
            return list(result) if result else []
        except Exception as exc:
            _logger.warning("구조 노드 후보 합산 실패 (non-fatal): %s", exc)
            return []

    async def _fetch_core_llm_candidates(self) -> list[NodeConfig]:
        """범용 LLM 노드(anthropic_chat/gemma_chat)를 관련도 무관 항상-포함 회수.

        의미검색이 도메인 쿼리에서 generic LLM 노드를 top-k 밖으로 밀어내 끊긴 워크플로우를
        만드는 문제(평가 진단 ②) 대응. ``list_by_node_types``(EXECUTABLE 가드 포함)를 재사용 —
        없거나(구버전 mock) 실패해도 빈 리스트로 비치명적 degrade(검색 후보만으로 진행).
        """
        grounder = getattr(self._node_registry, "list_by_node_types", None)
        if grounder is None:
            return []
        try:
            result = await grounder(list(_CORE_LLM_NODE_TYPES))
            return list(result) if result else []
        except Exception as exc:
            _logger.warning("범용 LLM 노드 후보 합산 실패 (non-fatal): %s", exc)
            return []

    @staticmethod
    def _dedup_union(base: list[NodeConfig], extra: list[NodeConfig]) -> list[NodeConfig]:
        """node_id 기준 dedup 합집합 — base를 우선 보존하고 새 항목만 뒤에 덧붙인다."""
        seen = {c.node_id for c in base}
        return base + [e for e in extra if e.node_id not in seen]

    async def _expand_can_follow(
        self, seed_candidates: list[NodeConfig], existing_pool: list[NodeConfig]
    ) -> tuple[list[NodeConfig], list[str]]:
        """검색 상위 hit의 CAN_FOLLOW 후행 노드를 회수해 NodeConfig로 ADD 보강 (§4.2a).

        **풀 비대 가드(평가 하니스 실측 회귀 대응)**: seed는 검색 상위 ``_EXPAND_SEED_LIMIT``
        hit으로 제한(구조/개인 노드는 제외 — 이들의 후행은 노이즈)하고, 추가 후보는
        ``_EXPAND_ADD_LIMIT``개로 cap한다. ADD-all은 후보 풀을 부풀려 작은 LLM 드래프터의
        structured JSON을 잘리게 해 품질을 떨어뜨렸다.

        반환: ``(보강 후보, 서브그래프 허용 node_type)``. 첫 값은 호출부 ``_dedup_union``으로
        합쳐지고, 둘째 값은 앙상블 OntologyVoter 입력으로 state에 실린다(seed+1-hop 허용집합).
        온톨로지 미주입/실패/미투영은 전부 ``([], [])``로 비치명적 degrade(검색 후보만으로 진행).
        """
        if self._ontology_retriever is None or not seed_candidates:
            return [], []
        grounder = getattr(self._node_registry, "list_by_node_types", None)
        if grounder is None:  # 구버전 NodeRegistry — 그라운딩 불가
            return [], []
        seeds = [c.node_type for c in seed_candidates[:_EXPAND_SEED_LIMIT]]
        existing = {c.node_type for c in existing_pool}
        try:
            subgraph = await self._ontology_retriever.expand_candidates(seeds)
            allowed = sorted(subgraph.allowed_node_types())
            # seed 관련도 순서를 보존(상위 hit의 후행 우선)하며 신규 후행만 cap까지 모은다.
            picked: list[str] = []
            seen: set[str] = set()
            for seed in seeds:
                for nt in subgraph.adjacency.get(seed, ()):
                    if nt in existing or nt in seen:
                        continue
                    seen.add(nt)
                    picked.append(nt)
                    if len(picked) >= _EXPAND_ADD_LIMIT:
                        break
                if len(picked) >= _EXPAND_ADD_LIMIT:
                    break
            if not picked:
                return [], allowed
            grounded = await grounder(picked)
            return (list(grounded) if grounded else []), allowed
        except Exception as exc:
            _logger.warning("CAN_FOLLOW 확장 실패 (후보 보강 생략): %s", exc)
            return [], []

    # 6. retriever_node — 노드 후보 검색 + 구조 노드 합산 + 개인 패턴 RAG 회수
    async def _retriever_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        spec = state["draft_spec"]
        query = spec.natural_language_intent if spec else state["messages"][-1].get("content", "")
        try:
            raw_candidates = await self._node_registry.search(query)
        except Exception as exc:
            return {"error": f"retriever 실패: {exc}"}

        # GraphRAG — ADR-0026 Phase 2a: match_patterns로 :Pattern 모티프를 회수해 drafter
        # 프롬프트에 주입한다(per-request driver). OntologyRetrieverPort 미주입/실패 시 기존
        # pgvector 단독 경로로 폴백(non-fatal). ETL 시드 전까지는 빈 리스트가 정상.
        pattern_templates: list[Any] | None = None
        if self._ontology_retriever is not None:
            try:
                pattern_templates = await self._ontology_retriever.match_patterns(query)
                if pattern_templates:
                    _logger.debug(
                        "GraphRAG 모티프 %d건 매칭: %s",
                        len(pattern_templates), [pt.name for pt in pattern_templates],
                    )
            except Exception as exc:
                _logger.warning("OntologyRetriever match_patterns 실패 (패턴 미적용): %s", exc)
                pattern_templates = None

        # 구조 노드(트리거/제어흐름)는 사용자 문장에 자연어로 녹아(예: "매주 월요일 9시") 의미검색
        # top-k에 안 떠서 drafter가 `후보 목록에 없는 node_type: schedule_trigger`로 하드페일했다
        # (#378 후속 A). 관련성 무관하게 항상 후보에 선제 합산해 첫 초안부터 사용 가능하게 한다.
        # node_id 기준 dedup. 조회 실패는 비치명적 — 검색 후보만으로 진행한다.
        candidates = self._dedup_union(raw_candidates, await self._fetch_structural_candidates())

        # 범용 LLM 노드(anthropic_chat/gemma_chat)도 구조 노드와 동일하게 관련도 무관 항상-포함한다.
        # 의미검색이 generic LLM 노드를 도메인 쿼리 top-k 밖으로 밀어내 drafter가 드롭→끊긴
        # 워크플로우를 만드는 문제(평가 진단 ②) 대응. 이미 있으면 dedup으로 무시된다.
        candidates = self._dedup_union(candidates, await self._fetch_core_llm_candidates())

        # GraphRAG CAN_FOLLOW 확장 (ADR-0026 §4.2a) — 검색 상위 hit의 후행 가능 노드를 온톨로지에서
        # 회수해 **ADD 보강**한다. 의미검색이 놓치는 글루/transform/control 노드(예: csv_parse 뒤
        # csv_build, file_read 뒤 json_extract)를 쓸 수 있게 해 누락을 줄인다. seed는 raw_candidates
        # (검색 hit)만 — 구조/개인 노드의 후행은 노이즈라 제외. cap으로 풀 비대 억제(위 상수).
        # ADD 전용(subtract 금지) — ETL stale 시에도 유효 후보를 지우지 않는다. 비치명적.
        expanded, ontology_allowed = await self._expand_can_follow(raw_candidates, candidates)
        candidates = self._dedup_union(candidates, expanded)

        # 스킬은 더 이상 노드 후보로 합산하지 않는다 (#372 결함 B — 스킬 이중 정체성 해소).
        # 스킬은 "실행 노드"가 아니라 "LLM 노드에 주입되는 지침서"(모델 A)다. 검색·제시는
        # two-shot 경로(`_suggest_skill_select_node`)가 전담하고, 선택된 스킬은 `_drafter_node`가
        # LLM 노드를 보장 → `_bind_skill_node`가 skill_id를 바인딩한다. 여기서 스킬 NodeDefinition을
        # candidates에 넣으면 drafter가 스킬을 빈 껍데기 노드로 배치해(parameter_schema={}) 실행
        # 불가 + 바인딩 대상 LLM 노드 미생성으로 이어진다(#372 재현 증상).

        # 개인 패턴 RAG 회수 — drafter 프롬프트 주입용(retry 루프 밖, 1회만 수행).
        personal_patterns = await self._recall_personal_patterns(state["user_id"], query)

        elapsed = int((time.monotonic() - t0) * 1000)
        node_types = ", ".join(c.node_type for c in candidates[:5])
        more = f" 외 {len(candidates) - 5}개" if len(candidates) > 5 else ""
        frames: list[AnySSEFrame] = [
            RationaleDeltaFrame(delta=f"🔍 노드 검색 완료 — {len(candidates)}개 후보 발견: {node_types}{more}"),
        ]
        if personal_patterns:
            frames.append(
                RationaleDeltaFrame(delta=f"🧠 사용자 과거 패턴 {len(personal_patterns)}건 반영")
            )
        frames.append(
            PipelineStatusFrame(service_name="retriever", status="completed", elapsed_ms=elapsed)
        )
        return {
            "node_candidates": candidates,
            "ontology_allowed": ontology_allowed,
            "personal_patterns": personal_patterns,
            "pattern_templates": pattern_templates,
            "collected_frames": frames,
        }

    # 6.6. suggest_skill_select_node — two-shot 1차: 스킬 옵션 제시 + 상태 영속 후 중단 (REQ-013)
    async def _suggest_skill_select_node(self, state: _State) -> dict:
        """스킬 검색 후 SkillSelectionFrame으로 옵션 제시하고 1차 라운드를 종료한다.

        skill_search/embedder 미주입 또는 후보 0건이면 `awaiting_skill_selection=False`로
        반환해 한 라운드 안에서 draft로 진행(one-shot 폴백, 회귀 보존).
        후보가 있으면 그래프 상태를 GCS에 영속(2차 resume 재료)하고 옵션 frame을 emit한다.
        """
        # refine(기존 워크플로우 편집)은 스킬 제안 대상이 아니다 — two-shot 스킬 선택은 **새 draft
        # 생성** 시에만 의미가 있다(#369 후속). refine을 스킬 선택으로 우회시키면 "url/채널 수정해줘"
        # 같은 편집 발화가 "워크플로우 작성을 시작" + (무관한) 스킬 카드로 끊겨 사용자에겐 새 생성처럼
        # 보이고 편집 흐름이 깨진다. 바로 draft_workflow로 보내 `_drafter_node`가 prior_workflow를
        # 로드해 제자리 편집하게 한다(intent는 이미 _intent_node에서 refine으로 상태 인지 분류됨).
        if state.get("intent") == "refine":
            return {"awaiting_skill_selection": False}
        if self._skill_search is None or self._embedder is None:
            return {"awaiting_skill_selection": False}

        t0 = time.monotonic()
        spec = state.get("draft_spec")
        query = spec.natural_language_intent if spec else state["messages"][-1].get("content", "")
        try:
            query_embedding = await self._embedder.embed(query)
            # 접근 가능 스코프(개인 본인 + 전사) 병합 + 관련성 컷 — 무관 스킬 옵션 노출 차단.
            skill_results = await self._skill_search.execute_accessible(
                query_embedding=query_embedding,
                user_id=state["user_id"],
                limit=5,
                max_distance=_SKILL_SEARCH_MAX_DISTANCE,
            )
        except Exception as exc:
            _logger.warning("suggest_skill_select 검색 실패 (one-shot 폴백): %s", exc)
            return {"awaiting_skill_selection": False}

        options: list[SkillOption] = []
        # owner_user_id는 개인 스킬 엔티티(MarketplacePersonalSkill)에만 존재 — 본인 소유면
        # 프론트에 "⭐ 자주 사용" 배지로 개인화 추천을 강조한다(REQ-013, execute_accessible personal 병합).
        user_id_str = str(state["user_id"])
        for skill in skill_results:
            skill_id = getattr(skill, "skill_id", None)
            if skill_id is None:  # 지침서형/노드형 무관 — skill_id만 있으면 선택지로 노출(필터 제거)
                continue
            owner = getattr(skill, "owner_user_id", None)
            options.append(
                SkillOption(
                    skill_id=skill_id,
                    name=getattr(skill, "name", ""),
                    description=getattr(skill, "description", ""),
                    node_definition_id=getattr(skill, "node_definition_id", None),
                    is_personal=owner is not None and str(owner) == user_id_str,
                )
            )

        if not options:
            return {"awaiting_skill_selection": False}

        # 2차 resume 재료를 GCS에 영속 — store 미주입 시 옵션 제시 자체를 포기하고 one-shot 폴백.
        # 제시한 옵션 skill_id 집합 + user_id를 함께 저장(2차 멤버십·소유권 검증 재료 — IDOR/세션탈취 차단).
        offered_skill_ids = [str(o.skill_id) for o in options]
        if self._composer_state_store is None:
            _logger.warning("composer_state_store 미주입 — two-shot 불가, one-shot 폴백")
            return {"awaiting_skill_selection": False}
        try:
            await self._composer_state_store.save_state(
                state["session_id"], self._serialize_resume_state(state, offered_skill_ids)
            )
        except Exception as exc:
            _logger.warning("composer 상태 영속 실패 (one-shot 폴백): %s", exc)
            return {"awaiting_skill_selection": False}

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "awaiting_skill_selection": True,
            "suggested_skills": [o.model_dump(mode="json") for o in options],
            "collected_frames": [
                SkillSelectionFrame(
                    prompt="요청에 맞는 스킬 지침서를 찾았어요. 워크플로우에 적용할 스킬을 선택해 주세요.",
                    options=options,
                    allow_skip=True,
                ),
                PipelineStatusFrame(service_name="suggest_skill_select", status="completed", elapsed_ms=elapsed),
            ],
        }

    @staticmethod
    def _serialize_resume_state(state: _State, offered_skill_ids: list[str]) -> dict[str, Any]:
        """2차 resume에 필요한 그래프 상태를 직렬화 dict로 추출 (Pydantic은 model_dump).

        user_id(세션 소유권 검증)·offered_skill_ids(옵션 멤버십 검증)를 함께 영속해
        2차 라운드에서 IDOR/세션 탈취를 차단한다.
        """
        spec = state.get("draft_spec")
        return {
            "user_id": str(state["user_id"]),
            "offered_skill_ids": offered_skill_ids,
            "draft_spec": spec.model_dump(mode="json") if spec else None,
            "node_candidates": [c.model_dump(mode="json") for c in state.get("node_candidates") or []],
            "intent": state.get("intent"),
            "intent_analyzed_entities": state.get("intent_analyzed_entities") or {},
        }

    @staticmethod
    def _resume_error(code: str, message: str) -> dict:
        return {"resume_ok": False, "collected_frames": [ErrorFrame(code=code, message=message)]}

    # 6.8. resume_node — two-shot 2차 진입: GCS에서 1차 상태 복원 (REQ-013)
    async def _resume_node(self, state: _State) -> dict:
        """2차 라운드 진입점. 1차에서 영속한 그래프 상태를 복원해 draft부터 이어간다.

        - 미존재(None) → `E_SESSION_EXPIRED`(진짜 만료/오타 session_id).
        - 일시적 저장소 오류(예외) → `E_RESUME_FAILED`(재시도 안내) — 만료와 구분(LOW #3).
        - 영속 user_id ≠ 호출자 → `E_SESSION_EXPIRED`(generic, 세션 탈취 차단 + 존재 누설 방지, MED #1).
        """
        if self._composer_state_store is None:
            return self._resume_error(
                "E_SESSION_EXPIRED", "세션 상태 저장소가 없어 재개할 수 없습니다. 처음부터 다시 시작해 주세요."
            )
        try:
            blob = await self._composer_state_store.load_state(state["session_id"])
        except Exception as exc:
            # 일시적 GCS/인증 오류 — 만료와 구분해 재시도 유도 (LOW #3)
            _logger.warning("composer 상태 복원 일시 오류: %s", exc)
            return self._resume_error(
                "E_RESUME_FAILED", "일시적인 오류로 재개에 실패했어요. 잠시 후 다시 시도해 주세요."
            )
        if not blob:
            return self._resume_error(
                "E_SESSION_EXPIRED", "세션이 만료되었습니다. 워크플로우 요청을 다시 말씀해 주세요."
            )

        # 세션 소유권 검증 — 1차 영속 user_id ≠ 2차 호출자면 거부 (타 세션 resume 가로채기 차단, MED #1)
        persisted_user = blob.get("user_id")
        if persisted_user is not None and persisted_user != str(state["user_id"]):
            _logger.warning("composer resume 소유권 불일치 차단: session=%s", state["session_id"])
            return self._resume_error(
                "E_SESSION_EXPIRED", "세션이 만료되었습니다. 워크플로우 요청을 다시 말씀해 주세요."
            )

        draft_spec = DraftSpec.model_validate(blob["draft_spec"]) if blob.get("draft_spec") else None
        node_candidates = [NodeConfig.model_validate(c) for c in blob.get("node_candidates") or []]
        # 2차 라운드는 search_nodes를 건너뛰므로(resume→draft) 여기서 개인 패턴을 직접 회수해
        # 재초안에도 개인화가 반영되게 한다(1차 회수 결과는 GCS 영속 상태에 없음).
        query = draft_spec.natural_language_intent if draft_spec else state["messages"][-1].get("content", "")
        personal_patterns = await self._recall_personal_patterns(state["user_id"], query)
        return {
            "resume_ok": True,
            "draft_spec": draft_spec,
            "node_candidates": node_candidates,
            "personal_patterns": personal_patterns,
            "intent": blob.get("intent"),
            "intent_analyzed_entities": blob.get("intent_analyzed_entities") or {},
            "offered_skill_ids": blob.get("offered_skill_ids") or [],
            "collected_frames": [
                PipelineStatusFrame(service_name="resume", status="completed", elapsed_ms=0),
            ],
        }

    # 6.9. bind_skill_node — draft 후 LLM 노드에 선택 skill_id 바인딩 (결정론적 후처리, REQ-013)
    async def _bind_skill_node(self, state: _State) -> dict:
        """선택된 skill_id를 draft된 워크플로우의 첫 LLM 노드(category=="ai")에 바인딩.

        drafter 무변경(바인딩=composer 후처리). 선택 없음/LLM 노드 0개면 no-op(경고).
        복수 LLM 노드면 첫 노드(MVP 휴리스틱, 향후 옵션에 target_node 추가).
        """
        sel = state.get("selected_skill_id")
        workflow = state.get("workflow_draft")
        if sel is None or workflow is None:
            return {}

        # 옵션 멤버십 검증 — 1차에 제시된 옵션(이미 호출자 스코프로 제한됨)에 없는 skill_id는 거부.
        # /slot이 임의 skill_id를 받을 수 있으므로 미제시 값 바인딩 차단 (스코프 밖 지침서 주입=IDOR 방지, MED #1).
        offered = set(state.get("offered_skill_ids") or [])
        if str(sel) not in offered:
            _logger.warning("bind_skill 거부 — 미제시 skill_id 바인딩 시도 차단: %s", sel)
            return {
                "collected_frames": [
                    RationaleDeltaFrame(delta="⚠️ 제시되지 않은 스킬은 바인딩할 수 없어 건너뜁니다."),
                ]
            }

        # node_id → category 맵 (node_candidates 우선, 누락분만 registry 조회)
        category_by_node_id = {c.node_id: c.category for c in state.get("node_candidates") or []}

        target_idx: int | None = None
        for i, node in enumerate(workflow.nodes):
            category = category_by_node_id.get(node.node_id)
            if category is None:
                try:
                    schema = await self._node_registry.get_schema(node.node_id)
                    category = getattr(schema, "category", None)
                except Exception:
                    category = None
            if category == "ai":
                target_idx = i
                break

        if target_idx is None:
            return {
                "collected_frames": [
                    RationaleDeltaFrame(delta="⚠️ 선택한 스킬을 바인딩할 LLM 노드가 워크플로우에 없어 건너뜁니다."),
                ]
            }

        nodes = list(workflow.nodes)
        nodes[target_idx] = nodes[target_idx].model_copy(update={"skill_id": sel})
        bound = workflow.model_copy(update={"nodes": nodes})
        return {
            "workflow_draft": bound,
            "collected_frames": [
                RationaleDeltaFrame(delta=f"🔗 스킬 지침서 바인딩 완료 — LLM 노드에 skill_id={sel} 주입"),
            ],
        }

    async def _ensure_llm_candidate(self, candidates: list[NodeConfig]) -> list[NodeConfig]:
        """후보에 LLM 노드(category=="ai")가 없으면 카탈로그에서 하나 확보해 추가 (#372 결함 A).

        스킬 바인딩 대상이 되는 LLM 노드를 drafter가 배치할 수 있게 보장한다. NodeRegistry는
        타입 조회 API가 없어 의미 검색으로 찾고 category=="ai" 첫 후보를 채택한다. 못 찾으면
        무변경(non-fatal) — drafter가 LLM 노드를 못 넣어 바인딩이 skip될 수 있으나 비차단.
        """
        try:
            results = await self._node_registry.search(
                "AI 언어모델 LLM으로 텍스트를 생성·요약·추론하는 노드", limit=5
            )
        except Exception as exc:
            _logger.warning("LLM 노드 확보 검색 실패 (스킬 바인딩 대상 없을 수 있음): %s", exc)
            return candidates
        existing_ids = {c.node_id for c in candidates}
        for cfg in results:
            if getattr(cfg, "category", None) == "ai" and cfg.node_id not in existing_ids:
                return [*candidates, cfg]
        return candidates

    async def _ensure_scaffold_candidates(
        self, candidates: list[NodeConfig], scaffold: Any
    ) -> list[NodeConfig]:
        """scaffold node_type 중 후보에 없는 것을 NodeRegistry에서 정확 조회해 보강 (ADR-0026 §6.6).

        scaffold 노드는 카탈로그 실재(그라운딩 가드)지만 의미검색 후보엔 빠질 수 있다. drafter의
        node_type→node_id 해소를 위해 누락분만 ``list_by_node_types``로 채운다. 실패 시 무변경
        (non-fatal) — 미해소 노드는 scaffold 빌드에서 드롭되고 drafter가 일반 경로로 폴백한다.
        """
        have = {c.node_type for c in candidates}
        missing = list(dict.fromkeys(dn.node_type for dn in scaffold.nodes if dn.node_type not in have))
        if not missing:
            return candidates
        # 기존 호출부(_retriever 보강)와 동일하게 getattr 가드 — port에 메서드가 있어도
        # 테스트 더블/구버전 어댑터가 미구현일 수 있어 일관 방어(#439 리뷰 LOW).
        grounder = getattr(self._node_registry, "list_by_node_types", None)
        if grounder is None:
            return candidates
        try:
            extra = await grounder(missing)
        except Exception as exc:
            _logger.warning("scaffold 후보 보강 실패 (일부 노드 드롭 가능): %s", exc)
            return candidates
        return [*candidates, *extra]

    # 7. drafter_node — 워크플로우 초안 생성
    async def _drafter_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        spec = state["draft_spec"]
        if spec is None:
            return {"error": "DraftSpec 없음"}
        candidates = state["node_candidates"]
        # refine(편집 모드) — 이전 워크플로우를 불러와 "지시한 부분만" 고친다(처음부터 재생성 X).
        # **편집 잠금(조장 지시 2026-06-10)**: confirm 카드가 나온 세션은 편집 전용이다. refine인데
        # prior를 못 불러오면 **새로 만들지 않고 에러로 중단**한다 — 사용자가 쌓은 워크플로우를
        # 조용히 2노드 fresh로 갈아엎던 회귀(#369) 차단. search 후보에 없는 기존 노드는
        # NodeRegistry.get_schema로 복원해 합쳐야 drafter가 그 노드를 직렬화·보존할 수 있다.
        prior_workflow: WorkflowSchema | None = None
        if state.get("intent") == "refine":
            # intent_node가 load해 stash한 prior 재사용(refine 경로 중복 load 방지). 부재 시에만 직접 load.
            prior_workflow = state.get("loaded_prior_workflow")
            if prior_workflow is None and self._workflow_draft_store is not None:
                try:
                    prior_workflow = await self._workflow_draft_store.load_draft(state["session_id"])
                except Exception as exc:
                    _logger.warning("refine: 이전 워크플로우 로드 실패: %s", exc)
                    prior_workflow = None
            if prior_workflow is None:
                # 편집 모드인데 기존 워크플로우 부재 → fresh 생성 금지. "error"만 반환하면
                # 스트리밍 핸들러가 E_COMPOSER 프레임 emit 후 즉시 종료한다(아래 노드 미실행 →
                # 새 워크플로우 안 만들어짐). 사용자에겐 새 대화 안내.
                _logger.warning("refine인데 prior 워크플로우 없음 — 새 생성 잠금, 에러 반환")
                return {
                    "error": "수정할 기존 워크플로우를 찾지 못했어요. 새로 만들려면 '새 대화'를 눌러 주세요.",
                }
            candidates = await self._augment_candidates_with_prior(candidates, prior_workflow)
        # 스킬이 선택되면(two-shot 2차) 그 지침서를 주입할 LLM 노드(category=="ai")가 반드시
        # 필요하다 (#372 결함 A). 후보에 LLM 노드가 없으면 확보해 넣고 drafter에 포함을 지시
        # → drafter가 LLM 노드를 배치 → `_bind_skill_node`가 skill_id를 바인딩한다.
        skill_selected = state.get("selected_skill_id") is not None
        if skill_selected and not any(getattr(c, "category", None) == "ai" for c in candidates):
            candidates = await self._ensure_llm_candidate(candidates)
        # LLM 노드를 끝내 확보 못 했으면(카탈로그 의미검색이 ai 노드 미검출) drafter에 "ai 노드를
        # 포함하라"고 지시하지 않는다 — 후보에 없는 노드 포함을 지시하면 지시/후보 desync(환각·미준수
        # 위험, PR #376 리뷰 LOW #2). 이 경우 바인딩은 어차피 skip(non-fatal)된다.
        instruct_skill_binding = skill_selected and any(
            getattr(c, "category", None) == "ai" for c in candidates
        )
        if skill_selected and not instruct_skill_binding:
            _logger.warning("스킬 선택됐으나 LLM 노드 후보 확보 실패 — 바인딩 skip 예상")
        # ADR-0024 D5: 선택된 스킬의 COMPOSER.md(composer_instructions)를 drafter에 주입.
        # SkillDocumentStore 미주입 또는 문서 없으면 non-fatal(None으로 진행).
        skill_composer_instructions: str | None = None
        if instruct_skill_binding and self._skill_doc_store is not None:
            try:
                skill_doc = await self._skill_doc_store.load(state["selected_skill_id"])
                if skill_doc and skill_doc.composer_instructions:
                    skill_composer_instructions = skill_doc.composer_instructions
            except Exception as exc:
                _logger.warning("COMPOSER.md 로드 실패 (건너뜀): %s", exc)
        # ADR-0026 §6.6: 결정적 스켈레톤 조립 — 구조는 코드가 결정, LLM은 파라미터만 채운다.
        # refine(prior_workflow)만 제외(편집은 prior 구조 보존). **스킬 선택 시에도 조립한다**
        # (조장 2026-06-11): 스켈레톤이 확신 있으면(비-None) drafter가 scaffold 경로(_fill_scaffold_params
        # 분기)를 스킬 지침 draft보다 우선하므로, 잘 짜인 온톨로지 워크플로우가 스킬에 덮어쓰이던 문제
        # 해소. 이때 COMPOSER.md(skill_composer_instructions)의 compose-time 지침은 구조뿐 아니라
        # **전부 yield**된다(_fill_scaffold_params가 받지 않음) — 단 런타임 SKILL.md 주입은 보존돼
        # _bind_skill_node가 그 구조 안 ai 노드에 skill_id를 바인딩한다. assemble None(확신 없음/미지원
        # shape/잡담)이면 스킬 지침 LLM draft로 폴백(drafter가 처리).
        skeleton_scaffold = None
        if prior_workflow is None:
            # ADR-0026 §6.6 Phase 2: SOURCE/SINK 노드 선택을 다중신호 앙상블(lexical+semantic+
            # ontology[+LLM])로 의미화 — 렉시컬 손사전이 못 따라잡는 발화 어휘 변형("gmail에서…")에
            # 강건. resolve 실패/픽 없음이면 assemble이 lexical/grounding으로 폴백(비치명적).
            ranked = tuple(c.node_type for c in candidates)
            resolved = None
            try:
                resolved = await self._slot_resolver.resolve(
                    spec.natural_language_intent,
                    ranked_candidates=ranked,
                    ontology_allowed=frozenset(state.get("ontology_allowed") or ()),
                )
            except Exception as exc:
                _logger.warning("앙상블 슬롯 채움 실패 (렉시컬로 진행): %s", exc)
            try:
                # 앙상블 픽을 우선 주입(resolved_slots). candidate_node_types는 앙상블 미해소
                # source/sink의 레거시 그라운딩 폴백(#453). candidates는 BGE rank 프리픽스 보존.
                skeleton_scaffold = self._skeleton_assembler.assemble(
                    spec.natural_language_intent,
                    candidate_node_types=list(ranked),
                    resolved_slots=resolved,
                )
            except Exception as exc:
                _logger.warning("스켈레톤 조립 실패 (LLM draft로 진행): %s", exc)
                skeleton_scaffold = None
            if skeleton_scaffold is not None:
                candidates = await self._ensure_scaffold_candidates(candidates, skeleton_scaffold)
        # LLM 자유 draft가 **발화에 명시된** 노드를 후보에 멀쩡히 두고도 드롭하던 회귀(#502 측정:
        # "PDF로"의 pdf_generate가 BGE-M3 #2 후보였는데 Gemma 미선택)를 막기 위해, 명시 I/O 노드
        # (트리거/소스/sink)를 drafter에 "반드시 포함"으로 넘긴다. drafter가 후보에 실재하는 것만
        # 지시에 반영(desync 차단). refine은 prior 보존이라 제외. scaffold 성공 시 drafter가
        # 프롬프트 전에 return해 무영향이고, scaffold param-fill 실패→일반 draft 폴백 시엔 directive가
        # 살아 명시 노드를 지킨다(이중 방어). 빈 추출이면 None(무영향).
        required_node_types: list[str] | None = None
        if prior_workflow is None:
            ent = self._skeleton_assembler.extractor.extract(spec.natural_language_intent)
            explicit_io = [nt for nt in (ent.trigger, *ent.sources, *ent.sinks) if nt]
            required_node_types = explicit_io or None
        # degrade로 버린 node_type을 수집할 요청-로컬 sink(동시 요청 안전). 재시도 retriever가
        # 이 ground-truth로 재검색하도록 state에 실어 보낸다(리뷰 #2 — QA-LLM 재인지 의존 제거).
        dropped: list[str] = []
        try:
            workflow = await self._drafter.draft(
                spec, candidates, owner_user_id=state["user_id"], prior_workflow=prior_workflow,
                personal_patterns=state.get("personal_patterns"),
                skill_selected=instruct_skill_binding,
                skill_composer_instructions=skill_composer_instructions,
                retry_feedback=state.get("retry_feedback"),
                dropped_node_types=dropped,
                pattern_templates=state.get("pattern_templates"),
                skeleton_scaffold=skeleton_scaffold,
                required_node_types=required_node_types,
            )
            workflow = self._layout.apply_layout(workflow)
        except Exception as exc:
            return {"error": f"drafter 실패: {exc}"}
        # 사용자가 이미 연결한 서비스(예: SSO google) 노드에 credential_id 선바인딩 —
        # 검증 단계의 불필요한 E_MISSING_CONNECTION을 줄인다(resolver 미주입 시 no-op).
        workflow, bound_services = await self._autobind_connections(
            workflow, candidates, state["user_id"]
        )
        # 산출물(pdf_generate)→발송(email_send/gmail_send) 연결이 있으면 발송 노드 attachments에
        # 산출물 출력 참조를 결정적으로 주입 — 체인 엣지(#532)만으론 이메일이 PDF를 안 실으므로
        # QA "첨부 누락"·런타임 미첨부를 차단. 이미 지정된 attachments는 보존.
        workflow = DrafterService.wire_artifact_attachments(
            workflow, {c.node_id: c.node_type for c in candidates}
        )
        # pdf_generate.sections를 객체 배열 계약([{heading, body}])으로 결정적 정규화 — drafter가
        # 상류 LLM 출력을 ["${x.content}"]처럼 스칼라 원소로 꽂으면 validator가 E_NODE_TYPE_MISMATCH
        # (scalar≠object)로 막으므로, bare 원소를 {"body": ...}로 감싼다(런타임은 어차피 tolerant).
        workflow = DrafterService.wrap_pdf_sections(
            workflow, {c.node_id: c.node_type for c in candidates}
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        nodes_data = [n.model_dump(mode="json") for n in workflow.nodes]
        connections_data = [c.model_dump(mode="json") for c in workflow.connections]
        # NodeInstance엔 node_type 없음(NodeConfig 필드) — candidates로 매핑해 요약 (REQ-004 버그 fix)
        type_by_id = {c.node_id: c.node_type for c in candidates}
        node_summary = ", ".join(type_by_id.get(n.node_id, str(n.node_id)) for n in workflow.nodes)
        verb = "수정" if prior_workflow is not None else "작성"
        draft_summary = (
            f"✏️ 워크플로우 초안 {verb} 완료 — 노드 {len(workflow.nodes)}개 "
            f"({node_summary}), 연결 {len(workflow.connections)}개"
        )
        frames: list[AnySSEFrame] = [RationaleDeltaFrame(delta=draft_summary)]
        if bound_services:
            frames.append(
                RationaleDeltaFrame(
                    delta=f"🔌 보유 연결 자동 바인딩 — {', '.join(sorted(bound_services))}"
                )
            )
        frames.extend([
            DraftSpecDeltaFrame(delta={"attempt": state["qa_attempts"] + 1}),
            WorkflowDraftFrame(nodes=nodes_data, connections=connections_data),
            PipelineStatusFrame(service_name="drafter", status="completed", elapsed_ms=elapsed),
        ])
        # no-progress 시그니처 — node_id 멀티셋 + node_id 수준 엣지(instance_id는 매 draft 랜덤이라
        # node_id로 환산). 재시도 draft가 직전 실패본과 동일하면 재시도해도 같은 결과 → 헛바퀴.
        cur_sig = self._draft_signature(workflow)
        prev_sig = state.get("last_draft_sig")
        return {
            "workflow_draft": workflow,
            "dropped_node_types": dropped,
            "last_draft_sig": cur_sig,
            "draft_repeated": prev_sig is not None and cur_sig == prev_sig,
            "collected_frames": frames,
        }

    @staticmethod
    def _draft_signature(workflow: WorkflowSchema) -> tuple[Any, ...]:
        """draft 구조 시그니처(node_id 집합 + node_id 수준 엣지) — 재시도 진전 판정용.

        instance_id는 draft마다 랜덤이므로 node_id로 환산해 구조만 비교한다(파라미터·위치 무관).
        동일 구조면 재조립/재드래프트가 같은 QA 결과를 낼 것이므로 재시도가 무의미.
        """
        id_to_nodeid = {n.instance_id: n.node_id for n in workflow.nodes}
        node_sig = tuple(sorted(str(n.node_id) for n in workflow.nodes))
        edge_sig = tuple(sorted(
            (str(id_to_nodeid.get(c.from_instance_id)), str(id_to_nodeid.get(c.to_instance_id)))
            for c in workflow.connections
        ))
        return (node_sig, edge_sig)

    async def _autobind_connections(
        self, workflow: WorkflowSchema, candidates: list[NodeConfig], user_id: UUID
    ) -> tuple[WorkflowSchema, set[str]]:
        """노드의 required_connections를 사용자가 보유한 connection으로 **provider별** 선바인딩.

        resolver 미주입 시 그대로 반환(no-op). 각 노드의 required provider를 모두 조회해
        사용자가 보유한 것만 ``credential_ids[provider]``에 채운다 — 멀티커넥션 노드
        (required ≥2)도 provider별로 완전 자동바인딩되며, validator(provider-aware)·executor가
        이 값을 그대로 소비한다(REQ-012). 이미 해소된 provider(명시 ``credential_ids`` 키 또는
        단일 legacy ``credential_id``)는 보존해 refine·사용자 선택을 덮어쓰지 않는다.
        반환된 set은 자동 바인딩된 provider 이름(요약 프레임용).
        """
        if self._connection_resolver is None:
            return workflow, set()
        conns_by_node_id = {c.node_id: c.required_connections for c in candidates}
        bound_services: set[str] = set()
        nodes = list(workflow.nodes)
        changed = False
        for i, node in enumerate(nodes):
            required = conns_by_node_id.get(node.node_id, [])
            if not required:
                continue
            already = set(node.resolve_credentials(required).keys())
            new_binding = dict(node.credential_ids)
            for service in required:
                if service in already:
                    continue  # 이미 바인딩됨(refine/사용자 선택/legacy) — 보존
                try:
                    cid = await self._connection_resolver.resolve(user_id, service)
                except Exception as exc:  # 조회 실패는 비치명적 — 바인딩만 생략
                    _logger.warning("connection 자동 바인딩 조회 실패 (%s): %s", service, exc)
                    cid = None
                if cid is not None:
                    new_binding[service] = cid
                    bound_services.add(service)
            if new_binding != node.credential_ids:
                nodes[i] = node.model_copy(update={"credential_ids": new_binding})
                changed = True
        if not changed:
            return workflow, set()
        return workflow.model_copy(update={"nodes": nodes}), bound_services

    async def _augment_candidates_with_prior(
        self, candidates: list[NodeConfig], prior: WorkflowSchema
    ) -> list[NodeConfig]:
        """refine 시 search 후보에 이전 워크플로우 노드의 NodeConfig를 합친다(node_id dedup).

        refine 메시지("url 바꿔줘")로 검색한 후보엔 기존 노드가 없을 수 있어, 그대로면
        drafter가 기존 노드를 직렬화 못 해 fresh로 폴백한다. get_schema로 복원해 보존을 보장.
        """
        existing_ids = {c.node_id for c in candidates}
        merged = list(candidates)
        for node in prior.nodes:
            if node.node_id in existing_ids:
                continue
            try:
                cfg = await self._node_registry.get_schema(node.node_id)
            except Exception as exc:
                _logger.warning("refine: 노드 스키마 조회 실패 node_id=%s: %s", node.node_id, exc)
                continue
            merged.append(cfg)
            existing_ids.add(node.node_id)
        return merged

    # ---- refine 전용 서브그래프 (op 기반 결정적 편집, PR-2) ----

    async def _load_prior_for_refine(self, state: _State) -> WorkflowSchema | None:
        """refine 대상 prior 워크플로우 로드 — intent_node가 stash한 것 우선, 부재 시 GCS 직접."""
        prior = state.get("loaded_prior_workflow")
        if prior is None and self._workflow_draft_store is not None:
            try:
                prior = await self._workflow_draft_store.load_draft(state["session_id"])
            except Exception as exc:
                _logger.warning("refine: 이전 워크플로우 로드 실패: %s", exc)
                prior = None
        return prior

    async def _refine_plan_node(self, state: _State) -> dict:
        """발화를 편집 연산(EditPlan)으로 번역. 불량 node_type/직렬화 실패/planner 부재 시
        graceful: 1회 재계획(replan) 또는 drafter ref-edit 폴백으로 보낸다. **편집 잠금(#369)**:
        prior 부재면 새로 만들지 않고 에러."""
        attempts = state.get("refine_plan_attempts", 0) + 1
        instruction = state["messages"][-1].get("content", "") if state["messages"] else ""
        prior = await self._load_prior_for_refine(state)
        if prior is None:
            _logger.warning("refine_plan: prior 워크플로우 없음 — 새 생성 잠금, 에러 반환")
            return {"error": "수정할 기존 워크플로우를 찾지 못했어요. 새로 만들려면 '새 대화'를 눌러 주세요."}

        candidates = await self._augment_candidates_with_prior(state["node_candidates"], prior)
        base = {"refine_plan_attempts": attempts, "node_candidates": candidates}
        serialized = DrafterService._serialize_for_edit(prior, candidates)
        if serialized is None or self._edit_planner is None:
            # 직렬화 불가(후보 복원 실패)나 planner 미주입 → drafter ref-edit 폴백(노드 보존).
            return {**base, "edit_fallback": True, "refine_route": "apply"}

        catalog = [
            {
                "node_type": c.node_type,
                "name": c.name,
                "input_schema": _slim_schema(c.input_schema),
                "outputs": _outputs_of(c),
                "required_connections": c.required_connections,
            }
            for c in candidates
        ]
        catalog_types = {c.node_type for c in candidates}
        feedback = state.get("retry_feedback") or state.get("validation_issues")
        try:
            plan = await self._edit_planner.plan(serialized, catalog, instruction, retry_feedback=feedback)
        except Exception as exc:
            _logger.warning("refine_plan: planner 실패 → drafter 폴백: %s", exc)
            return {**base, "edit_fallback": True, "refine_route": "apply"}

        bad = sorted({
            getattr(op, "new_node_type", None)
            for op in plan.ops
            if getattr(op, "new_node_type", None) and getattr(op, "new_node_type") not in catalog_types
        })
        if bad:
            if attempts < _REFINE_PLAN_MAX_ATTEMPTS:
                return {
                    **base,
                    "edit_plan": None,
                    "refine_route": "replan",
                    "retry_feedback": f"Unknown node_type(s) {bad} — use only catalog node_types.",
                }
            # 재계획 소진 → drafter ref-edit 폴백.
            return {**base, "edit_fallback": True, "refine_route": "apply"}

        n_ops = len(plan.ops)
        return {
            **base,
            "edit_plan": plan,
            "refine_route": "apply",
            "collected_frames": [
                RationaleDeltaFrame(delta=f"✏️ 편집 연산 {n_ops}건 계획 완료 — 지시한 부분만 수정합니다"),
                PipelineStatusFrame(service_name="refine_plan", status="completed", elapsed_ms=0),
            ],
        }

    async def _refine_apply_node(self, state: _State) -> dict:
        """EditPlan을 prior에 결정적 적용. 적용 실패/플랜부재 시 drafter ref-edit 폴백(노드 보존,
        절대 fresh 생성 안 함). 이후 layout+autobind는 fresh draft와 동일 후처리."""
        t0 = time.monotonic()
        prior = await self._load_prior_for_refine(state)
        if prior is None:
            return {"error": "수정할 기존 워크플로우를 찾지 못했어요. 새로 만들려면 '새 대화'를 눌러 주세요."}
        candidates = state["node_candidates"]
        plan = state.get("edit_plan")
        spec = state.get("draft_spec")
        edit_fallback = bool(state.get("edit_fallback"))

        try:
            if plan is not None and not edit_fallback and plan.ops:
                workflow = self._edit_service.apply(prior, plan, candidates)
            else:
                # 폴백: drafter ref 기반 전체 편집(노드 보존). prior 직렬화 불가 시 E_REFINE_SERIALIZE.
                edit_fallback = True
                if spec is None:
                    return {"error": "DraftSpec 없음"}
                workflow = await self._drafter.draft(
                    spec, candidates, owner_user_id=state["user_id"], prior_workflow=prior,
                    personal_patterns=state.get("personal_patterns"),
                )
        except Exception as exc:
            _logger.warning("refine_apply: 편집 적용 실패 → 폴백 시도: %s", exc)
            try:
                if spec is None:
                    return {"error": f"편집 적용 실패: {exc}"}
                edit_fallback = True
                workflow = await self._drafter.draft(
                    spec, candidates, owner_user_id=state["user_id"], prior_workflow=prior,
                    personal_patterns=state.get("personal_patterns"),
                )
            except Exception as exc2:
                return {"error": f"편집 적용 실패: {exc2}"}

        workflow = self._layout.apply_layout(workflow)
        workflow, bound_services = await self._autobind_connections(workflow, candidates, state["user_id"])
        elapsed = int((time.monotonic() - t0) * 1000)
        type_by_id = {c.node_id: c.node_type for c in candidates}
        node_summary = ", ".join(type_by_id.get(n.node_id, str(n.node_id)) for n in workflow.nodes)
        frames: list[AnySSEFrame] = [
            RationaleDeltaFrame(
                delta=f"✏️ 워크플로우 수정 적용 — 노드 {len(workflow.nodes)}개 ({node_summary}), "
                      f"연결 {len(workflow.connections)}개"
            )
        ]
        if bound_services:
            frames.append(RationaleDeltaFrame(delta=f"🔌 보유 연결 자동 바인딩 — {', '.join(sorted(bound_services))}"))
        frames.extend([
            WorkflowDraftFrame(
                nodes=[n.model_dump(mode="json") for n in workflow.nodes],
                connections=[c.model_dump(mode="json") for c in workflow.connections],
            ),
            PipelineStatusFrame(service_name="refine_apply", status="completed", elapsed_ms=elapsed),
        ])
        return {"workflow_draft": workflow, "edit_fallback": edit_fallback, "collected_frames": frames}

    # 8. validator_node — 그래프 구조 검증 + RiskLevel 강제
    async def _validator_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state["workflow_draft"]
        if workflow is None:
            return {}
        try:
            await self._graph_validator.validate(workflow)
        except Exception as exc:
            return {"pass_flag": False, "validation_issues": str(exc)}

        # RiskLevel 강제 — PermissionResolver 주입 + department_id 있을 때만
        if self._permission_resolver is not None and state.get("department_id"):
            perm = self._permission_resolver.resolve(
                user_id=state["user_id"],
                role=state["user_role"],  # type: ignore[arg-type]
                department_id=state["department_id"],
                session_id=state["session_id"],
            )
            risk_order = {
                RiskLevel.LOW: 0,
                RiskLevel.MEDIUM: 1,
                RiskLevel.HIGH: 2,
                RiskLevel.RESTRICTED: 3,
            }
            ceiling_val = risk_order.get(perm.risk_ceiling, 3)
            for node in workflow.nodes:
                try:
                    node_schema = await self._node_registry.get_schema(node.node_id)
                    node_risk = getattr(node_schema, "risk_level", None)
                    if node_risk and risk_order.get(node_risk, 0) > ceiling_val:
                        return {
                            "error": (
                                f"권한 초과 노드 포함: {node_schema.name or node.node_id} "
                                f"(risk={node_risk}, ceiling={perm.risk_ceiling})"
                            )
                        }
                except Exception:
                    continue  # 스키마 조회 실패 시 스킵

        return {
            "pass_flag": True,
            "validation_issues": None,
            "collected_frames": [
                RationaleDeltaFrame(delta="✅ 그래프 구조 검증 통과 — DAG, 사이클, 고립 노드, 필수 파라미터 이상 없음"),
                PipelineStatusFrame(service_name="validator", status="completed", elapsed_ms=int((time.monotonic() - t0) * 1000)),
            ],
        }

    # 9. qa_evaluator_node — LLM-as-a-Judge 품질 평가
    async def _qa_evaluator_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state["workflow_draft"]
        spec = state["draft_spec"]
        if workflow is None or spec is None:
            return {}
        # node_id → node_type 맵(node_candidates 우선, 누락분만 registry 조회) — QA LLM이 노드
        # 종류를 파라미터로 추론하지 않고 직접 인식하도록 직렬화에 주입(pdf_generate false-negative
        # 차단). bind_skill의 category_by_node_id와 동일 패턴.
        node_type_by_id: dict[str, str] = {
            str(c.node_id): c.node_type for c in state.get("node_candidates") or []
        }
        for node in workflow.nodes:
            if str(node.node_id) not in node_type_by_id:
                try:
                    schema = await self._node_registry.get_schema(node.node_id)
                    nt = getattr(schema, "node_type", None)
                    if nt:
                        node_type_by_id[str(node.node_id)] = nt
                except Exception:
                    pass
        try:
            result = await self._qa_evaluator.evaluate(workflow, spec, node_types=node_type_by_id)
        except Exception as exc:
            return {"error": f"qa_evaluator 실패: {exc}"}
        elapsed = int((time.monotonic() - t0) * 1000)
        attempt = state["qa_attempts"] + 1
        status_text = "통과" if result.pass_flag else "재시도 필요"
        return {
            "qa_attempts": attempt,
            "qa_score": result.score,
            "pass_flag": result.pass_flag,
            "qa_feedback": result.feedback,
            "collected_frames": [
                RationaleDeltaFrame(delta=f"⭐ 품질 평가 완료 — 점수: {result.score}/10 ({status_text}) | {result.reason or ''}"),
                QAMetricFrame(
                    score=result.score,
                    attempt=attempt,
                    pass_flag=result.pass_flag,
                    feedback=result.feedback,
                ),
                PipelineStatusFrame(service_name="qa_evaluator", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 10. qa_retry_node — validate/QA 실패 시 재시도 준비 (draft_workflow로 돌아감)
    async def _qa_retry_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        feedback = state.get("qa_feedback", "")
        validation_issues = state.get("validation_issues") or ""
        combined_feedback = " | ".join(filter(None, [feedback, validation_issues]))
        # 피드백은 natural_language_intent에 섞지 않는다 — 그러면 영어 교정문이 워크플로우
        # 이름/설명으로 누출된다(#378 부차). 별도 state 필드로 전달해 drafter가 교정에만 쓴다.
        updates: dict = {
            "retry_feedback": combined_feedback,
            "retry_count": state.get("retry_count", 0) + 1,
        }
        # B(#378 후속): 재시도 시 retriever 재검색 — 직전 후보로 충족 못 한 능력을 원 intent에
        # 보강해 새 노드를 끌어온다. 보강 신호 2종: (1) drafter가 degrade로 버린 node_type
        # (ground-truth, 리뷰 #2 — QA-LLM 재인지에 의존하지 않는 결정적 신호) (2) QA가 feedback에
        # 적은 missing_capabilities. 직전 후보는 보존하고 합집합(node_id dedup). 재검색 실패는 비치명적.
        spec = state.get("draft_spec")
        base_query = spec.natural_language_intent if spec else ""
        dropped = " ".join(state.get("dropped_node_types") or [])
        search_query = " ".join(filter(None, [base_query, dropped, combined_feedback])).strip()
        if search_query:
            try:
                fresh = await self._node_registry.search(search_query)
            except Exception as exc:
                _logger.warning("재시도 retriever 재검색 실패 (non-fatal): %s", exc)
                fresh = []
            if fresh:
                existing = state.get("node_candidates") or []
                merged = self._dedup_union(existing, list(fresh))
                if len(merged) != len(existing):
                    updates["node_candidates"] = merged
        elapsed = int((time.monotonic() - t0) * 1000)
        updates["collected_frames"] = [
            PipelineStatusFrame(service_name="qa_retry", status="started", elapsed_ms=elapsed),
        ]
        return updates

    # 11. promote_node — QA 통과 후 확정 + WorkflowDraftStore에 AI 초안 보관
    async def _promote_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state.get("workflow_draft")
        if workflow is None:
            return {"error": "promote 실패: workflow_draft 없음"}

        # WorkflowDraftStore에 AI 생성 초안 저장 (사용자 승인 후 diff 비교용)
        if self._workflow_draft_store is not None:
            try:
                await self._workflow_draft_store.save_draft(state["session_id"], workflow)
            except Exception as exc:
                _logger.warning("draft 저장 실패 (non-fatal): %s", exc)

        promoted = workflow.model_copy(update={"is_draft": False})
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "workflow_draft": promoted,
            "collected_frames": [
                PipelineStatusFrame(service_name="promote", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 12. handoff_node — WorkflowRepository.save → saved_workflow_id 저장
    async def _handoff_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state["workflow_draft"]
        if workflow is None:
            return {
                "saved_workflow_id": None,
                "collected_frames": [
                    ResultFrame(intent="propose", payload={"status": "no_workflow"})
                ],
            }
        try:
            workflow_id = await self._workflow_repo.save(workflow)
        except Exception as exc:
            return {"error": f"workflow 저장 실패: {exc}"}
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "saved_workflow_id": workflow_id,
            "collected_frames": [
                PipelineStatusFrame(service_name="handoff", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 13. execute_node — 실행 엔진 호출 + 결과 폴링 (HITL 게이트: 사용자 명시 요청 필수)
    async def _execute_node(self, state: _State) -> dict:
        t0 = time.monotonic()

        workflow_id = state.get("saved_workflow_id")
        if not workflow_id:
            return {
                "execution_id": None,
                "execution_result": {"status": "skipped", "reason": "workflow_id 없음"},
                "collected_frames": [
                    PipelineStatusFrame(service_name="execute", status="failed")
                ],
            }

        base_url = self._execution_engine_url
        if not base_url:
            _logger.warning("EXECUTION_ENGINE_URL 미설정 — 실행 검증 건너뜀")
            return {
                "execution_id": None,
                "execution_result": {"status": "skipped", "reason": "EXECUTION_ENGINE_URL 미설정"},
                "collected_frames": [
                    PipelineStatusFrame(service_name="execute", status="completed", elapsed_ms=0)
                ],
            }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    base_url + _EXEC_START_PATH.format(workflow_id=workflow_id),
                    json={"session_id": str(state["session_id"])},
                )
                resp.raise_for_status()
                start_data = resp.json()

            execution_id: str = start_data.get("execution_id", "")
            _logger.info("실행 시작: execution_id=%s", execution_id)

            result = await self._poll_execution_result(base_url, execution_id)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return {
                "execution_id": None,
                "execution_result": {"status": "failed", "error": str(exc)},
                "collected_frames": [
                    PipelineStatusFrame(service_name="execute", status="failed", elapsed_ms=elapsed)
                ],
            }

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "execution_id": execution_id,
            "execution_result": result,
            "collected_frames": [
                PipelineStatusFrame(service_name="execute", status="completed", elapsed_ms=elapsed)
            ],
        }

    async def _poll_execution_result(self, base_url: str, execution_id: str) -> dict[str, Any]:
        """실행 결과를 폴링으로 조회. 팀장님 결과 조회 API 확정 후 endpoint 조정."""
        deadline = time.monotonic() + _EXEC_TIMEOUT_SEC
        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        base_url + _EXEC_POLL_PATH.format(execution_id=execution_id)
                    )
                    if resp.status_code == 200:
                        data: dict[str, Any] = resp.json()
                        status = data.get("status", "")
                        if status in ("completed", "failed", "cancelled"):
                            return data
            except Exception as poll_exc:
                _logger.debug("폴링 중 오류 (재시도): %s", poll_exc)
            await asyncio.sleep(_EXEC_POLL_INTERVAL_SEC)

        return {"status": "timeout", "execution_id": execution_id}

    # 14. evaluate_output_node — 실행 산출물 퀄리티 검증
    async def _evaluate_output_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        result = state.get("execution_result") or {}
        status = result.get("status", "unknown")

        # 실행 실패/타임아웃이면 즉시 저점 처리
        if status in ("failed", "timeout", "cancelled"):
            elapsed = int((time.monotonic() - t0) * 1000)
            return {
                "output_quality_score": 0.0,
                "output_quality_feedback": f"실행 {status}",
                "collected_frames": [
                    PipelineStatusFrame(service_name="evaluate_output", status="failed", elapsed_ms=elapsed)
                ],
            }

        if status == "skipped":
            elapsed = int((time.monotonic() - t0) * 1000)
            return {
                "output_quality_score": 5.0,
                "output_quality_feedback": "실행 검증 건너뜀",
                "collected_frames": [
                    PipelineStatusFrame(service_name="evaluate_output", status="completed", elapsed_ms=elapsed)
                ],
            }

        # LLM 평가 — llm 주입된 경우
        score = 7.0
        feedback = "실행 완료"
        if self._llm is not None:
            try:
                spec = state.get("draft_spec")
                intent = spec.natural_language_intent if spec else "알 수 없음"
                prompt = (
                    "워크플로우 실행 결과를 검토해 0-10점으로 평가하세요.\n"
                    f"사용자 의도: {intent}\n"
                    f"실행 상태: {status}\n"
                    f"결과 요약: {json.dumps(result, ensure_ascii=False)[:500]}\n"
                    "평가 기준: 오류 없음(+4), 의도 달성(+4), 성능 적절(+2)\n"
                    '응답은 반드시 JSON: {"score": <float>, "feedback": "<한 줄 평가>"}'
                )
                raw = await self._llm.generate(prompt)
                parsed = json.loads(raw)
                score = float(parsed.get("score", 7.0))
                feedback = parsed.get("feedback", "LLM 평가 완료")
            except Exception as exc:
                _logger.warning("output 품질 LLM 평가 실패, 기본값 사용: %s", exc)

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "output_quality_score": score,
            "output_quality_feedback": feedback,
            "collected_frames": [
                PipelineStatusFrame(service_name="evaluate_output", status="completed", elapsed_ms=elapsed)
            ],
        }

    # 14-b. explain_node — WorkflowExplanation 생성 (컨펌 게이트 신뢰 매니페스트)
    async def _explain_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state.get("workflow_draft")
        spec = state.get("draft_spec")
        if workflow is None or spec is None:
            return {}
        try:
            explanation = self._workflow_explanation_svc.explain(
                workflow=workflow,
                spec=spec,
                node_configs=state.get("node_candidates") or [],
            )
        except Exception as exc:
            _logger.warning("explain_node 실패 (non-fatal): %s", exc)
            return {}
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "workflow_explanation": explanation,
            "collected_frames": [
                PipelineStatusFrame(service_name="explain", status="completed", elapsed_ms=elapsed),
            ],
        }

    @staticmethod
    def _build_qa_checklist(state: _State) -> str:
        """QA 통과 후 ConfirmCard 직전에 채팅창에 표시할 AI 검증 완료 보고서."""
        intent = state.get("intent") or "알 수 없음"
        entities = state.get("intent_analyzed_entities") or {}
        candidates = state.get("node_candidates") or []
        workflow = state.get("workflow_draft")
        qa_score = state.get("qa_score", 0.0)
        qa_feedback = state.get("qa_feedback", "")
        spec = state.get("draft_spec")

        intent_labels: dict[str, str] = {
            "draft": "새 워크플로우 생성",
            "refine": "워크플로우 수정",
            "clarify": "추가 정보 요청",
        }
        intent_label = intent_labels.get(str(intent), str(intent))
        entity_text = (
            ", ".join(f"{k}: {v}" for k, v in list(entities.items())[:5])
            if entities else "없음"
        )

        final_nodes = workflow.nodes if workflow else []
        final_connections = workflow.connections if workflow else []
        type_by_id = {c.node_id: c.node_type for c in candidates}
        selected_types = ", ".join(
            type_by_id.get(n.node_id, "알 수 없음") for n in final_nodes[:5]
        )
        if len(final_nodes) > 5:
            selected_types += f" 외 {len(final_nodes) - 5}개"

        intent_text = spec.natural_language_intent[:80] if spec else "없음"

        is_refine = str(intent) == "refine"
        section3_title = "**③ 워크플로우 수정**" if is_refine else "**③ 워크플로우 작성**"
        lines = [
            "📋 **AI 검증 완료 보고서**",
            "",
            "**① 의도 분석** ✅",
            f"- 요청 유형: {intent_label}",
            f"- 요청 내용: {intent_text}",
            f"- 추출된 정보: {entity_text}",
            "",
            "**② 노드 선출** ✅",
            f"- 후보 {len(candidates)}개 검색 완료",
            f"- 최종 선정: {len(final_nodes)}개 노드 ({selected_types or '없음'})",
            "",
            f"{section3_title} ✅",
            f"- 노드 {len(final_nodes)}개, 연결 {len(final_connections)}개",
            "- DAG 구조 검증 완료 (사이클 없음, 고립 노드 없음)",
            "",
        ]

        # refine은 QA 커버리지 게이트를 타지 않는다(부정 발화 오작동 차단) — 대신 prior 대비
        # 실제 변경(diff)을 ④로 보여 "지시한 부분만 고쳤다"를 사용자가 검증하게 한다.
        prior = state.get("loaded_prior_workflow")
        if is_refine and prior is not None and workflow is not None:
            diff = WorkflowDiffService().compute(prior, workflow)
            lines.append(
                f"**④ 수정 적용 완료** ✅ (추가 {len(diff.added_nodes)} / 삭제 "
                f"{len(diff.removed_nodes)} / 파라미터 변경 {len(diff.modified_params)})"
            )
            detail: list[str] = []
            for n in diff.removed_nodes[:5]:
                detail.append(f"- 삭제: {type_by_id.get(n.node_id, str(n.node_id))}")
            for n in diff.added_nodes[:5]:
                detail.append(f"- 추가: {type_by_id.get(n.node_id, str(n.node_id))}")
            for p in diff.modified_params[:5]:
                detail.append(f"- 변경: {type_by_id.get(p.node_id, str(p.node_id))}.{p.param_key} → {p.after!r}")
            lines.extend(detail or ["- 구조·파라미터 변경 없음"])
        else:
            lines.extend([
                f"**④ QA 품질 평가 통과** ✅ (점수: {qa_score:.1f}/10)",
                "- 완성도: 사용자 의도가 노드로 완전히 표현됐는지 검증",
                "- 안전성: 위험 노드 정당성 및 권한 적정성 검증",
            ])
            if qa_feedback:
                lines.append(f"- 평가 의견: {qa_feedback}")

        return "\n".join(lines)

    # 15. user_confirm_node — 최종 ResultFrame emit (fixed DAG: 항상 ready_to_execute)
    async def _user_confirm_node(self, state: _State) -> dict:
        workflow_id = state.get("saved_workflow_id")
        execution_result = state.get("execution_result")

        if execution_result is not None:
            return {
                "collected_frames": [
                    ResultFrame(
                        intent="execution_review",
                        payload={
                            "workflow_id": str(workflow_id) if workflow_id else None,
                            "execution_id": state.get("execution_id"),
                            "execution_status": execution_result.get("status"),
                            "output_quality_score": state.get("output_quality_score", 0.0),
                            "output_quality_feedback": state.get("output_quality_feedback", ""),
                            "session_id": str(state["session_id"]),
                        },
                    ),
                ]
            }

        explanation = state.get("workflow_explanation")
        qa_checklist = self._build_qa_checklist(state)
        return {
            "collected_frames": [
                ChatMessageFrame(role="assistant", content=qa_checklist),
                ResultFrame(
                    intent="propose",
                    payload={
                        "workflow_id": str(workflow_id) if workflow_id else None,
                        "status": "ready_to_execute",
                        "message": "워크플로우가 완성됐습니다. 저장하거나 편집 탭에서 편집 후 실행하세요.",
                        "session_id": str(state["session_id"]),
                        "explanation": explanation.model_dump(mode="json") if explanation else None,
                    },
                ),
            ]
        }

    # 16-a. validation_failed_node — 검증 실패 종결 (재시도 소진 또는 no-progress)
    async def _validation_failed_node(self, state: _State) -> dict:
        repeated = state.get("draft_repeated")
        detail = state.get("validation_issues") or ""
        reason = (
            "동일한 구조가 반복돼 더 진행해도 해결되지 않습니다 — 현재 노드로 만들 수 없는 요청일 수 있어요."
            if repeated
            else f"워크플로우 검증 {_QA_MAX_RETRY}회 실패"
        )
        msg = f"{reason}{(' — ' + detail) if detail else ''} 요청을 더 구체적으로 말씀해 주세요."
        return {"collected_frames": [ErrorFrame(code="E_VALIDATION_EXHAUSTED", message=msg)]}

    # 16-b. qa_failed_node — QA 실패 종결 (재시도 소진 또는 no-progress)
    async def _qa_failed_node(self, state: _State) -> dict:
        # no-progress면 솔직하게: 같은 결과가 반복돼 충족 못 한 능력(qa_feedback의 누락 채널/노드)을
        # 그대로 노출 — out-of-scope(없는 노드 필요) 요청을 5회 헛돌지 않고 빠르게 정직하게 실패.
        repeated = state.get("draft_repeated")
        feedback = (state.get("qa_feedback") or "").strip()
        if repeated:
            base = "동일한 결과가 반복돼 품질 기준을 충족하지 못했습니다 — 현재 노드로 만들 수 없는 요청일 수 있어요."
        else:
            base = f"품질 평가 {_QA_MAX_RETRY}회 실패"
        msg = f"{base}{(' (' + feedback + ')') if feedback else ''} 요청을 더 구체적으로 말씀해 주세요."
        return {"collected_frames": [ErrorFrame(code="E_QA_EXHAUSTED", message=msg)]}

    # 16. memory_save_node — 워크플로우 생성 패턴을 GCS PersonalMemoryStore에 저장
    async def _memory_save_node(self, state: _State) -> dict:
        # two-shot 2차 성공 종료 — 재개 상태 정리 (멱등, non-fatal)
        if state.get("round", 1) == 2 and self._composer_state_store is not None:
            try:
                await self._composer_state_store.delete_state(state["session_id"])
            except Exception as exc:
                _logger.warning("composer 상태 정리 실패 (non-fatal): %s", exc)

        if self._personal_memory_store is None:
            return {}

        try:
            claimed = await self._personal_memory_store.claim_debounce_window(
                state["user_id"], datetime.now(UTC), timedelta(minutes=5)
            )
            if not claimed:
                return {}

            workflow_id = state.get("saved_workflow_id")
            intent = state.get("intent") or ""
            if not workflow_id or not intent:
                return {}

            first_msg = state["messages"][0].get("content", "") if state["messages"] else ""
            mem_file = MemoryFile(
                filename=f"workflow_{workflow_id}.md",
                name=f"workflow_{workflow_id}",
                description=first_msg[:80],
                memory_type="project",
                body=(
                    f"사용자 의도: {intent}\n"
                    f"워크플로우 ID: {workflow_id}\n"
                    f"QA 점수: {state.get('qa_score', 0.0)}\n"
                    f"QA 시도: {state.get('qa_attempts', 0)}회\n"
                ),
            )
            await self._personal_memory_store.save_file(state["user_id"], mem_file)

            refs = await self._personal_memory_store.load_index(state["user_id"])
            refs = [r for r in refs if r.filename != mem_file.filename]
            refs.insert(0, MemoryFileRef(
                name=mem_file.name,
                filename=mem_file.filename,
                description=mem_file.description,
            ))
            await self._personal_memory_store.save_index(state["user_id"], refs)
        except Exception as exc:
            _logger.warning("memory save 실패 (non-fatal): %s", exc)

        return {}

    @staticmethod
    def _should_compress(state: _State) -> str:
        if state.get("turn_count", 0) >= TurnLimit.MAX:
            return "compress"
        return "security"

    # ------------------------------------------------------------------ build

    def _build(self):
        graph: StateGraph = StateGraph(_State)

        # two-shot DAG (REQ-013):
        #   [1차] compress → security → intent → search_nodes → suggest_skill_select
        #         → (옵션 emit) END  /  (옵션 없음·미주입 one-shot 폴백) draft_workflow → …
        #   [2차] resume → draft_workflow → bind_skill → validate → qa → promote → save → confirm → memory → END
        graph.add_node("compress", self._compress_node)
        graph.add_node("security", self._security_node)
        graph.add_node("intent", self._intent_node)
        graph.add_node("consultant", self._consultant_node)
        graph.add_node("slot_fill", self._slot_fill_node)
        graph.add_node("search_nodes", self._retriever_node)
        graph.add_node("suggest_skill_select", self._suggest_skill_select_node)  # two-shot 1차 종단
        graph.add_node("resume", self._resume_node)                              # two-shot 2차 진입
        graph.add_node("bind_skill", self._bind_skill_node)                      # 2차 skill_id 바인딩
        graph.add_node("draft_workflow", self._drafter_node)
        graph.add_node("refine_plan", self._refine_plan_node)        # refine 전용 — op 계획
        graph.add_node("refine_apply", self._refine_apply_node)      # refine 전용 — 결정적 적용
        graph.add_node("validate_workflow", self._validator_node)
        graph.add_node("retry_draft", self._qa_retry_node)
        graph.add_node("qa_evaluator", self._qa_evaluator_node)
        graph.add_node("validation_failed", self._validation_failed_node)
        graph.add_node("qa_failed", self._qa_failed_node)
        graph.add_node("promote", self._promote_node)
        graph.add_node("save_workflow", self._handoff_node)
        graph.add_node("explain", self._explain_node)
        graph.add_node("confirm_result", self._user_confirm_node)
        graph.add_node("save_memory", self._memory_save_node)

        # 진입 분기 — round=2(선택 입력)는 resume부터, round=1은 compress(전처리)부터
        graph.set_conditional_entry_point(
            self._route_entry,
            {"compress": "compress", "resume": "resume"},
        )
        # 2차 resume: 복원 성공 → draft, 실패 → 종료(E_SESSION_EXPIRED는 노드에서 emit)
        graph.add_conditional_edges(
            "resume",
            self._route_after_resume,
            {"draft": "draft_workflow", "end": END},
        )
        graph.add_conditional_edges(
            "compress",
            self._should_compress,
            {"compress": "compress", "security": "security"},
        )
        graph.add_conditional_edges(
            "security",
            self._route_after_security,
            {"intent": "intent", "end": END},
        )
        graph.add_conditional_edges(
            "intent",
            self._route_after_intent,
            {"consultant": "consultant", "search_nodes": "search_nodes", "end": END},
        )
        graph.add_edge("consultant", "slot_fill")
        graph.add_edge("slot_fill", END)
        # 1차: 노드 검색 직후 스킬 옵션 제시 단계로 (draft는 아직 미생성)
        graph.add_edge("search_nodes", "suggest_skill_select")
        # refine → op 편집 서브그래프 / 옵션 emit+중단(two-shot) → END / 그 외 → draft(fresh).
        # **fresh 경로(draft→bind→validate→qa) 엣지는 불변** — refine만 suggest에서 분기.
        graph.add_conditional_edges(
            "suggest_skill_select",
            self._route_after_suggest,
            {"wait": END, "draft": "draft_workflow", "refine": "refine_plan"},
        )
        # refine: 계획 → (불량 type 1회 replan) → 적용 → validate. prior 부재 시 error로 END.
        graph.add_conditional_edges(
            "refine_plan",
            self._route_after_refine_plan,
            {"apply": "refine_apply", "replan": "refine_plan", "end": END},
        )
        graph.add_edge("refine_apply", "validate_workflow")
        # draft 직후 항상 bind_skill 경유 (1차 폴백=no-op, 2차=skill_id 주입)
        graph.add_edge("draft_workflow", "bind_skill")
        graph.add_edge("bind_skill", "validate_workflow")
        # validate 후: fresh→qa_evaluator, refine→promote(QA 스킵)/실패 시 1회 refine_plan 재계획.
        graph.add_conditional_edges(
            "validate_workflow",
            self._route_after_validate,
            {
                "qa_evaluator": "qa_evaluator",
                "retry_draft": "retry_draft",
                "validation_failed": "validation_failed",
                "promote": "promote",
                "refine_plan": "refine_plan",
            },
        )
        graph.add_edge("retry_draft", "draft_workflow")
        graph.add_conditional_edges(
            "qa_evaluator",
            self._route_after_qa,
            {"promote": "promote", "retry_draft": "retry_draft", "qa_failed": "qa_failed"},
        )
        graph.add_edge("validation_failed", END)
        graph.add_edge("qa_failed", END)
        graph.add_edge("promote", "save_workflow")
        graph.add_edge("save_workflow", "explain")
        graph.add_edge("explain", "confirm_result")
        graph.add_edge("confirm_result", "save_memory")
        graph.add_edge("save_memory", END)

        return graph.compile()
