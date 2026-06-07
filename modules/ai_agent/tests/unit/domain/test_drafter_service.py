from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas import DraftSpec, Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.agent import SlotFillingState
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError

from ai_agent.domain.ports import LLMPort
from ai_agent.domain.services.drafter_service import (
    _EDIT_SYSTEM_PROMPT,
    DrafterService,
    _DraftResponse,
    _EdgeDraft,
    _EditEdgeDraft,
    _EditNodeDraft,
    _EditResponse,
    _NodeDraft,
)


def _node_config(node_type: str) -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type,
        category="test",
        version="1.0",
        description="",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        is_mvp=True,
    )


def _spec() -> DraftSpec:
    return DraftSpec(
        natural_language_intent="test intent",
        discovered_entities={},
        unresolved_nodes=[],
        slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
        consultant_turn_count=0,
    )


def _mock_llm(response: _DraftResponse) -> LLMPort:
    llm = AsyncMock(spec=LLMPort)
    llm.generate_structured = AsyncMock(return_value=response)
    return llm


class TestDrafterServiceBuild:
    def setup_method(self):
        self.owner_id = uuid4()

    def _svc(self, response: _DraftResponse) -> DrafterService:
        return DrafterService(_mock_llm(response))

    @pytest.mark.asyncio
    async def test_edges_correctly_mapped_to_instance_ids(self):
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="B")],
            connections=[_EdgeDraft(from_node_type="A", to_node_type="B")],
        )
        svc = self._svc(response)
        candidates = [_node_config("A"), _node_config("B")]
        schema = await svc.draft(_spec(), candidates, self.owner_id)

        assert len(schema.connections) == 1
        edge = schema.connections[0]
        node_ids = {n.instance_id for n in schema.nodes}
        assert edge.from_instance_id in node_ids
        assert edge.to_instance_id in node_ids
        assert edge.from_instance_id != edge.to_instance_id

    @pytest.mark.asyncio
    async def test_duplicate_node_type_raises(self):
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="A")],
            connections=[],
        )
        svc = self._svc(response)
        candidates = [_node_config("A")]
        with pytest.raises(ExecutionError) as exc_info:
            await svc.draft(_spec(), candidates, self.owner_id)
        assert exc_info.value.code == "E_DUPLICATE_NODE_TYPE"

    @pytest.mark.asyncio
    async def test_unknown_edge_node_type_skipped_with_warning(self, caplog):
        import logging
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A")],
            connections=[_EdgeDraft(from_node_type="A", to_node_type="UNKNOWN")],
        )
        svc = self._svc(response)
        candidates = [_node_config("A")]
        with caplog.at_level(logging.WARNING):
            schema = await svc.draft(_spec(), candidates, self.owner_id)
        assert len(schema.connections) == 0
        assert "UNKNOWN" in caplog.text

    @pytest.mark.asyncio
    async def test_unknown_node_type_dropped_not_raised(self, caplog):
        """후보에 없는 node_type은 하드페일(E_UNKNOWN_NODE_TYPE) 대신 drop+경고로 degrade.

        #378 후속 B — 재시도 루프(retriever 재검색)가 돌 기회를 주려면 drafter가 미상
        node_type에서 즉시 죽으면 안 된다. 해당 노드를 떨구고 진행, QA 게이트가 누락을 잡는다.
        """
        import logging
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="schedule_trigger")],
            connections=[_EdgeDraft(from_node_type="schedule_trigger", to_node_type="A")],
        )
        svc = self._svc(response)
        candidates = [_node_config("A")]  # schedule_trigger는 후보에 없음
        with caplog.at_level(logging.WARNING):
            schema = await svc.draft(_spec(), candidates, self.owner_id)
        # 하드페일 안 함, 알려진 노드만 남고 미상 노드 참조 엣지는 스킵
        node_ids = {n.node_id for n in schema.nodes}
        assert node_ids == {candidates[0].node_id}
        assert len(schema.connections) == 0
        assert "schedule_trigger" in caplog.text

    @pytest.mark.asyncio
    async def test_dropped_node_types_reported_to_sink(self):
        """degrade 시 버린 node_type을 dropped_node_types sink에 기록 — 재시도 retriever가
        그 ground-truth로 재검색하게 한다(#378 후속, QA-LLM 재인지 의존 제거)."""
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="email_send")],
            connections=[],
        )
        svc = self._svc(response)
        candidates = [_node_config("A")]  # email_send는 후보에 없음 → drop
        sink: list[str] = []
        await svc.draft(_spec(), candidates, self.owner_id, dropped_node_types=sink)
        assert sink == ["email_send"]

    @pytest.mark.asyncio
    async def test_no_drop_leaves_sink_empty(self):
        """전부 후보에 있으면 sink는 비어 있다."""
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A")],
            connections=[],
        )
        svc = self._svc(response)
        sink: list[str] = []
        await svc.draft(_spec(), [_node_config("A")], self.owner_id, dropped_node_types=sink)
        assert sink == []

    @pytest.mark.asyncio
    async def test_connections_included_in_workflow_schema(self):
        response = _DraftResponse(
            name="W",
            nodes=[_NodeDraft(node_type="A"), _NodeDraft(node_type="B"), _NodeDraft(node_type="C")],
            connections=[
                _EdgeDraft(from_node_type="A", to_node_type="B"),
                _EdgeDraft(from_node_type="B", to_node_type="C"),
            ],
        )
        svc = self._svc(response)
        candidates = [_node_config("A"), _node_config("B"), _node_config("C")]
        schema = await svc.draft(_spec(), candidates, self.owner_id)

        assert len(schema.connections) == 2
        assert schema.is_draft is True


