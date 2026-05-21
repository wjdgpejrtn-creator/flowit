"""LangGraph Orchestrator (Composer) — Workflow Composer 어댑터 레이어.

spec §3.2 Workflow Composer 내부 StateGraph 구현. LangGraph는 adapters/에만 존재.
13개 노드:
  security → intent →
    [clarify]      consultant → slot_fill (loop)
    [draft/refine] retriever → drafter → validator → qa_evaluator
                                                     score<8 → qa_retry → drafter
                                                     score>=8 ↓
    [propose]      ──────────────────────────────── promote → handoff → memory_save
  compress (turn_count >= 25 시 entry point 앞 삽입)
"""
from __future__ import annotations

import logging
import operator
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict
from uuid import UUID, uuid4

from auth.domain.services.permission_resolver import PermissionResolver
from common_schemas.agent import DraftSpec, MemoryEntry, SlotFillingState
from common_schemas.enums import IntentType, RiskLevel
from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    DraftSpecDeltaFrame,
    ErrorFrame,
    IntentResultFrame,
    PipelineStatusFrame,
    QAMetricFrame,
    ResultFrame,
    SessionFrame,
    SlotFillQuestionFrame,
    SSEFrame,
    WorkflowDraftFrame,
)
from common_schemas.workflow import NodeConfig, WorkflowSchema
from langgraph.graph import END, StateGraph
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.services.graph_validator import GraphValidator
from skills_marketplace.application.use_cases.search_skills_use_case import SearchSkillsUseCase
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

from ...domain.entities.session_ref import SessionRef
from ...domain.ports.node_registry import NodeRegistry
from ...domain.ports.session_frame_store import SessionFrameStore
from ...domain.ports.workflow_repository import WorkflowRepository
from ...domain.services.drafter_service import DrafterService
from ...domain.services.intent_analyzer_service import IntentAnalyzerService
from ...domain.services.qa_evaluator_service import QAEvaluatorService
from ...domain.services.slot_filling_service import SlotFillingService
from ...domain.services.workflow_layout_service import WorkflowLayoutService
from ...domain.value_objects.turn_limit import TurnLimit

_logger = logging.getLogger(__name__)

_QA_MAX_RETRY = 3

# routing keys
_CLARIFY = "clarify"
_DRAFT = "draft"
_PROPOSE = "propose"
_QA_PASS = "qa_pass"
_QA_RETRY = "qa_retry"
_QA_FORCE = "qa_force"
_SLOT_LOOP = "slot_loop"
_SLOT_DONE = "slot_done"


class _State(TypedDict):
    session_id: UUID
    user_id: UUID
    user_role: str  # "User" | "Admin" — PermissionResolver 권한 확인용
    department_id: UUID | None
    messages: list[dict[str, Any]]
    turn_count: int
    personal_memory: list[MemoryEntry]
    intent: str | None
    intent_analyzed_entities: dict[str, Any]
    draft_spec: DraftSpec | None
    node_candidates: list[NodeConfig]
    workflow_draft: WorkflowSchema | None
    qa_attempts: int
    qa_score: float
    pass_flag: bool
    qa_feedback: str
    collected_frames: Annotated[list[AnySSEFrame], operator.add]
    error: str | None