def _prior_workflow(cfg_a: NodeConfig, cfg_b: NodeConfig) -> WorkflowSchema:
    ia, ib = uuid4(), uuid4()
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="Prior WF",
        scope="private",
        is_draft=False,
        owner_user_id=uuid4(),
        nodes=[
            NodeInstance(
                instance_id=ia, node_id=cfg_a.node_id,
                parameters={"url": "https://old.com"}, position=Position(x=0, y=0),
            ),
            NodeInstance(
                instance_id=ib, node_id=cfg_b.node_id,
                parameters={"channel": "#general"}, position=Position(x=1, y=0),
            ),
        ],
        connections=[Edge(from_instance_id=ia, to_instance_id=ib, from_handle="output", to_handle="input")],
    )


class TestDrafterServiceRefine:
    """대화형 refine — prior_workflow ref 기반 편집 경로 (C)."""

    def setup_method(self):
        self.owner_id = uuid4()

    @pytest.mark.asyncio
    async def test_prior_workflow_uses_ref_based_edit_prompt(self):
        cfg_a, cfg_b = _node_config("http"), _node_config("slack")
        prior = _prior_workflow(cfg_a, cfg_b)
        llm = _mock_llm(_EditResponse(
            name="W",
            nodes=[_EditNodeDraft(ref="n0", node_type="http"), _EditNodeDraft(ref="n1", node_type="slack")],
            connections=[_EditEdgeDraft(from_ref="n0", to_ref="n1")],
        ))
        svc = DrafterService(llm)
        result = await svc.draft(_spec(), [cfg_a, cfg_b], self.owner_id, prior_workflow=prior)
        prompt, schema = llm.generate_structured.call_args.args[0], llm.generate_structured.call_args.args[1]
        assert schema is _EditResponse                  # 편집 경로 = ref 기반 응답 스키마
        assert _EDIT_SYSTEM_PROMPT in prompt
        assert "CURRENT WORKFLOW" in prompt
        assert "https://old.com" in prompt              # 기존 파라미터 보존 컨텍스트
        assert '"ref": "n0"' in prompt
        assert len(result.nodes) == 2

    @pytest.mark.asyncio
    async def test_no_prior_means_fresh_draft_response(self):
        cfg_a = _node_config("http")
        llm = _mock_llm(_DraftResponse(name="W", nodes=[_NodeDraft(node_type="http")], connections=[]))
        svc = DrafterService(llm)
        await svc.draft(_spec(), [cfg_a], self.owner_id)  # prior 없음 = fresh
        prompt, schema = llm.generate_structured.call_args.args[0], llm.generate_structured.call_args.args[1]
        assert schema is _DraftResponse
        assert "CURRENT WORKFLOW" not in prompt

    def test_serialize_for_edit_assigns_refs_and_maps_connections(self):
        cfg_a, cfg_b = _node_config("http"), _node_config("slack")
        prior = _prior_workflow(cfg_a, cfg_b)
        out = DrafterService._serialize_for_edit(prior, [cfg_a, cfg_b])
        assert out is not None
        assert [n["ref"] for n in out["nodes"]] == ["n0", "n1"]
        assert [n["node_type"] for n in out["nodes"]] == ["http", "slack"]
        assert out["nodes"][0]["parameters"]["url"] == "https://old.com"
        assert out["connections"][0]["from_ref"] == "n0"
        assert out["connections"][0]["to_ref"] == "n1"

    def test_serialize_returns_none_when_node_type_missing(self):
        # 후보에 slack 없음 → slack node_id 역매핑 불가 → None(fresh 폴백 신호)
        cfg_a, cfg_b = _node_config("http"), _node_config("slack")
        prior = _prior_workflow(cfg_a, cfg_b)
        assert DrafterService._serialize_for_edit(prior, [cfg_a]) is None

    @pytest.mark.asyncio
    async def test_unmappable_prior_falls_back_to_fresh(self):
        cfg_a, cfg_b = _node_config("http"), _node_config("slack")
        prior = _prior_workflow(cfg_a, cfg_b)
        llm = _mock_llm(_DraftResponse(name="W", nodes=[_NodeDraft(node_type="http")], connections=[]))
        svc = DrafterService(llm)
        # 후보에 slack 빠짐 → 편집 컨텍스트 생략하고 fresh로 진행(기존 노드 유실 방지)
        await svc.draft(_spec(), [cfg_a], self.owner_id, prior_workflow=prior)
        assert llm.generate_structured.call_args.args[1] is _DraftResponse  # fresh 스키마

    def test_duplicate_node_type_preserved_via_refs(self):
        # 동일 node_type 노드 2개도 ref로 구분 → 직렬화/빌드 모두 모호하지 않다(LOW~MED 해소).
        cfg = _node_config("http")
        ia, ib = uuid4(), uuid4()
        prior = WorkflowSchema(
            workflow_id=uuid4(), name="dup", scope="private", is_draft=False, owner_user_id=uuid4(),
            nodes=[
                NodeInstance(
                    instance_id=ia, node_id=cfg.node_id,
                    parameters={"url": "https://a.com"}, position=Position(x=0, y=0),
                ),
                NodeInstance(
                    instance_id=ib, node_id=cfg.node_id,
                    parameters={"url": "https://b.com"}, position=Position(x=1, y=0),
                ),
            ],
            connections=[],
        )
        out = DrafterService._serialize_for_edit(prior, [cfg])
        assert out is not None and [n["ref"] for n in out["nodes"]] == ["n0", "n1"]  # 직렬화 OK

        svc = DrafterService(AsyncMock(spec=LLMPort))
        built = svc._build_from_edit(
            _EditResponse(nodes=[
                _EditNodeDraft(ref="n0", node_type="http", parameters={"url": "https://a.com"}),
                _EditNodeDraft(ref="n1", node_type="http", parameters={"url": "https://b2.com"}),
            ]),
            [cfg],
            self.owner_id,
        )
        assert len(built.nodes) == 2  # 중복 node_type이 raise 없이 2개 인스턴스로 빌드됨
        assert {n.parameters["url"] for n in built.nodes} == {"https://a.com", "https://b2.com"}

    def test_build_from_edit_rejects_duplicate_ref(self):
        cfg = _node_config("http")
        svc = DrafterService(AsyncMock(spec=LLMPort))
        with pytest.raises(ExecutionError) as exc:
            svc._build_from_edit(
                _EditResponse(nodes=[
                    _EditNodeDraft(ref="n0", node_type="http"),
                    _EditNodeDraft(ref="n0", node_type="http"),
                ]),
                [cfg],
                self.owner_id,
            )
        assert exc.value.code == "E_DUPLICATE_REF"


class TestDrafterConnectionExposure:
    """PR2-A: 후보의 required_connections가 LLM 프롬프트에 노출되는지 검증."""

    @pytest.mark.asyncio
    async def test_required_connections_passed_to_llm_prompt(self):
        owner_id = uuid4()
        response = _DraftResponse(
            name="W", nodes=[_NodeDraft(node_type="gmail_send")], connections=[]
        )
        llm = _mock_llm(response)
        svc = DrafterService(llm)
        cfg = _node_config("gmail_send").model_copy(update={"required_connections": ["google"]})
        await svc.draft(_spec(), [cfg], owner_id)

        prompt = llm.generate_structured.call_args.args[0]
        assert "required_connections" in prompt
        assert "google" in prompt


class TestDrafterPersonalization:
    """REQ-004 개인화 배선 — RAG로 회수한 personal_patterns가 drafter 프롬프트에 주입되는지."""

    def setup_method(self):
        self.owner_id = uuid4()

    @pytest.mark.asyncio
    async def test_personal_patterns_injected_into_fresh_prompt(self):
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        svc = DrafterService(llm)
        await svc.draft(
            _spec(), [_node_config("slack")], self.owner_id,
            personal_patterns=["[알림 선호] Slack 알림은 항상 #automation 채널로 보낸다"],
        )
        prompt = llm.generate_structured.call_args.args[0]
        assert "USER PATTERNS" in prompt
        assert "#automation" in prompt

    @pytest.mark.asyncio
    async def test_no_patterns_leaves_prompt_unchanged(self):
        # 개인 패턴 없음(기본값) → USER PATTERNS 블록 미삽입(개인화 미적용 시 무영향).
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(_spec(), [_node_config("slack")], self.owner_id)
        prompt = llm.generate_structured.call_args.args[0]
        assert "USER PATTERNS" not in prompt

    @pytest.mark.asyncio
    async def test_personal_patterns_injected_into_edit_prompt(self):
        cfg_a, cfg_b = _node_config("http"), _node_config("slack")
        prior = _prior_workflow(cfg_a, cfg_b)
        llm = _mock_llm(_EditResponse(
            name="W",
            nodes=[_EditNodeDraft(ref="n0", node_type="http"), _EditNodeDraft(ref="n1", node_type="slack")],
            connections=[_EditEdgeDraft(from_ref="n0", to_ref="n1")],
        ))
        svc = DrafterService(llm)
        await svc.draft(
            _spec(), [cfg_a, cfg_b], self.owner_id, prior_workflow=prior,
            personal_patterns=["[요약 선호] 보고서는 한국어로 3줄 요약"],
        )
        prompt = llm.generate_structured.call_args.args[0]
        assert _EDIT_SYSTEM_PROMPT in prompt
        assert "USER PATTERNS" in prompt
        assert "3줄 요약" in prompt