class LangGraphOrchestrator:
    """Workflow Composer 내부 13-노드 StateGraph (spec §3.2).

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
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._drafter = drafter
        self._qa_evaluator = qa_evaluator
        self._slot_filler = slot_filler
        self._node_registry = node_registry
        self._workflow_repo = workflow_repo
        self._graph_validator = graph_validator
        self._permission_resolver = permission_resolver
        self._embedder = embedder
        self._skill_search = skill_search
        self._session_frame_store = session_frame_store
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
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._run(user_id, session_id, message, personal_memory or [], user_role, department_id)

    async def _run(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        personal_memory: list[MemoryEntry],
        user_role: str,
        department_id: UUID | None,
    ) -> AsyncGenerator[SSEFrame, None]:
        session_frame = SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())
        yield session_frame
        all_frames: list[AnySSEFrame] = [session_frame]

        initial: _State = {
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "department_id": department_id,
            "messages": [{"role": "user", "content": message}],
            "turn_count": 1,
            "personal_memory": personal_memory,
            "intent": None,
            "intent_analyzed_entities": {},
            "draft_spec": None,
            "node_candidates": [],
            "workflow_draft": None,
            "qa_attempts": 0,
            "qa_score": 0.0,
            "pass_flag": False,
            "qa_feedback": "",
            "collected_frames": [],
            "error": None,
        }

        async for event in self._graph.astream(initial, stream_mode="updates"):
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

    # ------------------------------------------------------------------ nodes (13)

    # 1. compress_node — turn_count >= 25 시 메시지 압축
    async def _compress_node(self, state: _State) -> dict:
        TurnLimit().validate(state["turn_count"])
        # 압축: 마지막 메시지만 보존
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
        # 실 노드가 확정되는 validator/drafter 단계에서 별도 처리 필요.
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
        try:
            result = await self._intent_analyzer.analyze(
                state["messages"], context={}
            )
        except Exception as exc:
            return {"intent": "clarify", "error": f"intent 분석 실패: {exc}"}
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
        # intent_analyzer가 이미 추출한 엔티티는 filled로 이동
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

    # 6. retriever_node — 노드 후보 검색 + 커스텀 스킬 합산
    async def _retriever_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        spec = state["draft_spec"]
        query = spec.natural_language_intent if spec else state["messages"][-1].get("content", "")
        try:
            candidates = await self._node_registry.search(query)
        except Exception as exc:
            return {"error": f"retriever 실패: {exc}"}

        # 커스텀 스킬 검색 — embedder + skill_search 모두 주입된 경우에만
        if self._embedder is not None and self._skill_search is not None:
            try:
                query_embedding = await self._embedder.embed(query)
                skill_results = await self._skill_search.execute(
                    query_embedding=query_embedding,
                    scope=SkillScope.COMPANY,
                    limit=10,
                )
                existing_ids = {c.node_id for c in candidates}
                for skill in skill_results:
                    try:
                        node_cfg = await self._node_registry.get_schema(skill.node_definition_id)
                        if node_cfg.node_id not in existing_ids:
                            candidates = [*candidates, node_cfg]
                            existing_ids.add(node_cfg.node_id)
                    except Exception:
                        continue  # 노드 정의 없으면 스킵
            except Exception as _skill_exc:
                import logging as _log
                _log.getLogger(__name__).warning("skill search failed: %s", _skill_exc)

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "node_candidates": candidates,
            "collected_frames": [
                PipelineStatusFrame(service_name="retriever", status="completed", elapsed_ms=elapsed)
            ],
        }

    # 7. drafter_node — 워크플로우 초안 생성
    async def _drafter_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        spec = state["draft_spec"]
        if spec is None:
            return {"error": "DraftSpec 없음"}
        try:
            workflow = await self._drafter.draft(spec, state["node_candidates"], owner_user_id=state["user_id"])
            workflow = self._layout.apply_layout(workflow)
        except Exception as exc:
            return {"error": f"drafter 실패: {exc}"}
        elapsed = int((time.monotonic() - t0) * 1000)
        nodes_data = [n.model_dump(mode="json") for n in workflow.nodes]
        connections_data = [c.model_dump(mode="json") for c in workflow.connections]
        return {
            "workflow_draft": workflow,
            "collected_frames": [
                DraftSpecDeltaFrame(delta={"attempt": state["qa_attempts"] + 1}),
                WorkflowDraftFrame(nodes=nodes_data, connections=connections_data),
                PipelineStatusFrame(service_name="drafter", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 8. validator_node — 그래프 구조 검증
    async def _validator_node(self, state: _State) -> dict:
        workflow = state["workflow_draft"]
        if workflow is None:
            return {}
        try:
            await self._graph_validator.validate(workflow)
        except Exception as exc:
            return {"error": f"validator 실패: {exc}"}
        return {}

    # 9. qa_evaluator_node — LLM-as-a-Judge 품질 평가
    async def _qa_evaluator_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state["workflow_draft"]
        spec = state["draft_spec"]
        if workflow is None or spec is None:
            return {}
        try:
            result = await self._qa_evaluator.evaluate(workflow, spec)
        except Exception as exc:
            return {"error": f"qa_evaluator 실패: {exc}"}
        elapsed = int((time.monotonic() - t0) * 1000)
        attempt = state["qa_attempts"] + 1
        return {
            "qa_attempts": attempt,
            "qa_score": result.score,
            "pass_flag": result.pass_flag,
            "qa_feedback": result.feedback,
            "collected_frames": [
                QAMetricFrame(
                    score=result.score,
                    attempt=attempt,
                    pass_flag=result.pass_flag,
                    feedback=result.feedback,
                ),
                PipelineStatusFrame(service_name="qa_evaluator", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 10. qa_retry_node — QA 실패 시 재시도 준비 (drafter로 돌아감)
    async def _qa_retry_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        spec = state.get("draft_spec")
        feedback = state.get("qa_feedback", "")
        if spec and feedback:
            updated_intent = f"{spec.natural_language_intent}\n[QA 피드백: {feedback}]"
            spec = spec.model_copy(update={"natural_language_intent": updated_intent})
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "draft_spec": spec,
            "collected_frames": [
                PipelineStatusFrame(service_name="qa_retry", status="started", elapsed_ms=elapsed),
            ],
        }

    # 11. promote_node — propose 인텐트 또는 QA 통과 후 확정
    async def _promote_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state.get("workflow_draft")
        if workflow is None:
            return {"error": "promote 실패: workflow_draft 없음"}
        promoted = workflow.model_copy(update={"is_draft": False})
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "workflow_draft": promoted,
            "collected_frames": [
                PipelineStatusFrame(service_name="promote", status="completed", elapsed_ms=elapsed),
            ],
        }

    # 12. handoff_node — WorkflowRepository.save → workflow_id → REQ-007
    async def _handoff_node(self, state: _State) -> dict:
        t0 = time.monotonic()
        workflow = state["workflow_draft"]
        if workflow is None:
            return {
                "collected_frames": [
                    ResultFrame(intent="propose", payload={"status": "no_workflow"})
                ]
            }
        try:
            workflow_id = await self._workflow_repo.save(workflow)
        except Exception as exc:
            return {"error": f"workflow 저장 실패: {exc}"}
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "collected_frames": [
                ResultFrame(intent="draft", payload={"workflow_id": str(workflow_id)}),
                PipelineStatusFrame(service_name="handoff", status="completed", elapsed_ms=elapsed),
            ]
        }

    # 13. memory_save_node — 세션 종료 후 메모리 저장 (AgentMemoryRepository는 DI 외부 처리)
    async def _memory_save_node(self, state: _State) -> dict:
        return {}

    # ------------------------------------------------------------------ routing

    @staticmethod
    def _route_intent(state: _State) -> str:
        intent = state.get("intent") or IntentType.CLARIFY
        if intent == IntentType.PROPOSE:
            return _PROPOSE
        if intent == IntentType.CLARIFY:
            return _CLARIFY
        return _DRAFT  # draft / refine

    @staticmethod
    def _route_slot(state: _State) -> str:
        spec = state.get("draft_spec")
        if spec and spec.slot_filling_state.pending:
            return _SLOT_LOOP
        return _SLOT_DONE

    @staticmethod
    def _route_qa(state: _State) -> str:
        qa_attempts = state.get("qa_attempts", 0)
        if qa_attempts >= _QA_MAX_RETRY:
            return _QA_FORCE
        if state.get("pass_flag"):
            return _QA_PASS
        return _QA_RETRY

    @staticmethod
    def _should_compress(state: _State) -> str:
        if state.get("turn_count", 0) >= TurnLimit.MAX:
            return "compress"
        return "security"

    # ------------------------------------------------------------------ build

    def _build(self):
        graph: StateGraph = StateGraph(_State)

        # 13 nodes
        graph.add_node("compress", self._compress_node)
        graph.add_node("security", self._security_node)
        graph.add_node("intent", self._intent_node)
        graph.add_node("consultant", self._consultant_node)
        graph.add_node("slot_fill", self._slot_fill_node)
        graph.add_node("retriever", self._retriever_node)
        graph.add_node("drafter", self._drafter_node)
        graph.add_node("validator", self._validator_node)
        graph.add_node("qa_evaluator", self._qa_evaluator_node)
        graph.add_node("qa_retry", self._qa_retry_node)
        graph.add_node("promote", self._promote_node)
        graph.add_node("handoff", self._handoff_node)
        graph.add_node("memory_save", self._memory_save_node)

        # entry: turn_count 체크 후 compress 또는 security
        graph.set_entry_point("compress")
        graph.add_conditional_edges(
            "compress",
            self._should_compress,
            {"compress": "compress", "security": "security"},
        )

        # security → intent
        graph.add_edge("security", "intent")

        # intent → branch
        graph.add_conditional_edges(
            "intent",
            self._route_intent,
            {_CLARIFY: "consultant", _DRAFT: "retriever", _PROPOSE: "promote"},
        )

        # clarify branch: consultant → slot_fill → (loop or retriever)
        graph.add_edge("consultant", "slot_fill")
        graph.add_conditional_edges(
            "slot_fill",
            self._route_slot,
            {_SLOT_LOOP: "slot_fill", _SLOT_DONE: "retriever"},
        )

        # draft branch: retriever → drafter → validator → qa_evaluator → branch
        graph.add_edge("retriever", "drafter")
        graph.add_edge("drafter", "validator")
        graph.add_edge("validator", "qa_evaluator")
        graph.add_conditional_edges(
            "qa_evaluator",
            self._route_qa,
            {_QA_PASS: "promote", _QA_RETRY: "qa_retry", _QA_FORCE: "promote"},
        )
        graph.add_edge("qa_retry", "drafter")

        # promote → handoff → memory_save → END
        graph.add_edge("promote", "handoff")
        graph.add_edge("handoff", "memory_save")
        graph.add_edge("memory_save", END)

        return graph.compile()