class TestDrafterSkillBinding:
    """#372 결함 A — skill_selected 시 LLM 노드 포함을 drafter 프롬프트에 지시하는지."""

    def setup_method(self):
        self.owner_id = uuid4()

    @pytest.mark.asyncio
    async def test_skill_selected_injects_binding_block(self):
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(
            _spec(), [_node_config("slack")], self.owner_id, skill_selected=True,
        )
        prompt = llm.generate_structured.call_args.args[0]
        assert "SKILL BINDING" in prompt
        assert 'category is "ai"' in prompt

    @pytest.mark.asyncio
    async def test_not_selected_leaves_prompt_unchanged(self):
        # 기본값(skill_selected=False) → SKILL BINDING 블록 미삽입.
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(_spec(), [_node_config("slack")], self.owner_id)
        prompt = llm.generate_structured.call_args.args[0]
        assert "SKILL BINDING" not in prompt

    @pytest.mark.asyncio
    async def test_composer_instructions_appended_when_present(self):
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(
            _spec(), [_node_config("slack")], self.owner_id,
            skill_selected=True,
            skill_composer_instructions="이 스킬은 LLM 노드 + Email 노드를 순서대로 엮어야 합니다.",
        )
        prompt = llm.generate_structured.call_args.args[0]
        assert "SKILL BINDING" in prompt
        assert "Email 노드를 순서대로" in prompt


class TestDrafterRefGeneration:
    """L1b — drafter가 생성한 ${node_type.field} / ${ref.field} 참조를 instance_id로 재작성."""

    def setup_method(self):
        self.owner_id = uuid4()

    def _svc(self, response):
        return DrafterService(_mock_llm(response))

    @pytest.mark.asyncio
    async def test_fresh_draft_rewrites_node_type_token_to_instance_id(self):
        response = _DraftResponse(
            name="W",
            nodes=[
                _NodeDraft(node_type="sheets"),
                _NodeDraft(node_type="summary", parameters={"document_text": "${sheets.values}"}),
            ],
            connections=[_EdgeDraft(from_node_type="sheets", to_node_type="summary")],
        )
        candidates = [_node_config("sheets"), _node_config("summary")]
        schema = await self._svc(response).draft(_spec(), candidates, self.owner_id)

        type_by_id = {c.node_id: c.node_type for c in candidates}
        sheets = next(n for n in schema.nodes if type_by_id[n.node_id] == "sheets")
        summary = next(n for n in schema.nodes if type_by_id[n.node_id] == "summary")
        assert summary.parameters["document_text"] == f"${{{sheets.instance_id}.values}}"

    @pytest.mark.asyncio
    async def test_unknown_ref_token_preserved(self):
        response = _DraftResponse(
            nodes=[_NodeDraft(node_type="summary", parameters={"x": "${ghost.field}"})],
            connections=[],
        )
        schema = await self._svc(response).draft(_spec(), [_node_config("summary")], self.owner_id)
        assert schema.nodes[0].parameters["x"] == "${ghost.field}"

    @pytest.mark.asyncio
    async def test_embedded_ref_rewritten(self):
        response = _DraftResponse(
            nodes=[
                _NodeDraft(node_type="sheets"),
                _NodeDraft(node_type="slack", parameters={"text": "요약:\n${sheets.summary}"}),
            ],
            connections=[_EdgeDraft(from_node_type="sheets", to_node_type="slack")],
        )
        candidates = [_node_config("sheets"), _node_config("slack")]
        schema = await self._svc(response).draft(_spec(), candidates, self.owner_id)
        type_by_id = {c.node_id: c.node_type for c in candidates}
        sheets = next(n for n in schema.nodes if type_by_id[n.node_id] == "sheets")
        slack = next(n for n in schema.nodes if type_by_id[n.node_id] == "slack")
        assert slack.parameters["text"] == f"요약:\n${{{sheets.instance_id}.summary}}"

    @pytest.mark.asyncio
    async def test_catalog_exposes_outputs_to_llm(self):
        response = _DraftResponse(nodes=[_NodeDraft(node_type="sheets")], connections=[])
        llm = _mock_llm(response)
        cfg = _node_config("sheets").model_copy(
            update={"output_schema": {"properties": {"values": {}, "rows": {}}}}
        )
        await DrafterService(llm).draft(_spec(), [cfg], self.owner_id)
        prompt = llm.generate_structured.call_args.args[0]
        assert "outputs" in prompt and "values" in prompt

    @pytest.mark.asyncio
    async def test_valid_output_field_ref_unchanged(self):
        # 상류 출력에 실제 존재하는 필드 참조 → 보정 없이 instance_id만 치환되어 보존.
        response = _DraftResponse(
            nodes=[
                _NodeDraft(node_type="sheets"),
                _NodeDraft(node_type="summary", parameters={"document_text": "${sheets.values}"}),
            ],
            connections=[_EdgeDraft(from_node_type="sheets", to_node_type="summary")],
        )
        sheets_cfg = _node_config("sheets").model_copy(
            update={"output_schema": {"properties": {"values": {}, "rows": {}}}}
        )
        candidates = [sheets_cfg, _node_config("summary")]
        schema = await self._svc(response).draft(_spec(), candidates, self.owner_id)
        type_by_id = {c.node_id: c.node_type for c in candidates}
        sheets = next(n for n in schema.nodes if type_by_id[n.node_id] == "sheets")
        summary = next(n for n in schema.nodes if type_by_id[n.node_id] == "summary")
        assert summary.parameters["document_text"] == f"${{{sheets.instance_id}.values}}"

    @pytest.mark.asyncio
    async def test_invalid_field_remapped_when_single_output(self):
        # 환각 필드(.output)인데 상류 출력이 단일(result) → result로 보정.
        response = _DraftResponse(
            nodes=[
                _NodeDraft(node_type="gen"),
                _NodeDraft(node_type="summary", parameters={"document_text": "${gen.output}"}),
            ],
            connections=[_EdgeDraft(from_node_type="gen", to_node_type="summary")],
        )
        gen_cfg = _node_config("gen").model_copy(
            update={"output_schema": {"properties": {"result": {}}}}
        )
        candidates = [gen_cfg, _node_config("summary")]
        schema = await self._svc(response).draft(_spec(), candidates, self.owner_id)
        type_by_id = {c.node_id: c.node_type for c in candidates}
        gen = next(n for n in schema.nodes if type_by_id[n.node_id] == "gen")
        summary = next(n for n in schema.nodes if type_by_id[n.node_id] == "summary")
        assert summary.parameters["document_text"] == f"${{{gen.instance_id}.result}}"

    @pytest.mark.asyncio
    async def test_invalid_field_preserved_with_warning_when_multi_output(self, caplog):
        # 재현 케이스: 환각 필드(.values)인데 상류 출력이 다중 → 보정 불가, 보존 + 경고.
        import logging
        response = _DraftResponse(
            nodes=[
                _NodeDraft(node_type="sched"),
                _NodeDraft(node_type="summary", parameters={"document_text": "${sched.values}"}),
            ],
            connections=[_EdgeDraft(from_node_type="sched", to_node_type="summary")],
        )
        sched_cfg = _node_config("sched").model_copy(
            update={"output_schema": {"properties": {"scheduled_at": {}, "channel_breakdown": {}}}}
        )
        candidates = [sched_cfg, _node_config("summary")]
        with caplog.at_level(logging.WARNING):
            schema = await self._svc(response).draft(_spec(), candidates, self.owner_id)
        type_by_id = {c.node_id: c.node_type for c in candidates}
        sched = next(n for n in schema.nodes if type_by_id[n.node_id] == "sched")
        summary = next(n for n in schema.nodes if type_by_id[n.node_id] == "summary")
        assert summary.parameters["document_text"] == f"${{{sched.instance_id}.values}}"
        assert "보정 불가" in caplog.text

    @pytest.mark.asyncio
    async def test_prompt_drops_biasing_values_example(self):
        # `.values` 하드코딩 예시가 프롬프트에서 제거됐는지(편향 방지) 회귀 가드.
        response = _DraftResponse(nodes=[_NodeDraft(node_type="sheets")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(_spec(), [_node_config("sheets")], self.owner_id)
        prompt = llm.generate_structured.call_args.args[0]
        assert "google_sheets_read.values" not in prompt
        assert "VERBATIM" in prompt


class TestDrafterMotifBlock:
    """ADR-0026 Phase 2 — pattern_templates가 drafter 프롬프트에 모티프 블록으로 주입되는지."""

    def setup_method(self):
        self.owner_id = uuid4()

    def _pattern(self, name: str, role_slots: dict):
        from ai_agent.domain.value_objects.ontology import PatternTemplate

        return PatternTemplate(name=name, intent="검증", role_slots=role_slots)

    @pytest.mark.asyncio
    async def test_loop_motif_injects_back_edge_guidance(self):
        """quality_gate_loop 패턴 시 BACK-EDGE + 단일 ai 노드 규칙이 프롬프트에 포함된다 (이슈 #406)."""
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        patterns = [self._pattern("quality_gate_loop", {"generator": ("gemma_chat",), "evaluator": ("if_condition",)})]
        await DrafterService(llm).draft(
            _spec(), [_node_config("slack")], self.owner_id, pattern_templates=patterns,
        )
        prompt = llm.generate_structured.call_args.args[0]
        assert "WORKFLOW MOTIFS" in prompt
        assert "quality_gate_loop" in prompt
        assert "BACK-EDGE" in prompt
        assert "LOOP" in prompt
        # 단일 ai 노드 규칙 — 두 번째 gemma_chat 추가 금지 지시
        assert "do NOT add a second" in prompt

    @pytest.mark.asyncio
    async def test_loop_prompt_also_has_loops_section(self):
        """_SYSTEM_PROMPT에 LOOPS 섹션이 있어 back-edge 방법을 알려준다."""
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(_spec(), [_node_config("slack")], self.owner_id)
        prompt = llm.generate_structured.call_args.args[0]
        assert "LOOPS" in prompt
        assert "back-edge" in prompt

    @pytest.mark.asyncio
    async def test_no_motif_block_when_no_patterns(self):
        response = _DraftResponse(name="W", nodes=[_NodeDraft(node_type="slack")], connections=[])
        llm = _mock_llm(response)
        await DrafterService(llm).draft(_spec(), [_node_config("slack")], self.owner_id)
        prompt = llm.generate_structured.call_args.args[0]
        assert "WORKFLOW MOTIFS" not in prompt

    @pytest.mark.asyncio
    async def test_motif_block_injected_in_edit_path_too(self):
        cfg_a, cfg_b = _node_config("http"), _node_config("slack")
        prior = _prior_workflow(cfg_a, cfg_b)
        patterns = [self._pattern("quality_gate_loop", {"generator": ("gemma_chat",), "evaluator": ("if_condition",)})]
        llm = _mock_llm(_EditResponse(
            name="W",
            nodes=[_EditNodeDraft(ref="n0", node_type="http"), _EditNodeDraft(ref="n1", node_type="slack")],
            connections=[],
        ))
        await DrafterService(llm).draft(
            _spec(), [cfg_a, cfg_b], self.owner_id, prior_workflow=prior, pattern_templates=patterns,
        )
        prompt = llm.generate_structured.call_args.args[0]
        assert "WORKFLOW MOTIFS" in prompt
        assert "BACK-EDGE" in prompt

    def test_motif_block_static_empty_when_no_slots(self):
        patterns = [self._pattern("no_slots_pattern", {})]
        block = DrafterService._motif_block(patterns)
        assert block == ""

    def test_motif_block_static_empty_when_none(self):
        assert DrafterService._motif_block(None) == ""

    def test_non_loop_motif_uses_simple_slot_format(self):
        """루프 패턴이 아닌 일반 모티프는 슬롯 목록만 출력한다."""
        from ai_agent.domain.value_objects.ontology import PatternTemplate

        pt = PatternTemplate(name="unknown_pattern", intent="기타", role_slots={"step": ("some_node",)})
        block = DrafterService._motif_block([pt])
        assert "BACK-EDGE" not in block
        assert "unknown_pattern" in block
        assert "step" in block


@pytest.mark.asyncio
async def test_refine_rewrites_ref_token_to_instance_id():
    """L1b refine 경로 — _build_from_edit가 ${<ref>.<field>}를 instance_id로 재작성."""
    cfg_a, cfg_b = _node_config("http"), _node_config("slack")
    prior = _prior_workflow(cfg_a, cfg_b)
    llm = _mock_llm(_EditResponse(
        name="W",
        nodes=[
            _EditNodeDraft(ref="n0", node_type="http"),
            _EditNodeDraft(ref="n1", node_type="slack", parameters={"text": "${n0.body}"}),
        ],
        connections=[_EditEdgeDraft(from_ref="n0", to_ref="n1")],
    ))
    result = await DrafterService(llm).draft(_spec(), [cfg_a, cfg_b], uuid4(), prior_workflow=prior)

    http_id = next(n.instance_id for n in result.nodes if n.node_id == cfg_a.node_id)
    slack = next(n for n in result.nodes if n.node_id == cfg_b.node_id)
    assert slack.parameters["text"] == f"${{{http_id}.body}}"
